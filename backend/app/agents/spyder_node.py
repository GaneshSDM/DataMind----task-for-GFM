"""
spyder_node.py
--------------
LangGraph node: synthesize validated SQL results via SPYDER (port 8005).

Runs after VALKYRIE passes. Builds SPYDER JSON contract from synthesizer_context,
calls POST /api/synthesize (SSE), collects the complete event, returns spyder_result.

RAG/unstructured inputs are intentionally empty for now — future agents will fill them.
"""

import json
import logging
import httpx

logger = logging.getLogger("spyder_node")

SPYDER_URL = "http://localhost:8005"
TIMEOUT    = 180.0


async def spyder_node(state: dict) -> dict:
    synthesizer_ctx = state.get("synthesizer_context")
    valkyrie_status = state.get("valkyrie_status", "")

    if valkyrie_status not in ("pass", "partial", "warn") or not synthesizer_ctx:
        logger.info("SPYDER skipped — valkyrie_status=%s", valkyrie_status)
        return _skip()

    intents              = synthesizer_ctx.get("intents", [])
    validated_sql_results = synthesizer_ctx.get("validated_sql_results", [])
    request_id           = synthesizer_ctx.get("request_id", "")
    prompt               = synthesizer_ctx.get("prompt", "")

    # Build sql_scripts from passed validated SQL only
    intent_map = {i["intent_id"]: i for i in intents}
    sql_scripts = []
    for vr in validated_sql_results:
        if vr.get("validation_status") != "pass":
            continue
        intent_id = vr.get("intent_id")
        intent    = intent_map.get(intent_id, {})
        sql       = vr.get("sql", "")
        if not sql:
            continue
        sql_scripts.append({
            "query_id":    f"SQL_{intent_id:03d}",
            "label":       intent.get("description", f"Query {intent_id}"),
            "source_table": intent.get("structured_table", ""),
            "sql":         sql,
        })

    if not sql_scripts:
        logger.info("SPYDER skipped — no validated SQL scripts to synthesize")
        return _skip()

    domain = intents[0].get("domain", "Unknown") if intents else "Unknown"
    allowed_tables = list({s["source_table"] for s in sql_scripts if s["source_table"]})

    spyder_payload = {
        "request_id": request_id,
        "app_context": {
            "application_name": "MANTHAN.AI",
            "agent_name":       "SPYDER",
            "domain":           domain,
            "objective":        prompt,
        },
        "persona": {
            "role":        f"{domain} Synthesizer Agent",
            "instruction": (
                f"You are a domain synthesizer agent for {domain}. "
                "Analyse the SQL data and provide a clear, accurate, actionable synthesis. "
                "Treat SQL results as source of truth."
            ),
        },
        "user_query": prompt,
        "input_contract": {
            "structured_input_type":   "SQL",
            "unstructured_input_type": "Embedding similarity search",
            "structured_tables_allowed": allowed_tables,
            "rag_table":               "tracopp.rag_document_chunks",
            "allowed_rag_documents_only": [],
        },
        "structured_inputs":   {"sql_scripts": sql_scripts},
        "unstructured_inputs": {"similarity_search_inputs": []},   # future agents
        "execution_flow": {
            "steps": ["validate_json", "execute_sql", "retrieve_rag", "synthesize", "render_output"],
            "parallel_sql_execution": True,
            "parallel_rag_execution": False,
            "stop_on_critical_error": False,
            "timeout_seconds": 120,
        },
        "synthesis_instruction": {
            "treat_structured_as":   "source_of_truth",
            "treat_unstructured_as": "policy_and_guidance",
            "conflict_resolution":   "structured_data_wins",
            "response_language":     "English",
            "response_tone":         "professional",
            "include_recommendations": True,
        },
        "expected_output_schema": {
            "sections": [
                {
                    "section_id":   "structured_summary",
                    "title":        "Data Summary",
                    "display_type": "table_and_chart",
                    "chart_type":   "bar",
                    "source":       "sql",
                },
                {
                    "section_id":   "synthesized_answer",
                    "title":        "Synthesized Answer",
                    "display_type": "text",
                    "source":       "llm",
                },
                {
                    "section_id":   "recommendations",
                    "title":        "Recommendations",
                    "display_type": "list",
                    "source":       "llm",
                },
            ]
        },
        "error_handling": {
            "on_sql_error":  "continue_with_warning",
            "on_rag_error":  "continue_with_warning",
            "on_llm_error":  "return_partial_results",
            "max_retries":   2,
            "fallback_message": "Synthesis failed — partial results shown.",
        },
    }

    logger.info(
        "SPYDER request_id=%s domain=%s sql_scripts=%d",
        request_id, domain, len(sql_scripts),
    )

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            async with client.stream(
                "POST", f"{SPYDER_URL}/api/synthesize", json=spyder_payload
            ) as resp:
                resp.raise_for_status()
                complete_data = None
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if not raw:
                        continue
                    try:
                        event = json.loads(raw)
                        if event.get("event") == "complete":
                            complete_data = event.get("data")
                            break
                        if event.get("event") == "error":
                            logger.warning(
                                "SPYDER SSE error step=%s msg=%s",
                                event.get("step"), event.get("message"),
                            )
                    except json.JSONDecodeError:
                        pass

        if not complete_data:
            return _error("No complete event received from SPYDER")

        logger.info(
            "SPYDER synthesis complete request_id=%s sql_ok=%d",
            request_id,
            sum(1 for r in complete_data.get("sql_results", []) if r.get("status") == "success"),
        )
        return {
            "spyder_status": "success",
            "spyder_result": complete_data,
            "spyder_error":  None,
        }

    except httpx.ConnectError:
        logger.error("SPYDER not reachable at %s", SPYDER_URL)
        return _error("SPYDER service unavailable")
    except Exception as e:
        logger.error("spyder_node error: %s", e)
        return _error(str(e))


def _skip() -> dict:
    return {"spyder_status": "skipped", "spyder_result": None, "spyder_error": None}


def _error(msg: str) -> dict:
    return {"spyder_status": "error", "spyder_result": None, "spyder_error": msg}
