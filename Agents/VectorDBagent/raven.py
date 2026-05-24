"""
R A V E N
---------
Retrieval and Vector Exploration Network — FastAPI microservice.

Receives ARIA-classified unstructured intents + security_profile.
Validates domain access, embeds query text, returns similarity_search_inputs[]
ready for SPYDER's rag_service to execute pgvector cosine search.

Port 8006  ·  POST /rag/query  ·  GET /health
"""
import os
import sys
import logging
from contextlib import asynccontextmanager
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

# Single source of truth — load from central backend .env
_BACKEND_ENV = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../backend/.env")
)
load_dotenv(dotenv_path=_BACKEND_ENV)

from fastapi import FastAPI
from pydantic import BaseModel

from config import get_settings
from services.embedder import get_embedder
from services.access_validator import is_domain_allowed, extract_document_filter, check_file_access

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("raven")

RAG_TABLE = "tracopp.rag_document_chunks"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("RAVEN warming up embedder…")
    emb = get_embedder()
    emb.warmup()
    logger.info("RAVEN ready — model=%s dim=%d", emb.model_name, emb.dim)
    yield


app = FastAPI(
    title="RAVEN — Retrieval and Vector Exploration Network",
    description="Generates pgvector similarity-search inputs from ARIA unstructured intents",
    version="1.0.0",
    lifespan=lifespan,
)


# ── Models ─────────────────────────────────────────────────────────────────────

class IntentItem(BaseModel):
    intent_id: int
    description: str
    domain: str
    sub_domain: Optional[str] = None
    data_source: str                           # Structured | Unstructured | Both
    unstructured_source: Optional[str] = None  # "filename.pdf — description"
    relevant_columns: list = []


class RAVENRequest(BaseModel):
    request_id: str
    prompt: str
    intents: list[IntentItem] = []
    security_profile: dict = {}
    top_k: int = 5


class SearchInput(BaseModel):
    embedding_id: str
    label: str
    content: str
    embedding: list[float]
    rag_table: str
    document_filter: Optional[str] = None
    top_k: int


class RAVENResponse(BaseModel):
    request_id: str
    status: str                                # success | skipped | error
    similarity_search_inputs: list[SearchInput] = []
    skipped_intents: list[int] = []
    error: Optional[str] = None


# ── Endpoint ───────────────────────────────────────────────────────────────────

@app.post("/rag/query", response_model=RAVENResponse)
def rag_query(request: RAVENRequest):
    embedder = get_embedder()

    # Filter intents that need unstructured retrieval
    rag_intents = [
        i for i in request.intents
        if i.data_source in ("Unstructured", "Both")
    ]

    if not rag_intents:
        logger.info(
            "RAVEN request_id=%s — no unstructured intents, skipping",
            request.request_id,
        )
        return RAVENResponse(request_id=request.request_id, status="skipped")

    logger.info(
        "RAVEN request_id=%s — processing %d unstructured intent(s)",
        request.request_id, len(rag_intents),
    )

    search_inputs: list[SearchInput] = []
    skipped: list[int] = []

    for intent in rag_intents:
        # Layer 1: domain access check (in-memory, from security_profile)
        if not is_domain_allowed(intent.domain, request.security_profile):
            logger.warning(
                "RAVEN intent_id=%d domain='%s' blocked by Layer 1 — not in security_profile",
                intent.intent_id, intent.domain,
            )
            skipped.append(intent.intent_id)
            continue

        # Extract document filter early — needed for Layer 2 check
        doc_filter = extract_document_filter(intent.unstructured_source)

        # Layer 2: file authorization check (DB — file must exist in authorized domain)
        authorized, reason = check_file_access(doc_filter, intent.domain)
        if not authorized:
            logger.warning(
                "RAVEN intent_id=%d blocked by Layer 2 — %s",
                intent.intent_id, reason,
            )
            skipped.append(intent.intent_id)
            continue

        logger.debug("RAVEN intent_id=%d Layer 2 passed — %s", intent.intent_id, reason)

        # Embed the intent description (natural-language question for this intent)
        try:
            embedding = embedder.embed(intent.description)
        except Exception as e:
            logger.error("RAVEN embed failed intent_id=%d: %s", intent.intent_id, e)
            skipped.append(intent.intent_id)
            continue

        search_inputs.append(SearchInput(
            embedding_id=f"RAG_{intent.intent_id:03d}",
            label=intent.unstructured_source or intent.description,
            content=intent.description,
            embedding=embedding,
            rag_table=RAG_TABLE,
            document_filter=doc_filter,
            top_k=request.top_k,
        ))

        logger.info(
            "RAVEN intent_id=%d embedded dim=%d doc_filter=%s",
            intent.intent_id, len(embedding), doc_filter,
        )

    status = "success" if search_inputs else "skipped"

    return RAVENResponse(
        request_id=request.request_id,
        status=status,
        similarity_search_inputs=search_inputs,
        skipped_intents=skipped,
    )


@app.get("/health")
def health():
    emb = get_embedder()
    return {
        "status":  "ok",
        "agent":   "RAVEN",
        "model":   emb.model_name,
        "dim":     emb.dim,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("raven:app", host="0.0.0.0", port=8006, reload=False)
