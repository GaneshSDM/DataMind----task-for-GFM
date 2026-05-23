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

    # One catalog entry per domain, all tables in a single sub_domain bucket
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
