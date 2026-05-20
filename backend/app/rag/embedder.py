"""
Embedding model singleton.
Loads BAAI/bge-large-en-v1.5 once at first use; reuses across requests.
BGE-large produces 1024-dim vectors; normalize_embeddings=True for cosine similarity.
"""

import logging
from typing import List

logger = logging.getLogger(__name__)

MODEL_NAME    = "BAAI/bge-large-en-v1.5"
EMBEDDING_DIM = 1024
BATCH_SIZE    = 32   # tune down if GPU OOM or CPU RAM tight

_model = None


def get_model():
    """Lazy-load model; thread-safe for single-process uvicorn."""
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading embedding model: {MODEL_NAME} ...")
            _model = SentenceTransformer(MODEL_NAME)
            logger.info(f"Embedding model ready — dim={EMBEDDING_DIM}")
        except ImportError:
            raise RuntimeError(
                "sentence-transformers not installed. "
                "Run: pip install sentence-transformers torch"
            )
    return _model


def embed(texts: List[str]) -> List[List[float]]:
    """
    Embed a list of strings.
    Returns list of 1024-dim float vectors (L2-normalised).
    """
    if not texts:
        return []
    model = get_model()
    vectors = model.encode(
        texts,
        normalize_embeddings=True,
        batch_size=BATCH_SIZE,
        show_progress_bar=False,
        convert_to_numpy=True,
    )
    return vectors.tolist()


def warmup():
    """Pre-load model at startup so first request isn't slow."""
    try:
        get_model()
    except Exception as e:
        logger.warning(f"Embedder warmup failed (non-fatal): {e}")
