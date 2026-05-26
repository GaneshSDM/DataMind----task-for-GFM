"""
RAG ingestion orchestrator.
Called as a FastAPI BackgroundTask — runs after HTTP response is sent.

Flow per file:
  1. Create RagIngestionJob (status=processing)
  2. Validate extension
  3. Extract text
  4. Chunk text
  5. Embed chunks (batch)
  6. Create RagFile record + save chunks
  7. Mark job completed / failed
Finally:
  8. Finalize RagIngestionRun (status + counters)
"""

import os
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def process_run(
    run_id: str,
    files_data: List[Dict[str, Any]],
    meta: Dict[str, Any],
):
    """
    Entry point for background processing.

    files_data items: {filename, content (bytes), content_type, size}
    meta: {domain_id, sub_domain_id, category_id, sub_category_id, user_id}
    """
    from app.db.session import SessionLocal
    db = SessionLocal()

    processed = 0
    failed    = 0
    invalid   = 0
    user_id   = meta['user_id']

    try:
        from app.rag.supported_formats import is_supported
        from app.rag.extractor         import extract, ExtractorError
        from app.rag.chunker           import chunk_text
        from app.rag.embedder          import embed
        from app.rag import storage
        from app.rag.storage           import DuplicateFileError

        for file_data in files_data:
            filename     = file_data['filename']
            file_bytes   = file_data['content']
            content_type = file_data.get('content_type', '')
            job          = None

            try:
                # 1. Create job record
                job = storage.create_job(db, run_id=run_id, filename=filename, user_id=user_id)
                db.commit()

                # 2. Validate extension
                if not is_supported(filename):
                    invalid += 1
                    storage.complete_job(
                        db, job.job_id,
                        status='skipped',
                        message=f"Unsupported file type: {os.path.splitext(filename)[1]}",
                        user_id=user_id,
                    )
                    storage.log_error(
                        db, run_id=run_id, job_id=job.job_id,
                        file_path=filename, error_type='unsupported',
                        error_message=f"Extension not in supported list: {filename}",
                        user_id=user_id,
                    )
                    db.commit()
                    continue

                # 3. Extract text
                text, page_count, extraction_method = extract(file_bytes, filename)

                if not text or not text.strip():
                    invalid += 1
                    storage.complete_job(db, job.job_id, status='failed', message='No text extracted', user_id=user_id)
                    storage.log_error(db, run_id=run_id, job_id=job.job_id, file_path=filename,
                                      error_type='extractor', error_message='Extraction returned empty text', user_id=user_id)
                    db.commit()
                    continue

                # 4. Chunk
                chunks = chunk_text(text)
                if not chunks:
                    invalid += 1
                    storage.complete_job(db, job.job_id, status='failed', message='No chunks produced', user_id=user_id)
                    db.commit()
                    continue

                # 5. Embed
                embeddings = embed(chunks)

                # 6. Save file record + chunks
                ext      = os.path.splitext(filename.lower())[1].lstrip('.')
                rag_file = storage.create_file_record(
                    db,
                    run_id            = run_id,
                    filename          = filename,
                    file_bytes        = file_bytes,
                    file_type         = ext,
                    mime_type         = content_type,
                    domain_id         = meta['domain_id'],
                    sub_domain_id     = meta['sub_domain_id'],
                    category_id       = meta['category_id'],
                    sub_category_id   = meta.get('sub_category_id'),
                    description       = meta.get('description'),
                    page_count        = page_count,
                    extraction_method = extraction_method,
                    user_id           = user_id,
                )

                storage.save_chunks(
                    db,
                    file_id    = rag_file.file_id,
                    chunks     = chunks,
                    embeddings = embeddings,
                    user_id    = user_id,
                )

                storage.update_file_status(db, rag_file.file_id, 'active', user_id)
                storage.complete_job(
                    db, job.job_id,
                    file_id = rag_file.file_id,
                    status  = 'completed',
                    message = f"OK — {len(chunks)} chunks embedded",
                    user_id = user_id,
                )
                db.commit()
                processed += 1
                logger.info(f"[RAG] {filename}: {len(chunks)} chunks stored. run={run_id}")

            except DuplicateFileError as e:
                invalid += 1
                logger.info(f"[RAG] Duplicate skipped {filename}: {e}")
                if job:
                    storage.complete_job(db, job.job_id, status='skipped', message=str(e), user_id=user_id)
                try:
                    db.commit()
                except Exception:
                    db.rollback()

            except ExtractorError as e:
                failed += 1
                logger.warning(f"[RAG] Extractor error {filename}: {e}")
                if job:
                    storage.complete_job(db, job.job_id, status='failed', message=str(e), user_id=user_id)
                storage.log_error(db, run_id=run_id, job_id=getattr(job, 'job_id', None),
                                  file_path=filename, error_type='extractor',
                                  error_message=str(e), user_id=user_id)
                try:
                    db.commit()
                except Exception:
                    db.rollback()

            except Exception as e:
                failed += 1
                logger.exception(f"[RAG] Unexpected error {filename}: {e}")
                try:
                    db.rollback()
                    if job:
                        storage.complete_job(db, job.job_id, status='failed', message=str(e), user_id=user_id)
                    storage.log_error(db, run_id=run_id, job_id=getattr(job, 'job_id', None),
                                      file_path=filename, error_type='db',
                                      error_message=str(e), user_id=user_id)
                    db.commit()
                except Exception:
                    db.rollback()

        # 8. Finalize run
        storage.finalize_run(
            db, run_id,
            processed = processed,
            failed    = failed,
            invalid   = invalid,
            user_id   = user_id,
        )
        db.commit()
        logger.info(f"[RAG] Run {run_id} finished — processed={processed} failed={failed} invalid={invalid}")

    except Exception as e:
        logger.exception(f"[RAG] Fatal error in process_run {run_id}: {e}")
        try:
            from app.models.rag_models import RagIngestionRun
            from datetime import datetime, timezone
            run = db.query(RagIngestionRun).filter(RagIngestionRun.run_id == run_id).first()
            if run:
                run.status       = 'failed'
                run.completed_at = datetime.now(timezone.utc)
                run.updated_by   = user_id
                db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()
