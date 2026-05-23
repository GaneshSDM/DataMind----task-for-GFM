"""
rag_retriever.py
----------------
Semantic retrieval from tracopp.rag_document_chunks using pgvector.

Embeds intent description with BAAI/bge-large-en-v1.5 (1024-dim) — same model
used during RAG ingestion — then runs cosine similarity search filtered to the
user's allowed domain IDs.

Production note:
  Model loads from HuggingFace cache (HF_HOME or SENTENCE_TRANSFORMERS_HOME).
  Set HF_HOME=/models and mount a persistent volume so containers skip download.
"""

import logging
import numpy as np
import psycopg2
from typing import Optional
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
from config.settings import DATABASE_URL

load_dotenv()

logger = logging.getLogger("aria.rag_retriever")

_EMBED_MODEL_NAME = "BAAI/bge-large-en-v1.5"
_EMBED_DIM = 1024
_model: Optional[SentenceTransformer] = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        logger.info("Loading embedding model %s…", _EMBED_MODEL_NAME)
        _model = SentenceTransformer(_EMBED_MODEL_NAME)
        logger.info("Embedding model ready")
    return _model


def _embed(text: str) -> list[float]:
    vec = _get_model().encode(text, normalize_embeddings=True)
    return vec.tolist()


def retrieve_chunks(
    intent_description: str,
    allowed_domain_ids: list[int],
    top_k: int = 5,
) -> list[dict]:
    """
    Embed intent_description and retrieve top_k most similar chunks
    from tracopp.rag_document_chunks, filtered to allowed_domain_ids.

    Returns list of dicts:
      filename, chunk_text, domain, subdomain, similarity (0-1)
    """
    if not DATABASE_URL:
        logger.warning("DATABASE_URL not set — skipping RAG retrieval")
        return []

    if not allowed_domain_ids:
        logger.warning("No domain IDs provided — skipping RAG retrieval")
        return []

    try:
        query_vec = _embed(intent_description)
    except Exception as e:
        logger.error("Embedding failed: %s", e)
        return []

    # Format vector as pgvector literal: '[0.1, 0.2, ...]'
    vec_literal = "[" + ",".join(f"{v:.8f}" for v in query_vec) + "]"

    sql = """
        SELECT
            rdc.chunk_text,
            rdc.chunk_index,
            rdc.page_number,
            rdc.content_type,
            rf.file_id,
            rf.original_file_name,
            rf.description,
            rf.file_type,
            d.domain_name,
            sd.sub_domain_name,
            1 - (rdc.embedding <=> %s::vector) AS similarity
        FROM tracopp.rag_document_chunks rdc
        JOIN tracopp.rag_files rf   ON rf.file_id       = rdc.file_id
        JOIN tracopp.domain d       ON d.domain_id      = rf.domain_id
        JOIN tracopp.sub_domain sd  ON sd.sub_domain_id = rf.sub_domain_id
        WHERE rf.domain_id = ANY(%s)
          AND rf.is_active  = true
          AND rf.status     = 'active'
        ORDER BY rdc.embedding <=> %s::vector ASC
        LIMIT %s
    """

    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute(sql, (vec_literal, allowed_domain_ids, vec_literal, top_k))
        rows = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        logger.error("RAG retrieval DB error: %s", e)
        return []

    results = []
    for row in rows:
        (chunk_text, chunk_index, page_number, content_type,
         file_id, filename, file_description, file_type,
         domain, subdomain, similarity) = row
        results.append({
            "file_id":          str(file_id),
            "filename":         filename,
            "file_description": file_description or "",
            "file_type":        file_type,
            "chunk_index":      chunk_index,
            "page_number":      page_number,
            "content_type":     content_type,
            "chunk_text":       chunk_text,
            "domain":           domain,
            "subdomain":        subdomain,
            "similarity":       round(float(similarity), 4),
        })

    logger.info(
        "RAG retrieval: '%s…' → %d chunks (top sim=%.3f)",
        intent_description[:50],
        len(results),
        results[0]["similarity"] if results else 0,
    )
    return results
