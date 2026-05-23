"""
GET /api/health
Checks database, PgVector, and LLM availability.
"""
from fastapi import APIRouter
from services.sql_service import test_connection
from services.llm_service import test_llm

router = APIRouter()


@router.get("/health")
async def health():
    db_result = test_connection()
    llm_result = test_llm()

    all_ok = db_result["status"] == "ok" and llm_result["status"] == "ok"

    return {
        "status": "healthy" if all_ok else "degraded",
        "components": {
            "database": db_result,
            "llm": llm_result,
        },
    }
