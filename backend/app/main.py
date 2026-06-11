from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db.session import engine, Base, SessionLocal
from app.models.user import PromptPolicy

# Import all models so they register with Base
import app.models.user      # noqa
import app.models.rag_models # noqa

from app.api.routes.auth import router as auth_router
from app.api.routes.users import router as users_router
from app.api.routes.geo_domain import geo_router, domain_router, subdomain_router
from app.api.routes.security import sg_router, rls_router, cls_router
from app.api.routes.guardrails import router as guardrails_router
from app.api.routes.chat import router as chat_router
from app.api.routes.config import slm_router, db_router
from app.api.routes.rag import router as rag_router
from app.api.routes.agents import router as agents_router
from app.api.routes.reports import router as reports_router
from app.api.routes.dataflow import router as dataflow_router

app = FastAPI(title="SLM Application API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create tables on startup (use alembic migrations in production)
Base.metadata.create_all(bind=engine)

# Cache for guardrails
app.state.guardrails = []

@app.on_event("startup")
async def startup():
    # Load guardrails cache
    try:
        db = SessionLocal()
        try:
            app.state.guardrails = db.query(PromptPolicy).filter(
                PromptPolicy.is_active == True
            ).order_by(PromptPolicy.priority).all()
        finally:
            db.close()
    except Exception as e:
        print(f"Guardrails cache load failed (non-fatal): {e}")

    # Pre-warm embedding model in background (non-blocking)
    import asyncio
    from app.rag.embedder import warmup
    loop = asyncio.get_event_loop()
    loop.create_task(_background_warmup(loop, warmup))

async def _background_warmup(loop, warmup_fn):
    """Run warmup in executor without blocking startup."""
    try:
        await loop.run_in_executor(None, warmup_fn)
    except Exception as e:
        print(f"Embedder warmup failed (non-fatal): {e}")

app.include_router(auth_router,       prefix="/api/auth",            tags=["Auth"])
app.include_router(users_router,      prefix="/api/users",           tags=["Users"])
app.include_router(geo_router,        prefix="/api/geographies",     tags=["Geography"])
app.include_router(domain_router,     prefix="/api/domains",         tags=["Domains"])
app.include_router(subdomain_router,  prefix="/api/subdomains",      tags=["SubDomains"])
app.include_router(sg_router,         prefix="/api/security-groups", tags=["Security Groups"])
app.include_router(rls_router,        prefix="/api/rls",             tags=["RLS"])
app.include_router(cls_router,        prefix="/api/cls",             tags=["CLS"])
app.include_router(guardrails_router, prefix="/api/guardrails",      tags=["Guardrails"])
app.include_router(chat_router,       prefix="/api/chats",           tags=["Chat"])
app.include_router(slm_router,        prefix="/api/slm-config",      tags=["SLM Config"])
app.include_router(db_router,         prefix="/api/db-connections",  tags=["DB Connections"])
app.include_router(rag_router,        prefix="/api/rag",             tags=["RAG"])
app.include_router(agents_router,     prefix="/api/agents",          tags=["Agents"])
app.include_router(reports_router,    prefix="/api/reports",         tags=["Reports"])
app.include_router(dataflow_router,   prefix="/api/dataflow",         tags=["DataFlow"])


@app.get("/")
def root():
    return {"message": "SLM Application API", "docs": "/docs"}
