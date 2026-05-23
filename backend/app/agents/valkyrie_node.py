"""
valkyrie_node.py
----------------
LangGraph node: validate SAGE SQL results via VALKYRIE (single pass).

Correction loop is orchestrator-managed:
  validate_sql → FAIL + attempts < 2 → sql_correct → validate_sql
  validate_sql → PASS / attempts >= 2 → END

This node only calls VALKYRIE once and returns the result.
"""

import logging
import httpx

logger = logging.getLogger("valkyrie_node")

VALKYRIE_URL = "http://localhost:8004"
TIMEOUT      = 120.0


async def valkyrie_node(state: dict) -> dict:
    sql_result       = state.get("sql_result")
    intent_result    = state.get("intent_result")
    security_profile = state.get("security_profile", {})
    prompt           = state.get("prompt", "")
    request_id       = state.get("metadata", {}).get("request_id", "")

    if not sql_result or not intent_result:
        return _skip()

    sql_results = sql_result.get("sql_results", [])
    intents     = intent_result.get("intents", [])

    if not any(r.get("status") == "success" for r in sql_results):
        return _skip()

    attempt = state.get("correction_attempt", 0)
    logger.info(
        "VALKYRIE validate request_id=%s attempt=%d",
        request_id, attempt,
    )

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            payload = {
                "request_id":       request_id,
                "prompt":           prompt,
                "security_profile": security_profile,
                "intents":          intents,
                "sql_results":      sql_results,
            }
            resp = await client.post(f"{VALKYRIE_URL}/sql/validate", json=payload)
            resp.raise_for_status()
            val_response = resp.json()

        overall = val_response.get("status", "error")
        logger.info(
            "VALKYRIE result request_id=%s attempt=%d status=%s",
            request_id, attempt, overall,
        )
        return {
            "valkyrie_status":     overall,
            "valkyrie_result":     val_response,
            "synthesizer_context": val_response.get("synthesizer_context"),
            "valkyrie_error":      None,
        }

    except httpx.ConnectError:
        logger.error("VALKYRIE not reachable at %s", VALKYRIE_URL)
        return {
            "valkyrie_status":     "error",
            "valkyrie_result":     None,
            "synthesizer_context": None,
            "valkyrie_error":      "VALKYRIE service unavailable",
        }
    except Exception as e:
        logger.error("valkyrie_node error: %s", e)
        return {
            "valkyrie_status":     "error",
            "valkyrie_result":     None,
            "synthesizer_context": None,
            "valkyrie_error":      str(e),
        }


def _skip() -> dict:
    return {
        "valkyrie_status":     "skipped",
        "valkyrie_result":     None,
        "synthesizer_context": None,
        "valkyrie_error":      None,
    }
