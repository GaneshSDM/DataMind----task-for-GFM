"""
spyder_node.py
--------------
LangGraph node: synthesize validated SQL results via SPYDER (port 8005).

Runs after VALKYRIE passes (SQL path) or directly after RAVEN (pure-unstructured path).
Builds SPYDER JSON contract, calls POST /api/synthesize (SSE), returns spyder_result.
"""

import json
import logging
import re
from collections import defaultdict

import httpx

from app.agents.http_clients import get_spyder_client

logger = logging.getLogger("spyder_node")


# ── Action 1: Merge duplicate RAG inputs ──────────────────────────────────────

def _merge_search_inputs(search_inputs: list) -> list:
    """
    Group search inputs by document_filter (same PDF file).
    Merge descriptions; use embedding of the most comprehensive query.
    Scale top_k = min(count × per_intent_k, 15) so more chunks are retrieved.
    Reduces redundant pgvector searches and duplicate context in LLM prompt.
    """
    groups: dict = defaultdict(list)
    for inp in search_inputs:
        key = inp.get("document_filter") or "__domain__"
        groups[key].append(inp)

    merged = []
    for key, items in groups.items():
        if len(items) == 1:
            merged.append(items[0])
            continue
        # Use embedding from the most comprehensive query (longest content string)
        primary = max(items, key=lambda x: len(x.get("content", "")))
        combined_content = " | ".join(i.get("content", "") for i in items)
        scaled_top_k = min(len(items) * int(primary.get("top_k", 5)), 15)
        merged.append({
            **primary,
            "embedding_id": items[0].get("embedding_id", "RAG_MERGED"),
            "content":      combined_content,
            "top_k":        scaled_top_k,
        })
        logger.info(
            "SPYDER merged %d RAG inputs for doc=%s → top_k=%d",
            len(items), key, scaled_top_k,
        )
    return merged


# ── Action 2: Dynamic output sections from intent descriptions ────────────────

def _clean_section_id(description: str) -> str:
    """Convert intent description → snake_case section_id."""
    desc = description.lower()
    for prefix in ("fetch ", "retrieve ", "get ", "analyze ", "analyse ", "compare and ", "compare "):
        if desc.startswith(prefix):
            desc = desc[len(prefix):]
            break
    for suffix in (" for a sales order cancellation", " for a sales order", " for sales orders",
                   " for the sales order", " for an order"):
        if desc.endswith(suffix):
            desc = desc[:-len(suffix)]
            break
    return re.sub(r"[^a-z0-9]+", "_", desc).strip("_")[:50]


def _clean_section_title(description: str) -> str:
    """Convert intent description → human-readable title."""
    desc = description
    for prefix in ("Fetch ", "Retrieve ", "Get ", "Analyze ", "Analyse ", "Compare and ", "Compare "):
        if desc.lower().startswith(prefix.lower()):
            desc = desc[len(prefix):]
            break
    for suffix in (" for a sales order cancellation", " for a sales order", " for sales orders",
                   " for the sales order", " for an order"):
        if desc.lower().endswith(suffix.lower()):
            desc = desc[:-len(suffix)]
            break
    return desc.strip()


def _build_rag_sections(intents: list) -> list:
    """
    Build dynamic expected_output_schema sections from Data-type unstructured intents.
    Reasoning intents are excluded — analysis is SPYDER's synthesis job, not a separate section.
    Always appends a Recommendations list section last.
    """
    sections = []
    seen_ids: set = set()

    for intent in intents:
        if intent.get("data_source") not in ("Unstructured", "Both"):
            continue
        # Skip pure-Reasoning intents (SPYDER synthesises, not retrieves)
        types = intent.get("intent_types") or []
        if types and all(t == "Reasoning" for t in types):
            continue
        desc = intent.get("description", "")
        sid  = _clean_section_id(desc)
        if not sid or sid in seen_ids:
            continue
        seen_ids.add(sid)
        sections.append({
            "section_id":   sid,
            "title":        _clean_section_title(desc),
            "display_type": "text",
            "source":       "llm",
        })

    sections.append({
        "section_id":   "recommendations",
        "title":        "Recommendations",
        "display_type": "list",
        "source":       "llm",
    })
    return sections

async def spyder_node(state: dict) -> dict:
    synthesizer_ctx = state.get("synthesizer_context")
    valkyrie_status = state.get("valkyrie_status", "")
    raven_result    = state.get("raven_result")

    has_sql_context = (
        valkyrie_status in ("pass", "partial", "warn") and synthesizer_ctx
    )
    has_raven_inputs = (
        raven_result and
        raven_result.get("status") == "success" and
        raven_result.get("similarity_search_inputs")
    )

    if not has_sql_context and not has_raven_inputs:
        logger.info(
            "SPYDER skipped — no SQL context (valkyrie_status=%s) and no RAG inputs",
            valkyrie_status,
        )
        return _skip()

    # ── Build context: SQL path uses synthesizer_ctx; pure-RAG path uses state directly ──
    if has_sql_context:
        intents               = synthesizer_ctx.get("intents", [])
        validated_sql_results = synthesizer_ctx.get("validated_sql_results", [])
        request_id            = synthesizer_ctx.get("request_id", "")
        prompt                = synthesizer_ctx.get("prompt", "")
    else:
        # Pure-RAG path — VALKYRIE was never called (no SQL intents)
        intent_result         = state.get("intent_result") or {}
        intents               = intent_result.get("intents", [])
        validated_sql_results = []
        request_id            = (state.get("metadata") or {}).get("request_id", "")
        prompt                = state.get("prompt", "")

    # RAG inputs from RAVEN node — Action 1: merge duplicates before sending to SPYDER
    search_inputs = []
    if has_raven_inputs:
        raw_inputs    = raven_result.get("similarity_search_inputs", [])
        search_inputs = _merge_search_inputs(raw_inputs)
        logger.info(
            "SPYDER RAG inputs: %d raw → %d merged",
            len(raw_inputs), len(search_inputs),
        )

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

    if not sql_scripts and not search_inputs:
        logger.info("SPYDER skipped — no SQL scripts and no RAG inputs")
        return _skip()

    domain = intents[0].get("domain", "Unknown") if intents else "Unknown"
    allowed_tables = list({s["source_table"] for s in sql_scripts if s["source_table"]})

    # Action 4: Context-aware persona with specific citation instructions
    if sql_scripts and search_inputs:
        persona_instruction = (
            f"You are a domain synthesizer agent for {domain}. "
            "Analyse the SQL data and knowledge base context together. "
            "Treat SQL results as source of truth for transactional data; "
            "use KB documents for policy rules, thresholds, and guidance. "
            "For each section, cite specific values from the data (e.g. counts, amounts, dates). "
            "Produce a clear, accurate, actionable synthesis."
        )
    elif search_inputs:
        # Action 4: Specific instruction to cite actual values, not vague paraphrases
        persona_instruction = (
            f"You are a knowledge base synthesizer for {domain}. "
            "For each requested section, extract SPECIFIC rules, thresholds, timelines, and "
            "procedures from the retrieved KB chunks. "
            "Cite actual values — e.g. '30 minutes', '3–5 business days', '7-day window', "
            "'full refund', 'partial refund'. "
            "Use bullet points for rule lists. Use numbered steps for processes. "
            "Do NOT paraphrase vaguely. Do NOT repeat raw chunk text. "
            "Produce a coherent, professional summary for each section."
        )
    else:
        persona_instruction = (
            f"You are a domain synthesizer agent for {domain}. "
            "Analyse the SQL data and provide a clear, accurate, actionable synthesis."
        )

    spyder_payload = {
        "request_id": request_id,
        "app_context": {
            "application_name": "MANTHAN.AI",
            "agent_name":       "SPYDER",
            "domain":           domain,
            "objective":        prompt,
        },
        "persona": {
            "role":        f"{domain} Knowledge Synthesizer" if not sql_scripts else f"{domain} Synthesizer Agent",
            "instruction": persona_instruction,
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
        "unstructured_inputs": {"similarity_search_inputs": [s if isinstance(s, dict) else s.model_dump() if hasattr(s, "model_dump") else s for s in search_inputs]},
        "execution_flow": {
            "steps": ["validate_json", "execute_sql", "retrieve_rag", "synthesize", "render_output"],
            "parallel_sql_execution": True,
            "parallel_rag_execution": False,
            "stop_on_critical_error": False,
            "timeout_seconds": 120,
        },
        "synthesis_instruction": {
            "treat_structured_as":   "source_of_truth" if sql_scripts else "not_applicable",
            "treat_unstructured_as": "primary_knowledge_source" if not sql_scripts else "policy_and_guidance",
            "conflict_resolution":   "structured_data_wins" if sql_scripts else "use_kb_as_truth",
            "response_language":     "English",
            "response_tone":         "professional",
            "include_recommendations": True,
        },
        # Action 2: dynamic sections — per-topic for pure-RAG, fixed for SQL paths
        "expected_output_schema": {
            "sections": (
                _build_rag_sections(intents)
                if not sql_scripts
                else [
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
            )
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
        client = get_spyder_client()
        async with client.stream("POST", "/api/synthesize", json=spyder_payload) as resp:
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
        logger.error("SPYDER not reachable at http://localhost:8005")
        return _error("SPYDER service unavailable")
    except Exception as e:
        logger.error("spyder_node error: %s", e)
        return _error(str(e))


def _skip() -> dict:
    return {"spyder_status": "skipped", "spyder_result": None, "spyder_error": None}


def _error(msg: str) -> dict:
    return {"spyder_status": "error", "spyder_result": None, "spyder_error": msg}
