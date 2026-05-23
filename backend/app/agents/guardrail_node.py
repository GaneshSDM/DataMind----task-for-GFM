"""
guardrail_node.py
-----------------
LangGraph node that calls the Heimdall guardrail microservice (port 8001).
Returns updated state with guardrail_status, blocked_by, guardrail_message.
"""
import logging
import httpx

logger = logging.getLogger("orchestrator.guardrail_node")

HEIMDALL_URL = "http://localhost:8001/guardrail/check"
TIMEOUT = 10.0  # seconds


async def guardrail_node(state: dict) -> dict:
    """
    Calls Heimdall with the full WatchmanRequest payload.
    On success  → guardrail_status = 'passed' | 'blocked'
    On HTTP/net error → guardrail_status = 'error'
    """
    payload = {
        "prompt": state["prompt"],
        "guardrails": state["guardrails"],
        "security_profile": state["security_profile"],
        "metadata": state["metadata"],
    }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(HEIMDALL_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()

        status = data.get("status", "error")
        logger.info(
            "Heimdall [%s] request_id=%s blocked_by=%s",
            status, state["metadata"].get("request_id"), data.get("blocked_by"),
        )
        return {
            "guardrail_status": status,
            "blocked_by": data.get("blocked_by"),
            "guardrail_message": data.get("message", ""),
        }

    except httpx.ConnectError:
        logger.error("Heimdall unreachable at %s", HEIMDALL_URL)
        return {
            "guardrail_status": "error",
            "blocked_by": "system",
            "guardrail_message": "Guardrail service is unavailable. Please try again later.",
        }
    except httpx.HTTPStatusError as e:
        logger.error("Heimdall HTTP %s: %s", e.response.status_code, e.response.text)
        return {
            "guardrail_status": "error",
            "blocked_by": "system",
            "guardrail_message": f"Guardrail service returned error {e.response.status_code}.",
        }
    except Exception as e:
        logger.error("Heimdall unexpected error: %s", e)
        return {
            "guardrail_status": "error",
            "blocked_by": "system",
            "guardrail_message": f"Guardrail check failed: {str(e)}",
        }
