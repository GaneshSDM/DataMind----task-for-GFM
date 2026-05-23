"""
POST /api/synthesize
Main synthesis pipeline with Server-Sent Events (SSE) streaming.

Stream format (one JSON object per "data:" line):
  { "event": "progress", "step": "<step_id>", "status": "in_progress"|"completed"|"error",
    "message": "...", "data": <optional intermediate result> }
  { "event": "complete", "data": { ...full result... } }
  { "event": "error",    "step": "...", "message": "...", "errors": [...] }
"""
import asyncio
import json
import time
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from services.json_validator import validate_json_contract
from services.sql_service import execute_sql_scripts
from services.rag_service import run_similarity_search
from services.llm_service import synthesize_with_llm

router = APIRouter()


def _sse(obj: dict) -> str:
    """Encode a dict as a single SSE data line."""
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def _progress(step: str, status: str, message: str = "", data=None) -> str:
    obj: dict = {"event": "progress", "step": step, "status": status, "message": message}
    if data is not None:
        obj["data"] = data
    return _sse(obj)


def _error_event(step: str, message: str, errors: list | None = None) -> str:
    obj: dict = {"event": "error", "step": step, "message": message}
    if errors:
        obj["errors"] = errors
    return _sse(obj)


@router.post("/synthesize")
async def synthesize(request: Request):
    payload = await request.json()
    loop = asyncio.get_event_loop()

    async def event_stream():
        logs: list[dict] = []
        start_time = time.time()

        def log(level: str, msg: str):
            entry = {"time": round(time.time() - start_time, 3), "level": level, "message": msg}
            logs.append(entry)

        # ── Step 1: Validate JSON ──────────────────────────────────────────────
        yield _progress("validate_json", "in_progress", "Validating JSON contract…")
        log("info", "Starting JSON validation")

        validation = await loop.run_in_executor(None, validate_json_contract, payload)

        if not validation["valid"]:
            log("error", f"Validation failed: {validation['errors']}")
            yield _error_event("validate_json", "JSON validation failed.", validation["errors"])
            yield _sse({"event": "logs", "data": logs})
            return

        if validation["warnings"]:
            log("warn", f"Validation warnings: {validation['warnings']}")

        yield _progress(
            "validate_json", "completed",
            f"JSON valid. {len(validation['warnings'])} warning(s).",
            {"warnings": validation["warnings"]},
        )
        log("info", "JSON validation passed")

        # ── Step 2: Execute SQL ────────────────────────────────────────────────
        sql_scripts = payload.get("structured_inputs", {}).get("sql_scripts", [])
        yield _progress("execute_sql", "in_progress", f"Executing {len(sql_scripts)} SQL query(ies)…")
        log("info", f"Executing {len(sql_scripts)} SQL scripts")

        sql_results = await loop.run_in_executor(None, execute_sql_scripts, sql_scripts)

        sql_errors = [r for r in sql_results if r["status"] == "error"]
        sql_ok = [r for r in sql_results if r["status"] == "success"]
        total_rows = sum(r["row_count"] for r in sql_ok)

        for r in sql_results:
            if r["status"] == "error":
                log("error", f"SQL {r['query_id']} failed: {r.get('error')}")
            else:
                log("info", f"SQL {r['query_id']} → {r['row_count']} row(s)")

        yield _progress(
            "execute_sql", "completed",
            f"{len(sql_ok)}/{len(sql_scripts)} queries succeeded. {total_rows} total row(s).",
            sql_results,
        )

        # ── Step 3: Retrieve RAG ───────────────────────────────────────────────
        rag_inputs = payload.get("unstructured_inputs", {}).get("similarity_search_inputs", [])
        yield _progress("retrieve_rag", "in_progress", f"Searching knowledge base ({len(rag_inputs)} query(ies))…")
        log("info", f"Running {len(rag_inputs)} RAG similarity search(es)")

        rag_results = await loop.run_in_executor(None, run_similarity_search, rag_inputs)

        for r in rag_results:
            if r["status"] == "error":
                log("error", f"RAG {r['embedding_id']} failed: {r.get('error')}")
            else:
                log("info", f"RAG {r['embedding_id']} → {r['chunk_count']} chunk(s)")

        total_chunks = sum(r.get("chunk_count", 0) for r in rag_results if r["status"] == "success")
        yield _progress(
            "retrieve_rag", "completed",
            f"Retrieved {total_chunks} chunk(s) across {len(rag_inputs)} search(es).",
            rag_results,
        )

        # ── Step 4: Synthesize (LLM) ───────────────────────────────────────────
        yield _progress("synthesize", "in_progress", "Synthesizing with LLM — this may take a moment…")
        log("info", f"Calling LLM ({payload.get('app_context', {}).get('model', 'unknown')})")

        try:
            llm_response = await loop.run_in_executor(
                None, synthesize_with_llm, payload, sql_results, rag_results
            )
            log("info", "LLM synthesis completed successfully")
        except Exception as e:
            log("error", f"LLM call failed: {e}")
            llm_response = {"synthesized_answer": f"LLM synthesis failed: {e}"}
            yield _error_event("synthesize", f"LLM error: {e}")

        yield _progress("synthesize", "completed", "Synthesis complete.")

        # ── Step 5: Render Output ──────────────────────────────────────────────
        yield _progress("render_output", "in_progress", "Preparing final output…")
        log("info", "Building final response")

        final = {
            "request_id": payload.get("request_id"),
            "domain": payload.get("app_context", {}).get("domain", "Unknown"),
            "agent_name": payload.get("app_context", {}).get("agent_name", "Domain Synthesizer Agent"),
            "user_query": payload.get("user_query", ""),
            "sql_results": sql_results,
            "rag_results": rag_results,
            "llm_response": llm_response,
            "expected_output_schema": payload.get("expected_output_schema", {}),
            "execution_meta": {
                "total_duration_s": round(time.time() - start_time, 2),
                "sql_queries": len(sql_scripts),
                "rag_searches": len(rag_inputs),
                "sql_errors": len(sql_errors),
                "rag_errors": len([r for r in rag_results if r["status"] == "error"]),
            },
            "logs": logs,
        }

        yield _progress("render_output", "completed", "Ready.")
        yield _sse({"event": "complete", "data": final})
        log("info", f"Done in {final['execution_meta']['total_duration_s']}s")
        yield _sse({"event": "logs", "data": logs})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
