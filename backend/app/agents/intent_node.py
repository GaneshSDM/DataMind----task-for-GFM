"""
intent_node.py
--------------
LangGraph node that calls the ARIA intent classifier microservice (port 8002).
Returns updated state with intent_result, intent_status, intent_error.
"""
import logging
import httpx

logger = logging.getLogger("orchestrator.intent_node")

ARIA_URL = "http://localhost:8002/intent/classify"
TIMEOUT = 60.0  # LLM call — allow up to 60s


async def intent_node(state: dict) -> dict:
    """
    Calls ARIA with prompt + security_profile.
    On success  → intent_status = 'success', intent_result = {...}
    On error    → intent_status = 'error', intent_error = '...'
    """
    payload = {
        "request_id": state["metadata"].get("request_id", ""),
        "prompt": state["prompt"],
        "security_profile": state["security_profile"],
        "metadata": state["metadata"],
    }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(ARIA_URL, json=payload)
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
            return {
                "intent_status": "success",
                "intent_result": data.get("intent_result"),
                "intent_error": None,
            }
        else:
            return {
                "intent_status": "error",
                "intent_result": None,
                "intent_error": data.get("error", "Unknown ARIA error"),
            }

    except httpx.ConnectError:
        logger.error("ARIA unreachable at %s", ARIA_URL)
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
