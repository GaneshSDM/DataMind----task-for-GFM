"""
raven_node.py
-------------
LangGraph node: generate RAG similarity search inputs via RAVEN (port 8006).

Runs after VALKYRIE validation passes (or directly after sql_generate when
all intents are Unstructured and no SQL was produced).
Sends unstructured intents + security_profile to RAVEN (:8006/rag/query).
RAVEN embeds query text and validates domain access.
Returns raven_status, raven_result (similarity_search_inputs[]), raven_error.

State keys set:
  raven_status   — "success" | "skipped" | "error"
  raven_result   — full RAVENResponse dict, or None
  raven_error    — error string, or None
"""
import logging
import httpx

from app.agents.http_clients import get_raven_client

logger = logging.getLogger("raven_node")


async def raven_node(state: dict) -> dict:
    intent_result    = state.get("intent_result")
    security_profile = state.get("security_profile", {})
    prompt           = state.get("prompt", "")
    request_id       = state.get("metadata", {}).get("request_id", "")

    if not intent_result:
        return _skip()

    intents = intent_result.get("intents", [])

    # Only call RAVEN if at least one intent needs unstructured retrieval
    has_unstructured = any(
        i.get("data_source") in ("Unstructured", "Both") for i in intents
    )
    if not has_unstructured:
        logger.info("RAVEN skip request_id=%s — no unstructured intents", request_id)
        return _skip()

    logger.info(
        "RAVEN query request_id=%s intents=%d",
        request_id, len(intents),
    )

    try:
        client = get_raven_client()
        payload = {
            "request_id":       request_id,
            "prompt":           prompt,
            "intents":          intents,
            "security_profile": security_profile,
            "top_k":            5,
        }
        resp = await client.post("/rag/query", json=payload)
        resp.raise_for_status()
        data = resp.json()

        status = data.get("status", "error")
        logger.info(
            "RAVEN result request_id=%s status=%s inputs=%d skipped=%d",
            request_id, status,
            len(data.get("similarity_search_inputs", [])),
            len(data.get("skipped_intents", [])),
        )
        return {
            "raven_status": status,
            "raven_result": data,
            "raven_error":  None,
        }

    except httpx.ConnectError:
        logger.error("RAVEN not reachable at http://localhost:8006")
        return _error("RAVEN service unavailable")
    except Exception as e:
        logger.error("raven_node error: %s", e)
        return _error(str(e))


def _skip() -> dict:
    return {"raven_status": "skipped", "raven_result": None, "raven_error": None}


def _error(msg: str) -> dict:
    return {"raven_status": "error", "raven_result": None, "raven_error": msg}
