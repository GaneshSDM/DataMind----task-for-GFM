# =============================================================================
#   A R I A
# =============================================================================
#
#   "I see your words and decompose your will into atomic truths."
#
#   ARIA — Analytical Reasoning & Intent Analyst
#   Decomposes every natural-language prompt into structured atomic intents,
#   constrained to the user's permitted domain scope.
#
#   Powered by Groq (llama-3.3-70b-versatile) · LangGraph-ready · Port 8002
# =============================================================================

import logging
import sys
import os

# Allow imports from this folder when run as `python aria.py`
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

# Single source of truth — load from central backend .env BEFORE any sub-module
# imports (config.settings reads GROQ_API_KEY at module level via `from config.settings import`)
_BACKEND_ENV = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../backend/.env")
)
load_dotenv(dotenv_path=_BACKEND_ENV)

from core.intent_processor import IntentProcessor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("aria")

# ── models ─────────────────────────────────────────────────

class SecurityProfile(BaseModel):
    user_id: str
    role: str
    security_groups: list[str] = []
    domains: list[dict] = []
    subdomains: list[dict] = []
    geographies: list[dict] = []
    row_level_security: list[dict] = []
    column_level_security: list[dict] = []


class ARIARequest(BaseModel):
    request_id: str
    prompt: str
    security_profile: SecurityProfile
    metadata: dict = {}


class ARIAResponse(BaseModel):
    request_id: str
    status: str          # 'success' | 'error'
    intent_result: Optional[dict] = None
    error: Optional[str] = None


# ── startup ────────────────────────────────────────────────

_processor: Optional[IntentProcessor] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _processor
    logger.info("Initialising IntentProcessor (Groq client)…")
    _processor = IntentProcessor()
    logger.info("ARIA ready")
    yield


app = FastAPI(title="ARIA — Intent Classifier Agent", lifespan=lifespan)


# ── endpoints ──────────────────────────────────────────────

@app.post("/intent/classify", response_model=ARIAResponse)
async def classify(request: ARIARequest):
    sp = request.security_profile

    # Extract allowed domains + subdomains + domain IDs from security profile
    allowed_domains     = [d["name"] for d in sp.domains]    if sp.domains    else []
    allowed_subdomains  = [d["name"] for d in sp.subdomains] if sp.subdomains else []
    allowed_domain_ids  = [d["id"]   for d in sp.domains]    if sp.domains    else []

    logger.info(
        "ARIA classify request_id=%s user=%s domains=%s domain_ids=%s",
        request.request_id, sp.user_id, allowed_domains or "ALL", allowed_domain_ids
    )

    try:
        import asyncio
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: _processor.process(
                request.prompt,
                allowed_domains=allowed_domains or None,
                allowed_subdomains=allowed_subdomains or None,
                allowed_domain_ids=allowed_domain_ids or None,
            )
        )
        return ARIAResponse(
            request_id=request.request_id,
            status="success",
            intent_result=result,
        )
    except Exception as e:
        logger.error("ARIA classification failed: %s", e)
        return ARIAResponse(
            request_id=request.request_id,
            status="error",
            error=str(e),
        )


@app.post("/schema/reload")
async def reload_schema():
    """Hot-reload schema_reference.json without restarting. Run after bootstrap_schema.py."""
    _processor.reload_schema()
    schema = _processor._schema
    if schema:
        return {
            "status": "reloaded",
            "generated_at": schema.get("generated_at"),
            "domains": len(schema.get("domains", [])),
            "subdomains": len(schema.get("subdomains", [])),
            "tables": len(schema.get("tables", [])),
            "rag_files": len(schema.get("rag_files", [])),
        }
    return {"status": "fallback", "message": "schema_reference.json not found — using built-in taxonomy"}


@app.get("/health")
async def health():
    schema = _processor._schema if _processor else None
    return {
        "status": "ok",
        "agent": "ARIA",
        "model": "llama-3.3-70b-versatile",
        "schema_loaded": schema is not None,
        "schema_generated_at": schema.get("generated_at") if schema else None,
        "tables": len(schema.get("tables", [])) if schema else 0,
        "rag_files": len(schema.get("rag_files", [])) if schema else 0,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("aria:app", host="0.0.0.0", port=8002, reload=False)
