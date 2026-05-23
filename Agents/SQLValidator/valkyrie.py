# =============================================================================
#   V A L K Y R I E
# =============================================================================
#
#   "I stand between creation and execution, judging every query that seeks passage."
#
#   VALKYRIE — Validation and Logical Knowledge Yielding Rigorous Intelligent Execution
#   Validates generated SQL against pipeline security_profile (RLS/CLS) and
#   syntax/date constraints. Returns violations + suggested corrections.
#
#   Port 8004  ·  POST /sql/validate  ·  GET /health
# =============================================================================

import logging
import sys
import os
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv

# Single source of truth — load from central backend .env
_BACKEND_ENV = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../backend/.env")
)
load_dotenv(dotenv_path=_BACKEND_ENV)

# Import lightweight SQL utility functions from existing validator
from sql_validator import (
    _check_syntax,
    _extract_columns_from_select,
    _normalize_column_name,
    _find_date_comparisons,
)
from groq_client import GroqClient, get_query_fingerprint

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("valkyrie")

_GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
_GROQ_MODEL   = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

_groq_client: Optional[GroqClient] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _groq_client
    if _GROQ_API_KEY:
        _groq_client = GroqClient(api_key=_GROQ_API_KEY, model=_GROQ_MODEL)
        logger.info("VALKYRIE ready — Groq enabled (model=%s)", _GROQ_MODEL)
    else:
        logger.warning("VALKYRIE ready — GROQ_API_KEY not set, LLM checks disabled")
    yield


app = FastAPI(title="VALKYRIE — SQL Validator Agent", lifespan=lifespan)


# ── Models ─────────────────────────────────────────────────────────────────────

class SecurityProfile(BaseModel):
    user_id: str
    role: str
    domains: list = []
    subdomains: list = []
    row_level_security: list = []
    column_level_security: list = []


class SQLResultItem(BaseModel):
    intent_id: int
    status: str                             # success | error | skipped
    generated_sql: Optional[str] = None
    rls_applied: Optional[dict] = None
    cls_applied: Optional[dict] = None
    tables_in_scope: list = []
    model_used: Optional[str] = None
    error: Optional[str] = None


class IntentItem(BaseModel):
    intent_id: int
    description: str
    domain: str
    sub_domain: Optional[str] = None
    data_source: str
    structured_table: Optional[str] = None
    relevant_columns: list = []
    retrieved_context: list = []


class VALKYRIERequest(BaseModel):
    request_id: str
    prompt: str
    security_profile: SecurityProfile
    intents: list[IntentItem] = []
    sql_results: list[SQLResultItem] = []


class ValidatedResult(BaseModel):
    intent_id: int
    sql: Optional[str]
    status: str                             # pass | fail | warn | skipped | error
    violations: list = []
    corrections_suggested: list = []
    fingerprint: Optional[str] = None


class VALKYRIEResponse(BaseModel):
    request_id: str
    status: str                             # pass | partial | fail
    validated_results: list[ValidatedResult] = []
    synthesizer_context: Optional[dict] = None
    error: Optional[str] = None


# ── Validation helpers ─────────────────────────────────────────────────────────

def _extract_where_clause(sql: str) -> str:
    """Extract WHERE clause content from SQL (stops at GROUP BY / ORDER BY / HAVING / LIMIT)."""
    m = re.search(
        r"\bWHERE\b(.+?)(?:\bGROUP\s+BY\b|\bORDER\s+BY\b|\bHAVING\b|\bLIMIT\b|;|$)",
        sql, re.IGNORECASE | re.DOTALL,
    )
    return m.group(1).strip() if m else ""


def _filter_present_in_sql(filter_expr: str, sql: str) -> bool:
    """
    Check that the RLS filter expression appears in the SQL.
    Uses normalised substring match (lowercase, collapsed whitespace).
    """
    if not filter_expr:
        return True  # nothing required
    norm_filter = re.sub(r"\s+", " ", filter_expr.lower().strip())
    norm_sql    = re.sub(r"\s+", " ", sql.lower())
    return norm_filter in norm_sql


def _restricted_columns_for_table(cls_list: list, target_table: str) -> set:
    """Return column names where can_read=False for the given table."""
    bare = target_table.split(".")[-1].lower()
    restricted = set()
    for entry in cls_list:
        if entry.get("table", "").split(".")[-1].lower() != bare:
            continue
        for col in entry.get("columns", []):
            if not col.get("can_read", True):
                restricted.add(col["column"].lower())
    return restricted


def _rls_policies_for_table(rls_list: list, target_table: str) -> list:
    """Return RLS policies that apply to the given table."""
    bare = target_table.split(".")[-1].lower()
    return [r for r in rls_list if r.get("table", "").split(".")[-1].lower() == bare]


def _validate_one(
    sql_result: dict,
    intent: Optional[dict],
    security_profile: dict,
    groq_client: Optional[GroqClient] = None,
) -> dict:
    """
    Validate one SAGE SQL result against pipeline security_profile.

    Returns dict with: intent_id, sql, status, violations, corrections_suggested, fingerprint.
    """
    intent_id = sql_result.get("intent_id", 0)
    status    = sql_result.get("status", "skipped")
    sql       = sql_result.get("generated_sql") or ""

    # Pass-through for non-SQL results
    if status in ("skipped", "error") or not sql:
        return {
            "intent_id":             intent_id,
            "sql":                   sql,
            "status":                status,
            "violations":            [],
            "corrections_suggested": [],
            "fingerprint":           None,
        }

    violations:            list[dict] = []
    corrections_suggested: list[str]  = []

    target_table = (intent or {}).get("structured_table") or ""
    rls_list     = security_profile.get("row_level_security", [])
    cls_list     = security_profile.get("column_level_security", [])

    # ── 1. Syntax check ──────────────────────────────────────────────────────
    for se in _check_syntax(sql):
        if se.get("type") != "WARNING":
            violations.append(se)
            corrections_suggested.append(se.get("fix", ""))

    # ── 2. CLS — restricted columns must not appear in SELECT ────────────────
    if target_table:
        restricted_cols = _restricted_columns_for_table(cls_list, target_table)
    else:
        # No table hint — union all restricted columns across policies
        restricted_cols = set()
        for entry in cls_list:
            for col in entry.get("columns", []):
                if not col.get("can_read", True):
                    restricted_cols.add(col["column"].lower())

    if restricted_cols:
        raw_cols    = _extract_columns_from_select(sql)
        norm_cols   = [_normalize_column_name(c).lower() for c in raw_cols]
        for col in norm_cols:
            if col and col not in ("*", "1", "") and "(" not in col and col in restricted_cols:
                violations.append({
                    "type":   "CLS",
                    "detail": f"Column '{col}' is restricted by Column-Level Security policy",
                    "fix":    f"Remove '{col}' from SELECT",
                })
                corrections_suggested.append(f"Remove restricted column '{col}' from SELECT")

    # ── 3. RLS — required filter expression must appear in WHERE clause ───────
    if target_table:
        for policy in _rls_policies_for_table(rls_list, target_table):
            filter_expr = policy.get("filter", "").strip()
            if filter_expr and not _filter_present_in_sql(filter_expr, sql):
                violations.append({
                    "type":   "RLS",
                    "detail": f"RLS filter not enforced: {filter_expr}",
                    "fix":    f"Add WHERE condition: {filter_expr}",
                })
                corrections_suggested.append(f"Ensure WHERE clause includes: {filter_expr}")

    # ── 4. Groq LLM semantic check ────────────────────────────────────────────
    if groq_client:
        try:
            domain    = (intent or {}).get("domain", "")
            subdomain = (intent or {}).get("sub_domain", "")

            # Allowed columns = those with can_read=True for the table
            allowed_for_groq = []
            if cls_list and target_table:
                bare = target_table.split(".")[-1].lower()
                for entry in cls_list:
                    if entry.get("table", "").split(".")[-1].lower() == bare:
                        for col in entry.get("columns", []):
                            if col.get("can_read", True):
                                allowed_for_groq.append(col["column"])

            rls_predicates = [
                p["filter"] for p in (
                    _rls_policies_for_table(rls_list, target_table) if target_table else rls_list
                )
                if p.get("filter")
            ]

            schema_ctx = {
                "allowed_columns":    allowed_for_groq,
                "rls_predicates":     rls_predicates,
                "restricted_columns": list(restricted_cols),
                "domain":             domain,
                "subdomain":          subdomain,
            }
            user_info = {
                "user_id":   security_profile.get("user_id", ""),
                "role":      security_profile.get("role", ""),
                "tenant_id": "default",
            }

            groq_result      = groq_client.validate_permissions(sql, user_info, schema_ctx)
            existing_details = {v["detail"] for v in violations}

            for bc in groq_result.get("blocked_columns", []):
                detail = f"LLM: blocked column '{bc}'"
                if detail not in existing_details:
                    violations.append({"type": "CLS (LLM)", "detail": detail, "fix": f"Remove '{bc}' from SELECT"})
                    corrections_suggested.append(f"Remove '{bc}' from SELECT")
                    existing_details.add(detail)

            for mf in groq_result.get("missing_filters", []):
                detail = f"LLM: missing RLS filter: {mf}"
                if detail not in existing_details:
                    violations.append({"type": "RLS (LLM)", "detail": detail, "fix": f"Add WHERE clause: {mf}"})
                    corrections_suggested.append(f"Add WHERE clause: {mf}")
                    existing_details.add(detail)

        except Exception as e:
            logger.warning("Groq check skipped intent_id=%d: %s", intent_id, e)

    # ── 5. Verdict ────────────────────────────────────────────────────────────
    hard = [v for v in violations if v.get("type") not in ("WARNING",)]
    val_status = "fail" if hard else ("warn" if violations else "pass")

    return {
        "intent_id":             intent_id,
        "sql":                   sql,
        "status":                val_status,
        "violations":            violations,
        "corrections_suggested": corrections_suggested,
        "fingerprint":           get_query_fingerprint(sql),
    }


# ── Endpoint ───────────────────────────────────────────────────────────────────

@app.post("/sql/validate", response_model=VALKYRIEResponse)
async def validate(request: VALKYRIERequest):
    import asyncio

    sp         = request.security_profile.model_dump()
    intent_map = {i.intent_id: i.model_dump() for i in request.intents}

    logger.info(
        "VALKYRIE validate request_id=%s intents=%d sql_results=%d",
        request.request_id, len(request.intents), len(request.sql_results),
    )

    loop      = asyncio.get_running_loop()
    validated = []
    for sql_res in request.sql_results:
        intent = intent_map.get(sql_res.intent_id)
        result = await loop.run_in_executor(
            None,
            lambda s=sql_res.model_dump(), i=intent: _validate_one(s, i, sp, _groq_client),
        )
        logger.info(
            "VALKYRIE intent %d → %s (%d violation(s))",
            result["intent_id"], result["status"], len(result["violations"]),
        )
        validated.append(result)

    # Overall status
    active = [r["status"] for r in validated if r["status"] not in ("skipped", "error")]
    if not active:
        overall = "pass"
    elif all(s == "pass" for s in active):
        overall = "pass"
    elif all(s == "fail" for s in active):
        overall = "fail"
    else:
        overall = "partial"

    # Build synthesizer context (packaged for next agent)
    sql_result_map = {r.intent_id: r for r in request.sql_results}
    retrieved_context = [
        chunk
        for intent in request.intents
        for chunk in (intent.retrieved_context or [])
    ]

    validated_sql_results = []
    for v in validated:
        sql_r = sql_result_map.get(v["intent_id"])
        validated_sql_results.append({
            "intent_id":         v["intent_id"],
            "sql":               v["sql"],
            "validation_status": v["status"],
            "violations":        v["violations"],
            "fingerprint":       v["fingerprint"],
            "rls_applied":       sql_r.rls_applied   if sql_r else None,
            "cls_applied":       sql_r.cls_applied    if sql_r else None,
            "tables_in_scope":   sql_r.tables_in_scope if sql_r else [],
            "model_used":        sql_r.model_used     if sql_r else None,
        })

    synthesizer_context = {
        "request_id":          request.request_id,
        "prompt":              request.prompt,
        "security_profile":    sp,
        "intents":             [i.model_dump() for i in request.intents],
        "validated_sql_results": validated_sql_results,
        "retrieved_context":   retrieved_context,
    }

    return VALKYRIEResponse(
        request_id=request.request_id,
        status=overall,
        validated_results=[ValidatedResult(**v) for v in validated],
        synthesizer_context=synthesizer_context,
    )


@app.get("/health")
async def health():
    return {
        "status":      "ok",
        "agent":       "VALKYRIE",
        "groq_enabled": _groq_client is not None,
        "model":       _GROQ_MODEL if _groq_client else None,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("valkyrie:app", host="0.0.0.0", port=8004, reload=False)
