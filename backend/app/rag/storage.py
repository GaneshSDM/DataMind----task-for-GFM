"""
All DB write operations for the RAG pipeline.
Isolated here so pipeline.py has no direct SQLAlchemy imports.
"""

import uuid
import hashlib
import logging
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.rag_models import (
    RagFile, RagDocumentChunk,
    RagIngestionJob, RagIngestionRun, RagIngestionError,
)

logger = logging.getLogger(__name__)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ── RagFile ───────────────────────────────────────────────────────────────────

def create_file_record(
    db: Session,
    *,
    run_id: str,
    filename: str,
    file_bytes: bytes,
    file_type: str,
    mime_type: str,
    domain_id: int,
    sub_domain_id: int,
    category_id: int,
    sub_category_id: Optional[int],
    description: Optional[str],
    page_count: int,
    extraction_method: str,
    user_id: int,
) -> RagFile:
    f = RagFile(
        original_file_name  = filename,
        storage_uri         = f"run:{run_id}/{filename}",
        relative_path       = filename,
        file_hash           = sha256(file_bytes),
        file_type           = file_type,
        mime_type           = mime_type,
        file_size_bytes     = len(file_bytes),
        page_count          = page_count,
        domain_id           = domain_id,
        sub_domain_id       = sub_domain_id,
        category_id         = category_id,
        sub_category_id     = sub_category_id,
        description         = description,
        version_no          = 1,
        status              = 'processing',
        extraction_method   = extraction_method,
        embedding_model     = "BAAI/bge-large-en-v1.5",
        embedding_dimension = 1024,
        is_active           = True,
        created_by          = user_id,
    )
    db.add(f)
    db.flush()  # get file_id without committing
    return f


def update_file_status(db: Session, file_id, status: str, user_id: int):
    f = db.query(RagFile).filter(RagFile.file_id == file_id).first()
    if f:
        f.status      = status
        f.updated_by  = user_id
        f.updated_date = datetime.now(timezone.utc)


# ── RagDocumentChunk ──────────────────────────────────────────────────────────

def save_chunks(
    db: Session,
    *,
    file_id,
    chunks: List[str],
    embeddings: List[List[float]],
    user_id: int,
):
    """Bulk-insert all chunks for a file in one transaction flush."""
    for idx, (text, vector) in enumerate(zip(chunks, embeddings)):
        chunk = RagDocumentChunk(
            file_id     = file_id,
            chunk_index = idx,
            chunk_text  = text,
            token_count = len(text.split()),  # rough word-count proxy
            embedding   = vector,
            created_by  = user_id,
        )
        db.add(chunk)
    db.flush()


# ── RagIngestionJob ───────────────────────────────────────────────────────────

def create_job(db: Session, *, run_id: str, filename: str, user_id: int) -> RagIngestionJob:
    job = RagIngestionJob(
        run_id      = run_id,
        storage_uri = filename,
        job_type    = 'new_file',
        status      = 'processing',
        started_at  = datetime.now(timezone.utc),
        created_by  = user_id,
    )
    db.add(job)
    db.flush()
    return job


def complete_job(db: Session, job_id, *, file_id=None, status: str, message: str, user_id: int):
    job = db.query(RagIngestionJob).filter(RagIngestionJob.job_id == job_id).first()
    if job:
        job.file_id      = file_id
        job.status       = status
        job.message      = message
        job.completed_at = datetime.now(timezone.utc)
        job.updated_by   = user_id
        job.updated_date = datetime.now(timezone.utc)


# ── RagIngestionError ─────────────────────────────────────────────────────────

def log_error(
    db: Session,
    *,
    run_id: str,
    job_id=None,
    file_path: str,
    error_type: str,
    error_message: str,
    user_id: int,
):
    err = RagIngestionError(
        run_id        = run_id,
        job_id        = job_id,
        file_path     = file_path,
        error_type    = error_type,
        error_message = error_message,
        created_by    = user_id,
    )
    db.add(err)


# ── RagIngestionRun ───────────────────────────────────────────────────────────

def finalize_run(
    db: Session,
    run_id: str,
    *,
    processed: int,
    failed: int,
    invalid: int,
    user_id: int,
):
    run = db.query(RagIngestionRun).filter(RagIngestionRun.run_id == run_id).first()
    if not run:
        return

    run.processed_files = processed
    run.failed_files    = failed
    run.invalid_files   = invalid
    run.completed_at    = datetime.now(timezone.utc)
    run.updated_by      = user_id
    run.updated_date    = datetime.now(timezone.utc)

    if failed == 0 and invalid == 0:
        run.status = 'completed'
    elif processed == 0:
        run.status = 'failed'
    else:
        run.status = 'completed_with_errors'

    run.run_summary = {
        'processed': processed,
        'failed':    failed,
        'invalid':   invalid,
        'total':     run.total_files_found,
    }
