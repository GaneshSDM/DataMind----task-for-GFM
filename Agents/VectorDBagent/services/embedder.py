"""
Singleton sentence-transformer embedder for RAVEN.
Model: BAAI/bge-large-en-v1.5 (1024-dim) — same as ARIA rag_retriever.
L2-normalised embeddings for cosine similarity via pgvector <=> operator.

Remote API fallback: if EMBEDDER_BASE_URL is set, calls remote /v1/embeddings endpoint
instead of loading a local model. Useful for CDAC / cloud deployment.
"""
import logging
import os

logger = logging.getLogger("raven.embedder")

_embedder = None


class Embedder:
    def __init__(self):
        from config import get_settings
        s = get_settings()
        self.model_name       = s.embedding_model
        self.dim              = s.embedding_dim
        self._base_url        = s.embedder_base_url.rstrip("/") if s.embedder_base_url else ""
        self._api_key         = s.embedder_api_key or os.getenv("LLM_API_KEY", "")
        self._local_model     = None

        if self._base_url:
            logger.info("RAVEN embedder → remote API at %s (model=%s)", self._base_url, self.model_name)
        else:
            from sentence_transformers import SentenceTransformer
            logger.info("RAVEN loading local embedder model=%s dim=%d", self.model_name, self.dim)
            self._local_model = SentenceTransformer(self.model_name)
            logger.info("RAVEN embedder loaded")

    def warmup(self):
        """Pre-warm model to avoid cold-start latency on first request."""
        if self._local_model:
            self._local_model.encode(["warmup"], normalize_embeddings=True)
            logger.info("RAVEN embedder warmup complete")

    def embed(self, text: str) -> list[float]:
        """Embed a single text string. Returns L2-normalised 1024-dim vector."""
        if self._base_url:
            import httpx
            resp = httpx.post(
                self._base_url + "/embeddings",
                json={"input": text, "model": self.model_name},
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=30.0,
            )
            resp.raise_for_status()
            return resp.json()["data"][0]["embedding"]
        vec = self._local_model.encode([text], normalize_embeddings=True)[0]
        return vec.tolist()


def get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        _embedder = Embedder()
    return _embedder
