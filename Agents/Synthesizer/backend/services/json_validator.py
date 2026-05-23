"""
JSON contract validator.
Checks required fields, SQL safety, and table allow-list.
"""
import re
from typing import Any

# ── SQL safety ─────────────────────────────────────────────────────────────────
FORBIDDEN_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE",
    "CREATE", "GRANT", "REVOKE", "MERGE", "EXECUTE", "EXEC",
    "COPY", "VACUUM", "REINDEX", "CLUSTER", "SECURITY",
    "EXTENSION", "TRIGGER", "PROCEDURE",
}

REQUIRED_TOP_LEVEL = [
    "request_id", "app_context", "persona", "user_query",
    "input_contract", "structured_inputs", "unstructured_inputs",
]

REQUIRED_APP_CONTEXT = ["domain", "objective"]
REQUIRED_INPUT_CONTRACT = ["structured_tables_allowed", "rag_table"]


def _check_sql_safety(query_id: str, sql: str, allowed_tables: list[str]) -> list[str]:
    errors: list[str] = []
    sql_upper = sql.strip().upper()

    # Must start with SELECT or WITH (for CTEs)
    if not (sql_upper.startswith("SELECT") or sql_upper.startswith("WITH")):
        errors.append(f"[{query_id}] Only SELECT statements are allowed.")

    # Forbidden keywords check (word-boundary aware)
    for kw in FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{kw}\b", sql_upper):
            errors.append(f"[{query_id}] Forbidden keyword detected: {kw}")

    # Multiple statements (extra semicolons)
    stripped = sql.strip().rstrip(";")
    if ";" in stripped:
        errors.append(f"[{query_id}] Multiple SQL statements in a single script are not allowed.")

    return errors


def _validate_table_allowlist(query_id: str, source_table: str, allowed: list[str]) -> list[str]:
    errors: list[str] = []
    if source_table and source_table not in allowed:
        errors.append(
            f"[{query_id}] Table '{source_table}' is not in the allowed list: {allowed}"
        )
    return errors


def validate_json_contract(payload: Any) -> dict:
    """
    Returns dict with keys:
      valid   : bool
      errors  : list of blocking error strings
      warnings: list of non-blocking warning strings
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(payload, dict):
        return {"valid": False, "errors": ["Payload must be a JSON object."], "warnings": []}

    # ── Top-level required fields ───────────────────────────────────────────────
    for field in REQUIRED_TOP_LEVEL:
        if field not in payload:
            errors.append(f"Missing required field: '{field}'")

    # ── app_context ─────────────────────────────────────────────────────────────
    app_ctx = payload.get("app_context", {})
    for field in REQUIRED_APP_CONTEXT:
        if field not in app_ctx:
            warnings.append(f"Missing app_context.{field}")

    # ── input_contract ──────────────────────────────────────────────────────────
    contract = payload.get("input_contract", {})
    for field in REQUIRED_INPUT_CONTRACT:
        if field not in contract:
            errors.append(f"Missing input_contract.{field}")

    allowed_tables: list[str] = contract.get("structured_tables_allowed", [])
    rag_table: str = contract.get("rag_table", "")

    # ── SQL scripts ─────────────────────────────────────────────────────────────
    sql_scripts = payload.get("structured_inputs", {}).get("sql_scripts", [])
    if not sql_scripts:
        warnings.append("No SQL scripts found in structured_inputs.sql_scripts")

    for script in sql_scripts:
        qid = script.get("query_id", "UNKNOWN")
        sql = script.get("sql", "")
        source_table = script.get("source_table", "")

        if not sql:
            errors.append(f"[{qid}] SQL script is empty.")
            continue

        errors.extend(_check_sql_safety(qid, sql, allowed_tables))
        if source_table and allowed_tables:
            errors.extend(_validate_table_allowlist(qid, source_table, allowed_tables))

    # ── RAG inputs ──────────────────────────────────────────────────────────────
    rag_inputs = payload.get("unstructured_inputs", {}).get("similarity_search_inputs", [])
    if not rag_inputs:
        warnings.append("No RAG search inputs found in unstructured_inputs.similarity_search_inputs")

    allowed_docs: list[str] = contract.get("allowed_rag_documents_only", [])
    for item in rag_inputs:
        eid = item.get("embedding_id", "UNKNOWN")
        embedding = item.get("embedding", [])
        doc_filter = item.get("document_filter", "")

        if not embedding:
            warnings.append(f"[{eid}] Embedding vector is empty — RAG search may use zero vector.")
        elif not all(isinstance(v, (int, float)) for v in embedding):
            errors.append(f"[{eid}] Embedding contains non-numeric values.")

        if doc_filter and allowed_docs and doc_filter not in allowed_docs:
            errors.append(
                f"[{eid}] document_filter '{doc_filter}' is not in allowed_rag_documents_only."
            )

        item_rag_table = item.get("rag_table", rag_table)
        if not item_rag_table:
            errors.append(f"[{eid}] No rag_table specified.")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }
