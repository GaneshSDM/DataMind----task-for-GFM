"""
orchestrator.py
---------------
LangGraph StateGraph for the prompt pipeline.

Current flow (Phase 4):
  guardrail_check → [blocked/error → END]
                  → intent_classify → [error → END]
                  → save_to_queue → sql_generate → validate_sql → END

State keys:
  prompt, guardrails, security_profile, metadata          — inputs
  guardrail_status, blocked_by, guardrail_message         — set by guardrail_node
  intent_status, intent_result, intent_error              — set by intent_node
  queue_path, queue_error                                 — set by queue_writer_node
  sql_status, sql_result, sql_error                       — set by sql_node
  valkyrie_status, valkyrie_result, valkyrie_error        — set by valkyrie_node
  synthesizer_context                                     — set by valkyrie_node
"""
import logging
from typing import Optional
from typing_extensions import TypedDict

from langgraph.graph import StateGraph, END

from app.agents.guardrail_node import guardrail_node
from app.agents.intent_node import intent_node
from app.agents.queue_writer import queue_writer_node
from app.agents.sql_node import sql_node
from app.agents.valkyrie_node import valkyrie_node

logger = logging.getLogger("orchestrator")


# ── state schema ─────────────────────────────────────────────

class OrchestratorState(TypedDict):
    # inputs
    prompt: str
    guardrails: dict
    security_profile: dict
    metadata: dict
    # guardrail outputs
    guardrail_status: Optional[str]
    blocked_by: Optional[str]
    guardrail_message: Optional[str]
    # intent outputs
    intent_status: Optional[str]
    intent_result: Optional[dict]
    intent_error: Optional[str]
    # queue outputs
    queue_path: Optional[str]
    queue_error: Optional[str]
    # sql generator outputs
    sql_status: Optional[str]
    sql_result: Optional[dict]
    sql_error: Optional[str]
    # valkyrie outputs
    valkyrie_status: Optional[str]
    valkyrie_result: Optional[dict]
    valkyrie_error: Optional[str]
    synthesizer_context: Optional[dict]


# ── routers ──────────────────────────────────────────────────

def _after_guardrail(state: OrchestratorState) -> str:
    if state.get("guardrail_status") == "passed":
        return "intent_classify"
    return END


def _after_intent(state: OrchestratorState) -> str:
    if state.get("intent_status") == "success":
        return "save_to_queue"
    return END


def _after_queue(state: OrchestratorState) -> str:
    # Always attempt SQL generation if intents exist, even if queue write failed
    if state.get("intent_result") and state["intent_result"].get("intents"):
        return "sql_generate"
    return END


def _after_sql(state: OrchestratorState) -> str:
    # Validate SQL if SAGE produced at least one successful result
    sql_result = state.get("sql_result")
    if sql_result and any(
        r.get("status") == "success"
        for r in sql_result.get("sql_results", [])
    ):
        return "validate_sql"
    return END


# ── graph ────────────────────────────────────────────────────

def _build_graph():
    g = StateGraph(OrchestratorState)

    g.add_node("guardrail_check", guardrail_node)
    g.add_node("intent_classify", intent_node)
    g.add_node("save_to_queue",   queue_writer_node)
    g.add_node("sql_generate",    sql_node)
    g.add_node("validate_sql",    valkyrie_node)

    g.set_entry_point("guardrail_check")
    g.add_conditional_edges(
        "guardrail_check",
        _after_guardrail,
        {"intent_classify": "intent_classify", END: END},
    )
    g.add_conditional_edges(
        "intent_classify",
        _after_intent,
        {"save_to_queue": "save_to_queue", END: END},
    )
    g.add_conditional_edges(
        "save_to_queue",
        _after_queue,
        {"sql_generate": "sql_generate", END: END},
    )
    g.add_conditional_edges(
        "sql_generate",
        _after_sql,
        {"validate_sql": "validate_sql", END: END},
    )
    g.add_edge("validate_sql", END)

    return g.compile()


_pipeline_graph = _build_graph()


# ── public API ───────────────────────────────────────────────

async def run_pipeline(
    prompt: str,
    guardrails: dict,
    security_profile: dict,
    metadata: dict,
) -> OrchestratorState:
    initial: OrchestratorState = {
        "prompt": prompt,
        "guardrails": guardrails,
        "security_profile": security_profile,
        "metadata": metadata,
        "guardrail_status": None,
        "blocked_by": None,
        "guardrail_message": None,
        "intent_status": None,
        "intent_result": None,
        "intent_error": None,
        "queue_path":  None,
        "queue_error": None,
        "sql_status":  None,
        "sql_result":  None,
        "sql_error":   None,
        "valkyrie_status":    None,
        "valkyrie_result":    None,
        "valkyrie_error":     None,
        "synthesizer_context": None,
    }
    result = await _pipeline_graph.ainvoke(initial)
    return result
