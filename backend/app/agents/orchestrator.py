"""
orchestrator.py
---------------
LangGraph StateGraph for the prompt pipeline.

Current flow (Phase 8 — SAGE ∥ RAVEN + DATAFLOW):
  guardrail_check → [blocked/error → END]
                  → intent_classify → [error → END]
                  → save_to_queue ─┬─ sql_generate → [SQL ok  → validate_sql]
                  (parallel)       │                          → [no SQL   → END]
                                   │                 validate_sql:
                                   │                   PASS/PARTIAL/WARN → dataflow_if_needed → spyder_synthesize → END
                                   │                   FAIL + attempt<2  → sql_correct → validate_sql
                                   │                   FAIL + attempt≥2  → END
                                   └─ raven_query → spyder_synthesize → END

  SAGE (sql_generate) and RAVEN (raven_query) run in parallel after save_to_queue.
  Both converge at spyder_synthesize (fan-in).
  RAVEN skips automatically when no unstructured intents exist.
  DATAFLOW (dataflow_run) fires after VALKYRIE when source/target config in metadata.

State keys:
  prompt, guardrails, security_profile, metadata          — inputs
  guardrail_status, blocked_by, guardrail_message         — set by guardrail_node
  intent_status, intent_result, intent_error              — set by intent_node
  queue_path, queue_error                                 — set by queue_writer_node
  sql_status, sql_result, sql_error                       — set by sql_node
  valkyrie_status, valkyrie_result, valkyrie_error        — set by valkyrie_node
  synthesizer_context                                     — set by valkyrie_node
  correction_attempt                                      — incremented by sql_correct_node
  correction_history                                      — audit list, appended by sql_correct_node
  spyder_status, spyder_result, spyder_error              — set by spyder_node
  raven_status, raven_result, raven_error                 — set by raven_node
  dataflow_status, dataflow_result, dataflow_error        — set by dataflow_node
  dataflow_plan                                           — set by dataflow_node
"""
import logging
from typing import Optional, List
from typing_extensions import TypedDict

from langgraph.graph import StateGraph, END

from app.agents.guardrail_node import guardrail_node
from app.agents.intent_node import intent_node
from app.agents.queue_writer import queue_writer_node
from app.agents.sql_node import sql_node
from app.agents.valkyrie_node import valkyrie_node
from app.agents.sql_correct_node import sql_correct_node
from app.agents.spyder_node import spyder_node
from app.agents.raven_node import raven_node
from app.agents.dataflow_node import dataflow_node

logger = logging.getLogger("orchestrator")

MAX_CORRECTIONS = 2

NODE_NAMES = frozenset({
    "guardrail_check",
    "intent_classify",
    "sql_generate",
    "validate_sql",
    "sql_correct",
    "raven_query",
    "spyder_synthesize",
    "dataflow_run",
})


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
    # correction loop
    correction_attempt: int
    correction_history: List[dict]
    # spyder outputs
    spyder_status: Optional[str]
    spyder_result: Optional[dict]
    spyder_error: Optional[str]
    # raven outputs
    raven_status: Optional[str]
    raven_result: Optional[dict]
    raven_error: Optional[str]
    # conversation memory
    conversation_context: Optional[str]
    # dataflow outputs
    dataflow_status: Optional[str]
    dataflow_result: Optional[dict]
    dataflow_error: Optional[str]
    dataflow_plan: Optional[dict]


# ── routers ──────────────────────────────────────────────────

def _after_guardrail(state: OrchestratorState) -> str:
    if state.get("guardrail_status") == "passed":
        return "intent_classify"
    return END


def _after_intent(state: OrchestratorState) -> str:
    if state.get("intent_status") == "success":
        return "save_to_queue"
    return END  # covers "error" and "out_of_scope"


def _after_sql(state: OrchestratorState) -> str:
    sql_result = state.get("sql_result")

    has_sql = sql_result and any(
        r.get("status") == "success"
        for r in sql_result.get("sql_results", [])
    )

    if has_sql:
        return "validate_sql"

    # If no SQL but user provided data-engineering config, route to dataflow
    metadata = state.get("metadata", {})
    if metadata.get("source_config") or metadata.get("target_config"):
        return "dataflow_if_needed"

    return END


def _after_validate(state: OrchestratorState) -> str:
    """
    PASS / WARN         → dataflow_if_needed (then spyder_synthesize)
    PARTIAL + attempt<2 → sql_correct (attempt to fix failed intents)
    PARTIAL + attempt≥2 → dataflow_if_needed (best-effort with passing intents)
    FAIL    + attempt<2 → sql_correct (loop back)
    FAIL    + attempt≥2 → dataflow_if_needed (then END)
    error / skipped     → dataflow_if_needed
    """
    status  = state.get("valkyrie_status", "")
    attempt = state.get("correction_attempt", 0)

    if status in ("fail", "partial") and attempt < MAX_CORRECTIONS:
        logger.info(
            "VALKYRIE %s — routing to sql_correct (attempt %d/%d)",
            status, attempt + 1, MAX_CORRECTIONS,
        )
        return "sql_correct"
    # After validation (pass/warn/partial≥2/fail≥2), optionally run dataflow
    return "dataflow_if_needed"


def _after_dataflow(state: OrchestratorState) -> str:
    """
    dataflow_run → spyder_synthesize (always, even if dataflow was skipped or failed)
    """
    return "spyder_synthesize"


# ── graph ────────────────────────────────────────────────────

def _build_graph():
    g = StateGraph(OrchestratorState)

    g.add_node("guardrail_check",   guardrail_node)
    g.add_node("intent_classify",   intent_node)
    g.add_node("save_to_queue",     queue_writer_node)
    g.add_node("sql_generate",      sql_node)
    g.add_node("validate_sql",      valkyrie_node)
    g.add_node("sql_correct",       sql_correct_node)
    g.add_node("dataflow_run",      dataflow_node)
    g.add_node("spyder_synthesize", spyder_node)
    g.add_node("raven_query",       raven_node)

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
    # Parallel fan-out: SAGE and RAVEN start simultaneously after queue write
    g.add_edge("save_to_queue", "sql_generate")
    g.add_edge("save_to_queue", "raven_query")
    g.add_conditional_edges(
        "sql_generate",
        _after_sql,
        {"validate_sql": "validate_sql", "dataflow_if_needed": "dataflow_run", END: END},
    )
    g.add_conditional_edges(
        "validate_sql",
        _after_validate,
        {
            "sql_correct": "sql_correct",
            "dataflow_if_needed": "dataflow_run",
            END: END,
        },
    )
    # After correction always re-validate
    g.add_edge("sql_correct", "validate_sql")
    # Dataflow runs between VALKYRIE and SPYDER; dataflow node skips gracefully
    g.add_edge("dataflow_run", "spyder_synthesize")
    # RAVEN fan-in: converges with SQL path at SPYDER
    g.add_edge("raven_query", "spyder_synthesize")
    # After synthesis always end
    g.add_edge("spyder_synthesize", END)

    return g.compile()


_pipeline_graph = _build_graph()


# ── public API ───────────────────────────────────────────────

def _make_initial_state(
    prompt: str,
    guardrails: dict,
    security_profile: dict,
    metadata: dict,
) -> OrchestratorState:
    return {
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
        "correction_attempt": 0,
        "correction_history": [],
        "spyder_status":      None,
        "spyder_result":      None,
        "spyder_error":       None,
        "raven_status":          None,
        "raven_result":          None,
        "raven_error":           None,
        "dataflow_status":       None,
        "dataflow_result":       None,
        "dataflow_error":        None,
        "dataflow_plan":         None,
        "conversation_context":  metadata.get("conversation_context", ""),
    }


async def run_pipeline(
    prompt: str,
    guardrails: dict,
    security_profile: dict,
    metadata: dict,
) -> OrchestratorState:
    result = await _pipeline_graph.ainvoke(
        _make_initial_state(prompt, guardrails, security_profile, metadata)
    )
    return result


async def stream_pipeline(
    prompt: str,
    guardrails: dict,
    security_profile: dict,
    metadata: dict,
):
    """Async generator: yields (node_name, state_delta) for each tracked node completion."""
    initial = _make_initial_state(prompt, guardrails, security_profile, metadata)
    async for event in _pipeline_graph.astream_events(initial, version="v2"):
        if event["event"] == "on_chain_end" and event["name"] in NODE_NAMES:
            yield event["name"], event["data"].get("output") or {}
