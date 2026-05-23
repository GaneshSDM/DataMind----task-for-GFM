"""
sql_node.py
-----------
LangGraph node — calls SAGE (SQL generator) microservice on :8003.

Only runs for intents with data_source in (Structured, Both).
Sets sql_status, sql_result, sql_error on state.
"""

import logging
import httpx

logger = logging.getLogger("orchestrator.sql_node")

SAGE_URL     = "http://localhost:8003/sql/generate"
SAGE_TIMEOUT = 60.0   # LLM call can take a few seconds


async def sql_node(state: dict) -> dict:
    intent_result    = state.get("intent_result") or {}
    security_profile = state.get("security_profile") or {}
    metadata         = state.get("metadata") or {}
    request_id       = metadata.get("request_id", "unknown")

    intents = intent_result.get("intents", [])

    # Nothing to do — no intents or all unstructured
    structured = [i for i in intents if i.get("data_source") in ("Structured", "Both")]
    if not structured:
        logger.info("sql_node: no structured intents for %s — skip SAGE", request_id)
        return {"sql_status": "skipped", "sql_result": None, "sql_error": None}

    # Build SAGE request — pass full intent list; SAGE filters internally
    sage_payload = {
        "request_id":       request_id,
        "prompt":           state.get("prompt", ""),
        "security_profile": {
            "user_id": security_profile.get("user_id", ""),
            "role":    security_profile.get("role", ""),
            "row_level_security":    security_profile.get("row_level_security", []),
            "column_level_security": security_profile.get("column_level_security", []),
        },
        "intents":  intents,
        "metadata": metadata,
    }

    try:
        async with httpx.AsyncClient(timeout=SAGE_TIMEOUT) as client:
            resp = await client.post(SAGE_URL, json=sage_payload)
            resp.raise_for_status()
            data = resp.json()

        status = data.get("status", "error")
        logger.info("SAGE response: request_id=%s status=%s results=%d",
                    request_id, status, len(data.get("sql_results", [])))

        # Surface error: top-level first, then first failed intent's error
        sql_error = data.get("error")
        if not sql_error and status == "error":
            errs = [r.get("error") for r in data.get("sql_results", []) if r.get("error")]
            sql_error = errs[0] if errs else "SQL generation failed"

        return {
            "sql_status": status,
            "sql_result": data,
            "sql_error":  sql_error,
        }

    except httpx.ConnectError:
        logger.error("SAGE unreachable at %s", SAGE_URL)
        return {
            "sql_status": "error",
            "sql_result": None,
            "sql_error":  "SAGE service unavailable",
        }
    except Exception as e:
        logger.error("sql_node error: %s", e)
        return {
            "sql_status": "error",
            "sql_result": None,
            "sql_error":  str(e),
        }
