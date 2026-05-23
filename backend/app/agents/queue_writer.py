"""
queue_writer.py
---------------
LangGraph node that persists the pipeline payload to Agents/pipeline_queue/.
File name: {request_id}.json
Only called when guardrail_status == 'passed'.
"""
import os
import json
import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger("orchestrator.queue_writer")

# Resolved relative to this file: slm-app/Agents/pipeline_queue/
_HERE = os.path.dirname(os.path.abspath(__file__))
QUEUE_DIR = os.path.normpath(
    os.path.join(_HERE, "..", "..", "..", "Agents", "pipeline_queue")
)


def _ensure_queue_dir():
    os.makedirs(QUEUE_DIR, exist_ok=True)


async def queue_writer_node(state: dict) -> dict:
    """
    Writes enriched pipeline JSON to Agents/pipeline_queue/{request_id}.json.
    Sets queue_path on success, queue_error on failure.
    """
    _ensure_queue_dir()

    request_id = state["metadata"].get("request_id", str(uuid.uuid4()))
    filename = f"{request_id}.json"
    filepath = os.path.join(QUEUE_DIR, filename)

    intent_result = state.get("intent_result")
    payload = {
        "schema_version": "1.1",
        "queued_at": datetime.now(timezone.utc).isoformat(),
        "request_id": request_id,
        "stage": "intent_classified",
        "next_agent": "sql_generator",
        "prompt": state["prompt"],
        "guardrails": state["guardrails"],
        "security_profile": state["security_profile"],
        "metadata": state["metadata"],
        "intent_result": intent_result,
    }

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)
        logger.info("Pipeline JSON queued: %s", filepath)
        return {"queue_path": filepath, "queue_error": None}
    except Exception as e:
        logger.error("queue_writer failed: %s", e)
        return {"queue_path": None, "queue_error": str(e)}
