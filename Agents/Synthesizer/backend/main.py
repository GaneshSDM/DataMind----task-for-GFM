"""
Universal Synthesizer Agent App (SPYDER) — FastAPI entry point.
Serves the static frontend AND the /api/* endpoints.

Run:
    cd Agents/Synthesizer/backend
    uvicorn main:app --host 0.0.0.0 --port 8005 --reload
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Single source of truth — load from central backend .env before config is imported
_BACKEND_ENV = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../backend/.env")
)
load_dotenv(dotenv_path=_BACKEND_ENV)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from routes import health, validate, synthesize, submit
# generate_json route excluded — uses Google AI (not needed for MANTHAN.AI integration)

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Universal Synthesizer Agent App",
    description="Domain-agnostic synthesis platform — SQL + RAG + LLM",
    version="1.0.0",
)

# ── CORS (allows the upstream agent to POST /api/submit-json) ──────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API routes ─────────────────────────────────────────────────────────────────
app.include_router(health.router,     prefix="/api", tags=["Health"])
app.include_router(validate.router,   prefix="/api", tags=["Validate"])
app.include_router(synthesize.router, prefix="/api", tags=["Synthesize"])
app.include_router(submit.router,     prefix="/api", tags=["Submit"])

# ── Static frontend ────────────────────────────────────────────────────────────
STATIC_DIR = Path(__file__).parent / "static"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
async def root():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str):
    """Catch-all so browser refreshes on deep paths still load the SPA."""
    return FileResponse(str(STATIC_DIR / "index.html"))
