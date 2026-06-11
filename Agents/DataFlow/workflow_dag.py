"""
Workflow DAG — Declarative YAML parser and agentic LLM planner.

Two modes:
1. Declarative: parse a YAML workflow definition into ordered steps
2. Agentic: LLM receives the user's natural-language task, available sub-agents,
   and discovery results, then produces an execution plan

The planner outputs a WorkflowPlan containing ordered WorkflowStep items
that the executor runs sequentially.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from models import (
    ConnectionConfig,
    DiscoveryResult,
    PipelineOptions,
    WorkflowPlan,
    WorkflowRunRequest,
    WorkflowStep,
)

# ── LLM planner prompt ────────────────────────────────────────────────────

AGENTIC_PLANNER_PROMPT = """You are a data engineering workflow planner. You receive a user's
natural-language data engineering task and information about available sub-agents,
then produce a step-by-step plan.

Available sub-agents:
1. DISCOVERY — Introspect source tables, profile data, detect PII columns
2. INGESTION — Copy data from source to target with schema mapping
3. PII_MASK — Detect and mask PII columns (email, phone, SSN, CC, etc.)
4. TRANSFORMATION — Execute SQL/Jinja templates or dbt models
5. QUALITY — Run data quality checks (nulls, uniqueness, referential integrity)
6. PUBLISH — Create final tables, log lineage, apply permissions

Output a JSON array of step objects. Each step:
{{"step_id": "step_1", "agent": "discovery", "description": "..."}}

The steps will be executed in order. Dependencies between steps are expressed
by their position in the array (sequential execution).

Current task: {prompt}

Discovery results (if available):
{discovery_info}

Options:
- PII masking: {pii_mask}
- Quality rules: {quality_rules}
- dbt model: {dbt_model}
- Materialization: {materialization}

Return ONLY a valid JSON array of step objects, no markdown, no explanation."""


def _build_llm_payload(prompt: str, request: WorkflowRunRequest, discovery: Optional[DiscoveryResult]) -> str:
    """Build the prompt for the LLM planner."""
    discovery_info = ""
    if discovery and discovery.tables:
        parts = []
        for t in discovery.tables:
            cols = ", ".join(
                f"{c.name}({c.data_type}){' PII:' + c.pii_category if c.pii_category else ''}"
                for c in t.columns
            )
            parts.append(f"  - {t.table_name} ({t.row_count} rows): {cols}")
        discovery_info = "Tables found:\n" + "\n".join(parts)

    quality_rules = ", ".join(request.options.quality_rules or ["none"])
    dbt_model = request.options.dbt_model or "none"

    return AGENTIC_PLANNER_PROMPT.format(
        prompt=prompt,
        discovery_info=discovery_info or "No discovery results available",
        pii_mask=str(request.options.pii_mask),
        quality_rules=quality_rules,
        dbt_model=dbt_model,
        materialization=request.options.materialization,
    )


def _call_llm(prompt: str) -> str:
    """Call the configured LLM for agentic planning."""
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", "..", "backend", ".env"))

    import httpx

    api_key = os.getenv("LLM_API_KEY") or os.getenv("GROQ_API_KEY")
    base_url = os.getenv("LLM_BASE_URL") or "https://api.groq.com/openai/v1"
    model = os.getenv("LLM_MODEL") or os.getenv("GROQ_MODEL") or "llama-3.3-70b-versatile"

    if not api_key:
        # Fall back to a simple default plan
        return json.dumps([
            {"step_id": "step_1", "agent": "discovery", "description": "Discover source schema and profile data"},
            {"step_id": "step_2", "agent": "ingestion", "description": "Ingest data from source to target"},
            {"step_id": "step_3", "agent": "quality", "description": "Run quality checks"},
            {"step_id": "step_4", "agent": "publish", "description": "Publish final output"},
        ])

    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                f"{base_url}/chat/completions",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "You are a data engineering planner. Return only valid JSON."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                },
                headers={"Authorization": f"Bearer {api_key}"},
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            # Strip code fences if present
            content = content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1]
                if "```" in content:
                    content = content.rsplit("```", 1)[0]
            return content.strip()
    except Exception as e:
        # Fallback plan on error
        return json.dumps([
            {"step_id": "step_1", "agent": "discovery", "description": f"Discover source schema (fallback: {str(e)})"},
            {"step_id": "step_2", "agent": "ingestion", "description": "Ingest data"},
            {"step_id": "step_3", "agent": "quality", "description": "Quality checks"},
            {"step_id": "step_4", "agent": "publish", "description": "Publish results"},
        ])


# ── Public API ────────────────────────────────────────────────────────────

def build_default_plan(request: WorkflowRunRequest, discovery: Optional[DiscoveryResult] = None) -> WorkflowPlan:
    """
    Build a sensible default plan based on the request configuration.
    Used when LLM planning is not available or the user wants a quick standard plan.
    """
    steps: List[WorkflowStep] = []
    step_counter = 0

    def next_id() -> str:
        nonlocal step_counter
        step_counter += 1
        return f"step_{step_counter}"

    # Always: discover if we have a source
    if request.source_config and request.source_config.connection_string:
        steps.append(WorkflowStep(
            step_id=next_id(),
            agent="discovery",
            status="pending",
            description=f"Discover source schema and profile data",
        ))

    # Always: ingest
    if request.source_config and request.target_config:
        steps.append(WorkflowStep(
            step_id=next_id(),
            agent="ingestion",
            status="pending",
            description="Transfer data from source to target",
        ))

    # PII mask if requested
    if request.options.pii_mask:
        steps.append(WorkflowStep(
            step_id=next_id(),
            agent="pii_mask",
            status="pending",
            description="Detect and mask PII columns",
        ))

    # Transformation (SQL or dbt)
    if request.options.dbt_model:
        steps.append(WorkflowStep(
            step_id=next_id(),
            agent="transformation",
            status="pending",
            description=f"Run dbt model: {request.options.dbt_model}",
        ))

    # Quality checks
    if request.options.quality_rules:
        steps.append(WorkflowStep(
            step_id=next_id(),
            agent="quality",
            status="pending",
            description=f"Run {len(request.options.quality_rules)} quality checks",
        ))

    # Always: publish
    steps.append(WorkflowStep(
        step_id=next_id(),
        agent="publish",
        status="pending",
        description="Publish final output and log lineage",
    ))

    return WorkflowPlan(steps=steps, rationale="Default sequential plan based on pipeline options")


def plan_agentic(
    request: WorkflowRunRequest,
    discovery: Optional[DiscoveryResult] = None,
    use_llm: bool = True,
) -> WorkflowPlan:
    """
    Generate a workflow plan: either agentic (LLM decides) or default.

    Args:
        request: The full workflow run request.
        discovery: Optional discovery results to inform planning.
        use_llm: If True, call LLM for agentic planning. Falls back to default on error.

    Returns:
        WorkflowPlan with ordered steps.
    """
    if not use_llm:
        return build_default_plan(request, discovery)

    try:
        prompt = _build_llm_payload(request.prompt, request, discovery)
        llm_response = _call_llm(prompt)
        steps_data = json.loads(llm_response)

        steps: List[WorkflowStep] = []
        for item in steps_data:
            steps.append(WorkflowStep(
                step_id=item.get("step_id", f"step_{len(steps) + 1}"),
                agent=item.get("agent", "unknown"),
                status="pending",
                description=item.get("description", ""),
            ))

        if not steps:
            return build_default_plan(request, discovery)

        return WorkflowPlan(
            steps=steps,
            rationale=f"LLM-generated plan with {len(steps)} steps",
        )

    except Exception:
        return build_default_plan(request, discovery)