"""
sql_correct_node.py
-------------------
LangGraph node: correct failed SQL intents via SAGE /sql/correct.

Reads failed intents from valkyrie_result in state.
For each failed intent: calls SAGE /sql/correct with violations + context.
Updates sql_result.sql_results with corrected SQLs.
Increments correction_attempt.
Appends audit record to correction_history.
"""

import logging
import httpx

from app.agents.http_clients import get_sage_client

logger = logging.getLogger("sql_correct_node")


async def sql_correct_node(state: dict) -> dict:
    valkyrie_result  = state.get("valkyrie_result", {})
    sql_result       = state.get("sql_result", {})
    intent_result    = state.get("intent_result", {})
    request_id       = state.get("metadata", {}).get("request_id", "")
    attempt          = state.get("correction_attempt", 0) + 1
    history          = list(state.get("correction_history", []))

    validated_results = valkyrie_result.get("validated_results", [])
    failed = [r for r in validated_results if r.get("status") == "fail"]

    if not failed:
        # Nothing to correct — shouldn't reach here but guard anyway
        return {"correction_attempt": attempt, "correction_history": history}

    sql_results  = sql_result.get("sql_results", [])
    intents      = intent_result.get("intents", [])
    intent_map   = {i["intent_id"]: i for i in intents}
    sql_map      = {r["intent_id"]: r for r in sql_results}

    logger.info(
        "SAGE correction attempt=%d request_id=%s failed_intents=%s",
        attempt, request_id, [f["intent_id"] for f in failed],
    )

    corrected_sqls = []   # audit: what was corrected this round
    updated_sql_results = list(sql_results)  # copy to mutate

    client = get_sage_client()
    for failed_result in failed:
        intent_id = failed_result["intent_id"]
        intent    = intent_map.get(intent_id, {})
        original  = sql_map.get(intent_id, {})

        # For Both intents: override original_prompt to prevent JOIN hallucination on retry
        data_source     = intent.get("data_source", "Structured")
        relevant_cols   = intent.get("relevant_columns", [])
        table_name      = intent.get("structured_table", "")
        if data_source == "Both":
            cols_hint = ", ".join(relevant_cols) if relevant_cols else "all columns"
            original_prompt = (
                f"Fetch raw data from {table_name}: select {cols_hint}. "
                "Return all rows without filtering, aggregation, or derived columns."
            )
        else:
            original_prompt = intent.get("description", "")

        payload = {
            "request_id":            f"{request_id}_corr{attempt}_i{intent_id}",
            "intent_id":             intent_id,
            "generated_sql":         failed_result.get("sql", ""),
            "validation_errors":     failed_result.get("violations", []),
            "corrections_suggested": failed_result.get("corrections_suggested", []),
            "original_prompt":       original_prompt,
            "domain":                intent.get("domain", ""),
            "sub_domain":            intent.get("sub_domain"),
            "tables":                [table_name] if table_name else [],
            "data_source":           data_source,
            "relevant_columns":      relevant_cols,
            "rls_applied":           original.get("rls_applied"),
            "cls_applied":           original.get("cls_applied"),
            "model_used":            original.get("model_used"),
        }

        try:
            resp = await client.post("/sql/correct", json=payload)
            resp.raise_for_status()
            data          = resp.json()
            corrected_sql = data.get("corrected_sql")

            if corrected_sql:
                updated_sql_results = [
                    {**r, "generated_sql": corrected_sql, "status": "success"}
                    if r.get("intent_id") == intent_id else r
                    for r in updated_sql_results
                ]
                corrected_sqls.append({
                    "intent_id":     intent_id,
                    "original_sql":  failed_result.get("sql", ""),
                    "corrected_sql": corrected_sql,
                    "violations":    failed_result.get("violations", []),
                })
                logger.info(
                    "SAGE corrected intent_id=%d attempt=%d (%d chars)",
                    intent_id, attempt, len(corrected_sql),
                )
            else:
                logger.warning("SAGE returned no corrected_sql intent_id=%d", intent_id)

        except Exception as e:
            logger.error(
                "SAGE correction failed intent_id=%d attempt=%d: %s",
                intent_id, attempt, e,
            )

    # Append audit record
    history.append({
        "attempt":        attempt,
        "failed_intents": [f["intent_id"] for f in failed],
        "corrections":    corrected_sqls,
    })

    # Rebuild sql_result with corrected SQLs
    updated_sql_result = {**sql_result, "sql_results": updated_sql_results}

    logger.info(
        "Correction attempt=%d done. corrected=%d/%d",
        attempt, len(corrected_sqls), len(failed),
    )

    return {
        "sql_result":         updated_sql_result,
        "correction_attempt": attempt,
        "correction_history": history,
    }
