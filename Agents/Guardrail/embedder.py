import os
import numpy as np
from sentence_transformers import SentenceTransformer

_MODEL_NAME = "all-MiniLM-L6-v2"
_model: SentenceTransformer | None = None

# Remote embedder API (optional — set EMBEDDER_BASE_URL in backend/.env)
_EMBEDDER_BASE_URL = os.getenv("EMBEDDER_BASE_URL", "").rstrip("/")
_EMBEDDER_MODEL    = os.getenv("EMBEDDER_MODEL", _MODEL_NAME)
_EMBEDDER_API_KEY  = os.getenv("LLM_API_KEY", "")


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(_MODEL_NAME)
    return _model


def _embed_remote(text: str) -> list[float]:
    import urllib.request, json as _json
    payload = _json.dumps({"input": text, "model": _EMBEDDER_MODEL}).encode()
    req = urllib.request.Request(
        _EMBEDDER_BASE_URL + "/embeddings",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {_EMBEDDER_API_KEY}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = _json.loads(resp.read())
    return body["data"][0]["embedding"]


def embed(text: str) -> list[float]:
    if _EMBEDDER_BASE_URL:
        return _embed_remote(text)
    return _get_model().encode(text).tolist()


def embed_batch(texts: list[str]) -> list[list[float]]:
    if _EMBEDDER_BASE_URL:
        return [_embed_remote(t) for t in texts]
    return _get_model().encode(texts).tolist()


def cosine_similarity(a: list[float], b: list[float]) -> float:
    va, vb = np.array(a), np.array(b)
    norm = np.linalg.norm(va) * np.linalg.norm(vb)
    if norm == 0:
        return 0.0
    return float(np.dot(va, vb) / norm)
