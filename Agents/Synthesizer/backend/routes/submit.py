"""
POST /api/submit-json   — Previous agent submits JSON directly.
GET  /api/latest-submission — Frontend polls to pick up new submissions.
"""
import time
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()

# In-memory store: last submitted payload + timestamp
_store: dict = {"payload": None, "received_at": None, "consumed": True}


@router.post("/submit-json")
async def submit_json(request: Request):
    """
    Called by the upstream agent to push a new JSON payload.
    The frontend will pick it up via GET /api/latest-submission.
    """
    try:
        payload = await request.json()
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": f"Invalid JSON: {e}"})

    _store["payload"] = payload
    _store["received_at"] = time.time()
    _store["consumed"] = False

    domain = payload.get("app_context", {}).get("domain", "Unknown")
    request_id = payload.get("request_id", "n/a")
    return JSONResponse(
        content={
            "accepted": True,
            "request_id": request_id,
            "domain": domain,
            "message": "JSON received. The Synthesizer UI will pick it up shortly.",
        }
    )


@router.get("/latest-submission")
async def latest_submission():
    """
    Frontend polls this endpoint to detect new agent-submitted payloads.
    Returns the payload once, then marks it consumed.
    """
    if _store["payload"] is None or _store["consumed"]:
        return JSONResponse(content={"new_submission": False})

    _store["consumed"] = True
    return JSONResponse(
        content={
            "new_submission": True,
            "payload": _store["payload"],
            "received_at": _store["received_at"],
        }
    )
