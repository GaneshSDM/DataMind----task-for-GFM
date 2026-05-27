"""
intent_node.py
--------------
LangGraph node that calls the ARIA intent classifier microservice (port 8002).
Returns updated state with intent_result, intent_status, intent_error.
"""
import logging
import httpx

from app.agents.http_clients import get_aria_client

logger = logging.getLogger("orchestrator.intent_node")


async def intent_node(state: dict) -> dict:
    """
    Calls ARIA with prompt + security_profile.
    On success  → intent_status = 'success', intent_result = {...}
    On error    → intent_status = 'error', intent_error = '...'
    """
    payload = {
        "request_id":           state["metadata"].get("request_id", ""),
        "prompt":               state["prompt"],
        "security_profile":     state["security_profile"],
        "metadata":             state["metadata"],
        "conversation_context": state.get("conversation_context", ""),
    }

    try:
        client = get_aria_client()
        resp = await client.post("/intent/classify", json=payload)
        resp.raise_for_status()
        data = resp.json()

        status = data.get("status", "error")
        logger.info(
            "ARIA [%s] request_id=%s intents=%s",
            status,
            state["metadata"].get("request_id"),
            len(data.get("intent_result", {}).get("intents", [])) if data.get("intent_result") else 0,
        )

        if status == "success":
            intent_result = data.get("intent_result") or {}
            # Check if ARIA flagged query as out of scope
            if intent_result.get("out_of_scope"):
                return {
                    "intent_status": "out_of_scope",
                    "intent_result": intent_result,
                    "intent_error": intent_result.get("reason", "Query is outside your accessible data domains."),
                }
            return {
                "intent_status": "success",
                "intent_result": intent_result,
                "intent_error": None,
            }
        else:
            return {
                "intent_status": "error",
                "intent_result": None,
                "intent_error": data.get("error", "Unknown ARIA error"),
            }

    except httpx.ConnectError:
        logger.error("ARIA unreachable at http://localhost:8002")
        return {
            "intent_status": "error",
            "intent_result": None,
            "intent_error": "Intent classifier service is unavailable. Please try again later.",
        }
    except httpx.HTTPStatusError as e:
        logger.error("ARIA HTTP %s: %s", e.response.status_code, e.response.text)
        return {
            "intent_status": "error",
            "intent_result": None,
            "intent_error": f"Intent classifier returned error {e.response.status_code}.",
        }
    except Exception as e:
        logger.error("ARIA unexpected error: %s", e)
        return {
            "intent_status": "error",
            "intent_result": None,
            "intent_error": f"Intent classification failed: {str(e)}",
        }
