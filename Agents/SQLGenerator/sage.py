# =============================================================================
#   S A G E
# =============================================================================
#
#   SQL Analysis & Generation Engine
#   Receives pipeline payload from orchestrator, generates PostgreSQL per intent.
#
#   Port 8003  ·  POST /sql/generate  ·  GET /health
# =============================================================================

import logging
import sys
import os

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

# Resolve SCHEMA_FILE_PATH to absolute path before sql_agent imports it at module level
_ARIA_SCHEMA = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "../IntentClassifier/schema_reference.json")
)
os.environ.setdefault("SCHEMA_FILE_PATH", _ARIA_SCHEMA)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("sage")

# Lazy imports — heavy models load once at startup
from sql_agent import (
    get_provider,
    load_schema_reference,
    load_examples,
    resolve_tables,
    generate_sql,
    build_output,
    run_correction,
)


# ── schema format adapter ──────────────────────────────────────────────────────

def _normalize_schema(schema: dict) -> dict:
    """
    Convert ARIA flat schema → SAGE catalog format if needed.

    ARIA format (bootstrap_schema.py output):
      {"domains": [...], "subdomains": [...], "tables": [...], "rag_files": [...]}

    SAGE format (sync_schema.py output):
      {"catalog": [{"domain": "...", "sub_domains": [{"name": "...", "tables": [...]}]}]}

    Strategy: put all tables under every domain as a single sub_domain bucket.
    resolve_tables() filters by table_name anyway, so domain bucket is just structure.
    Also normalises column key "schema" → "schema_name".
    """
    if "catalog" in schema:
        return schema  # already SAGE format

    domains = schema.get("domains", [])
    raw_tables = schema.get("tables", [])
    target_schema = schema.get("target_schema", "sales")

    # Normalise table entries: ARIA uses "schema", SAGE uses "schema_name"
    norm_tables = []
    for t in raw_tables:
        norm_tables.append({
            "table_name":  t["table_name"],
            "schema_name": t.get("schema") or t.get("schema_name", target_schema),
            "columns":     t.get("columns", []),
            "tags":        t.get("tags", []),
            "description": t.get("description", ""),
        })

    # Group tables by domain (new multi-domain schema_reference format).
    # Tables without a domain field fall back to all-domains behaviour (legacy).
    has_domain_tagged = any(t.get("domain") for t in norm_tables)

    if has_domain_tagged:
        from collections import defaultdict as _defaultdict
        domain_tables_map: dict = _defaultdict(list)
        for t in norm_tables:
            d_name = t.get("domain") or target_schema
            domain_tables_map[d_name].append(t)

        catalog = [
            {
                "domain": d["name"],
                "sub_domains": [{"name": "default", "tables": domain_tables_map.get(d["name"], [])}],
            }
            for d in domains
        ]
        # Fallback entry for untagged tables bucket
        if domain_tables_map.get(target_schema) and not any(
            d["name"] == target_schema for d in domains
        ):
            catalog.append({
                "domain": target_schema,
                "sub_domains": [{"name": "default", "tables": domain_tables_map[target_schema]}],
            })
    else:
        # Legacy: all tables visible under every domain
        catalog = [
            {
                "domain": d["name"],
                "sub_domains": [{"name": "default", "tables": norm_tables}],
            }
            for d in domains
        ]

    # If no domains defined, create a fallback entry so tables are still reachable
    if not catalog and norm_tables:
        catalog = [{"domain": target_schema, "sub_domains": [{"name": "default", "tables": norm_tables}]}]

    logger.info(
        "Schema normalised (ARIA→SAGE): %d domains, %d tables",
        len(catalog), len(norm_tables),
    )
    return {**schema, "catalog": catalog}


# ── startup ────────────────────────────────────────────────────────────────────

_provider = None
_model    = None
_client   = None
_schema   = None
_examples = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _provider, _model, _client, _schema, _examples
    logger.info("SAGE startup — loading provider and schema…")
    _provider, _model, _client = get_provider()
    _schema   = _normalize_schema(load_schema_reference())
    _examples = load_examples()
    table_count = sum(
        len(sd["tables"])
        for cat in _schema.get("catalog", [])
        for sd in cat.get("sub_domains", [])
    )
    logger.info("SAGE ready — provider=%s model=%s tables=%d", _provider, _model, table_count)
    yield


app = FastAPI(title="SAGE — SQL Analysis & Generation Engine", lifespan=lifespan)


# ── models ─────────────────────────────────────────────────────────────────────

class IntentItem(BaseModel):
    intent_id: int
    description: str
    domain: str
    sub_domain: Optional[str] = None
    data_source: str                        # Structured | Unstructured | Both
    structured_table: Optional[str] = None
    relevant_columns: list[str] = []


class SecurityProfile(BaseModel):
    user_id: str
    role: str
    row_level_security: list[dict] = []
    column_level_security: list[dict] = []


class SAGERequest(BaseModel):
    request_id: str
    prompt: str
    security_profile: SecurityProfile
    intents: list[IntentItem]
    metadata: dict = {}


class SQLResult(BaseModel):
    intent_id: int
    status: str                             # success | error | skipped
    generated_sql: Optional[str] = None
    rls_applied: Optional[dict] = None
    cls_applied: Optional[dict] = None
    tables_in_scope: list[str] = []
    model_used: Optional[str] = None
    error: Optional[str] = None


class SAGEResponse(BaseModel):
    request_id: str
    status: str                             # success | partial | error
    sql_results: list[SQLResult]
    error: Optional[str] = None


class CorrectionRequest(BaseModel):
    """Request to re-generate SQL for a single failed intent."""
    request_id: str
    intent_id: int
    generated_sql: str
    validation_errors: list[dict] = []
    corrections_suggested: list[str] = []
    original_prompt: str
    domain: str
    sub_domain: Optional[str] = None
    tables: list[str] = []
    rls_applied: Optional[dict] = None
    cls_applied: Optional[dict] = None
    model_used: Optional[str] = None


class CorrectionResponse(BaseModel):
    request_id: str
    intent_id: int
    status: str                             # corrected | error
    corrected_sql: Optional[str] = None
    error: Optional[str] = None


# ── security adapters ──────────────────────────────────────────────────────────

def _adapt_rls(rls_list: list[dict], target_table: str) -> dict:
    """
    Pipeline RLS format:
      [{"name": "...", "table": "fact_orders", "filter": "country IN ('India')"}]
    SAGE format:
      {"enabled": True, "policy_name": "...", "expression": "country IN ('India')"}
    """
    # table may be schema-qualified — match on bare name
    bare = target_table.split(".")[-1].lower()
    matching = [r for r in rls_list if r.get("table", "").split(".")[-1].lower() == bare]
    if not matching:
        return {"enabled": False, "filters": [], "policy_name": None}
    policy = matching[0]
    expr   = policy.get("filter", "").strip()
    return {
        "enabled":     bool(expr),
        "policy_name": policy.get("name"),
        "expression":  expr or None,
        "filters":     [],
    }


def _adapt_cls(cls_list: list[dict], target_table: str) -> dict:
    """
    Pipeline CLS format:
      [{"name": "...", "table": "fact_orders",
        "columns": [{"column": "profit_usd", "can_read": false, ...}]}]
    SAGE format:
      {"enabled": True, "policy_name": "...", "restricted_columns": ["profit_usd"]}
    """
    bare = target_table.split(".")[-1].lower()
    restricted  = []
    policy_name = None
    for cls in cls_list:
        if cls.get("table", "").split(".")[-1].lower() != bare:
            continue
        policy_name = cls.get("name")
        for col in cls.get("columns", []):
            if not col.get("can_read", True):
                restricted.append(col["column"])
    return {
        "enabled":            bool(restricted),
        "policy_name":        policy_name,
        "restricted_columns": restricted,
    }


# ── endpoint ───────────────────────────────────────────────────────────────────

@app.post("/sql/generate", response_model=SAGEResponse)
async def generate(request: SAGERequest):
    import asyncio
    sp = request.security_profile

    # Only Structured / Both intents produce SQL
    structured = [i for i in request.intents if i.data_source in ("Structured", "Both")]

    if not structured:
        logger.info("SAGE %s — no structured intents, skipping", request.request_id)
        skipped = [
            SQLResult(intent_id=i.intent_id, status="skipped")
            for i in request.intents
        ]
        return SAGEResponse(
            request_id=request.request_id,
            status="success",
            sql_results=skipped,
        )

    sql_results: list[SQLResult] = []

    for intent in request.intents:
        if intent.data_source not in ("Structured", "Both"):
            sql_results.append(SQLResult(intent_id=intent.intent_id, status="skipped"))
            continue

        table_name = intent.structured_table
        if not table_name:
            sql_results.append(SQLResult(
                intent_id=intent.intent_id,
                status="error",
                error="No structured_table specified in intent",
            ))
            continue

        # Build per-intent SAGE input
        rls_cfg = _adapt_rls(sp.row_level_security, table_name)
        cls_cfg = _adapt_cls(sp.column_level_security, table_name)

        agent_payload = {
            "request_id":             f"{request.request_id}_i{intent.intent_id}",
            "prompt":                 intent.description,   # intent description → SQL
            "domain":                 intent.domain,
            "sub_domain":             intent.sub_domain or "",
            "tables":                 [table_name],
            "row_level_security":     rls_cfg,
            "column_level_security":  cls_cfg,
        }

        try:
            loop = asyncio.get_running_loop()
            output = await loop.run_in_executor(
                None,
                lambda p=agent_payload: _generate_one(p)
            )
            sql_results.append(SQLResult(
                intent_id=intent.intent_id,
                status="success",
                generated_sql=output["generated_sql"],
                rls_applied=output["rls_applied"],
                cls_applied=output["cls_applied"],
                tables_in_scope=output["metadata"]["tables_in_scope"],
                model_used=output["metadata"]["model_used"],
            ))
            logger.info("SAGE intent %d → SQL generated (%d chars)",
                        intent.intent_id, len(output["generated_sql"]))
        except Exception as e:
            logger.error("SAGE intent %d failed: %s", intent.intent_id, e)
            sql_results.append(SQLResult(
                intent_id=intent.intent_id,
                status="error",
                error=str(e),
            ))

    any_success = any(r.status == "success" for r in sql_results)
    any_error   = any(r.status == "error"   for r in sql_results)
    overall = "success" if any_success and not any_error else (
              "partial" if any_success else "error")

    return SAGEResponse(
        request_id=request.request_id,
        status=overall,
        sql_results=sql_results,
    )


@app.post("/sql/correct", response_model=CorrectionResponse)
async def correct(request: CorrectionRequest):
    """
    Re-generate SQL for a single failed intent using VALKYRIE violation feedback.
    Called by valkyrie_node during the correction loop (max 2 attempts).
    """
    import asyncio

    # Assemble correction_input in the format run_correction() expects
    rls_applied = request.rls_applied or {}
    cls_applied = request.cls_applied or {}

    correction_input = {
        "request_id":    request.request_id,
        "generated_sql": request.generated_sql,
        "validation_errors": [
            {"type": e.get("type", ""), "detail": e.get("detail", ""), "fix": e.get("fix", "")}
            for e in request.validation_errors
        ],
        "suggested_corrections": request.corrections_suggested,
        "validation_hints": {
            "original_prompt": request.original_prompt,
            "expected_tables": request.tables,
        },
        "metadata": {
            "domain":     request.domain,
            "sub_domain": request.sub_domain or "",
            "model_used": request.model_used or _model or "",
        },
        # Preserve RLS — include expression so build_rls_where uses it in correction prompt
        "rls_applied": {
            "enabled":             rls_applied.get("enabled", False),
            "policy_name":         rls_applied.get("policy_name"),
            "expression":          rls_applied.get("where_clause_injected") or rls_applied.get("expression"),
            "where_clause_injected": rls_applied.get("where_clause_injected"),
            "filters_applied":     rls_applied.get("filters_applied", []),
        },
        "cls_applied": {
            "enabled":          cls_applied.get("enabled", False),
            "policy_name":      cls_applied.get("policy_name"),
            "columns_excluded": cls_applied.get("columns_excluded", []),
        },
    }

    logger.info(
        "SAGE correction request_id=%s intent_id=%d errors=%d",
        request.request_id, request.intent_id, len(request.validation_errors),
    )

    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda ci=correction_input: run_correction(ci, _schema, _examples),
        )
        corrected_sql = result.get("corrected_sql")
        logger.info(
            "SAGE corrected intent_id=%d → %d chars",
            request.intent_id, len(corrected_sql) if corrected_sql else 0,
        )
        return CorrectionResponse(
            request_id=request.request_id,
            intent_id=request.intent_id,
            status="corrected",
            corrected_sql=corrected_sql,
        )
    except Exception as e:
        logger.error("SAGE correction failed intent_id=%d: %s", request.intent_id, e)
        return CorrectionResponse(
            request_id=request.request_id,
            intent_id=request.intent_id,
            status="error",
            error=str(e),
        )


def _generate_one(agent_payload: dict) -> dict:
    """Synchronous generation for a single intent. Runs in executor."""
    resolved = resolve_tables(_schema, agent_payload["domain"], agent_payload["tables"])
    if not resolved:
        raise ValueError(
            f"Table '{agent_payload['tables']}' not found in schema_reference "
            f"for domain '{agent_payload['domain']}'"
        )
    sql, excluded_cols, rls_where, rls_cfg, cls_cfg = generate_sql(
        _provider, _client, _model, agent_payload, resolved, _examples
    )
    return build_output(agent_payload, resolved, sql, excluded_cols, rls_where, rls_cfg, cls_cfg, _model)


# ── schema reload ──────────────────────────────────────────────────────────────

@app.post("/schema/reload")
async def reload_schema():
    """Hot-reload schema_reference.json without restart. Call after bootstrap_schema.py runs."""
    global _schema
    try:
        _schema = _normalize_schema(load_schema_reference())
        table_count = sum(
            len(sd["tables"])
            for cat in _schema.get("catalog", [])
            for sd in cat.get("sub_domains", [])
        )
        logger.info("SAGE schema reloaded — %d tables", table_count)
        return {"status": "reloaded", "tables": table_count}
    except Exception as e:
        logger.error("SAGE schema reload failed: %s", e)
        return {"status": "error", "detail": str(e)}


# ── health ─────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    table_count = sum(
        len(sd["tables"])
        for cat in (_schema.get("catalog", []) if _schema else [])
        for sd in cat.get("sub_domains", [])
    ) if _schema else 0
    return {
        "status":        "ok",
        "agent":         "SAGE",
        "provider":      _provider,
        "model":         _model,
        "schema_loaded": _schema is not None,
        "tables":        table_count,
        "examples":      len(_examples) if _examples else 0,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("sage:app", host="0.0.0.0", port=8003, reload=False)
