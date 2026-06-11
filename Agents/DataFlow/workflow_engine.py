"""
DataFlow — Agentic Data Engineering Workflow Engine

Standalone FastAPI microservice on port 8007.

Endpoints:
  POST /dataflow/run       — Full agentic pipeline (discover → plan → execute)
  POST /dataflow/discover  — Schema discovery only
  POST /dataflow/plan      — Plan generation only (preview before execution)
  GET  /health             — Health check

Architecture:
  - Receives a natural-language data engineering task + inline source/target config
  - An LLM planner produces a step-by-step workflow DAG
  - Each step is executed by a dedicated sub-agent
  - Supports both SQL/Jinja templates and dbt model execution
  - Reports progress through structured log events
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

# Add parent to sys.path so sub_agents imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

# ── Load backend .env ─────────────────────────────────────────────────────
_backend_env = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "backend", ".env",
)
if os.path.exists(_backend_env):
    load_dotenv(_backend_env)
    print(f"[DataFlow] Loaded env: {_backend_env}")
else:
    print(f"[DataFlow] WARNING: backend/.env not found at {_backend_env}")

from models import (
    ConnectionConfig,
    DiscoverRequest,
    DiscoveryResult,
    PlanRequest,
    PlanResponse,
    PipelineOptions,
    PublishResult,
    WorkflowPlan,
    WorkflowRunRequest,
    WorkflowRunResponse,
    WorkflowStep,
)

# ── Sub-agent imports ─────────────────────────────────────────────────────
from sub_agents.discovery_agent import discover as run_discovery
from sub_agents.ingestion_agent import ingest as run_ingestion
from sub_agents.pii_mask_agent import scan_and_mask as run_pii_mask
from sub_agents.transformation_agent import run_transform
from sub_agents.quality_agent import run_quality_checks
from sub_agents.publish_agent import publish as run_publish

# ── Workflow DAG planner ──────────────────────────────────────────────────
from workflow_dag import plan_agentic, build_default_plan

# ── App Setup ─────────────────────────────────────────────────────────────

logger = logging.getLogger("dataflow")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

app = FastAPI(title="DataFlow — Agentic Data Engineering", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── In-memory run store (replace with DB in production) ───────────────────

_runs: Dict[str, WorkflowRunResponse] = {}


def _get_run(request_id: str) -> WorkflowRunResponse:
    run = _runs.get(request_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {request_id} not found")
    return run


# ── Step Executor ─────────────────────────────────────────────────────────

def _execute_step(
    step: WorkflowStep,
    run: WorkflowRunResponse,
    request: WorkflowRunRequest,
    discovery_result: Optional[DiscoveryResult],
    context: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Execute a single workflow step by dispatching to the appropriate sub-agent.
    Returns the step result dict.
    """
    logger.info(f"Executing step {step.step_id}: {step.agent} — {step.description}")

    source = request.source_config
    target = request.target_config
    result: Dict[str, Any] = {}

    try:
        if step.agent == "discovery":
            if source:
                disc = run_discovery(source)
                result = disc.model_dump()
            else:
                result = {"tables": [], "warnings": ["No source config provided"]}

        elif step.agent == "ingestion":
            if source and target:
                # Determine source table
                src_table = context.get("source_table") or source.tables[0] if source.tables else None
                tgt_table = context.get("target_table") or src_table
                ingestion_result = run_ingestion(
                    source_config=source,
                    target_config=target,
                    source_table=src_table,
                    target_table=tgt_table,
                    chunk_size=request.options.chunk_size,
                )
                result = ingestion_result.model_dump()
                context["target_table"] = ingestion_result.target_table
                context["staging_table"] = ingestion_result.target_table
            else:
                result = {"rows_ingested": 0, "warnings": ["Source or target config missing"]}

        elif step.agent == "pii_mask":
            if target:
                table = context.get("staging_table") or target.tables[0] if target.tables else None
                if table:
                    pii_result = run_pii_mask(
                        config=target,
                        table=table,
                    )
                    result = pii_result.model_dump()
                else:
                    result = {"masked_columns": [], "warnings": ["No table specified"]}
            else:
                result = {"masked_columns": [], "warnings": ["No target config"]}

        elif step.agent == "transformation":
            if target:
                result = run_transform(
                    config=target,
                    sql_template=context.get("sql_template"),
                    context_vars=context.get("template_context"),
                    output_table=context.get("output_table", "transform_output"),
                    materialization=request.options.materialization,
                    dbt_model_name=request.options.dbt_model,
                    dbt_project_dir=request.options.dbt_project_dir,
                    dbt_profiles_dir=context.get("dbt_profiles_dir"),
                ).model_dump()
                if result.get("steps"):
                    last = result["steps"][-1]
                    context["output_table"] = last.get("output_table") or context.get("output_table")
                    context["staging_table"] = context["output_table"]
            else:
                result = {"steps": [], "warnings": ["No target config"]}

        elif step.agent == "quality":
            if target:
                table = context.get("output_table") or context.get("staging_table") or "transform_output"
                rules = request.options.quality_rules or ["not_empty"]
                quality_result = run_quality_checks(
                    config=target,
                    table=table,
                    rules=rules,
                )
                result = quality_result.model_dump()
            else:
                result = {"checks": [], "overall": "fail", "summary": "No target config"}

        elif step.agent == "publish":
            if target:
                staging = context.get("staging_table") or context.get("target_table") or "temp_output"
                final = context.get("final_table") or staging
                # Determine row count from context
                row_count = context.get("row_count", 0)
                if not row_count and discovery_result and discovery_result.tables:
                    src_table = source.tables[0] if source and source.tables else None
                    for t in discovery_result.tables:
                        if t.table_name == src_table:
                            row_count = t.row_count or 0
                            break

                publish_result = run_publish(
                    config=target,
                    staging_table=staging,
                    final_table=final,
                    security_profile=request.security_profile,
                    workflow_steps=run.plan.steps if run.plan else None,
                    step_results=run.results,
                    source_table=source.tables[0] if source and source.tables else None,
                    row_count=row_count,
                )
                result = publish_result.model_dump()
                run.final_output = publish_result
            else:
                result = {"final_table": "", "row_count": 0, "column_lineage": []}

        else:
            result = {"status": "error", "message": f"Unknown agent: {step.agent}"}

        step.status = "completed"

    except Exception as e:
        logger.error(f"Step {step.step_id} failed: {e}")
        step.status = "failed"
        step.error = str(e)
        result = {"status": "error", "message": str(e)}

    step.result = result
    step.completed_at = datetime.utcnow()
    run.results[step.step_id] = result

    return result


# ── Endpoints ─────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "dataflow", "version": "1.0.0"}


# ── Upload directory ──────────────────────────────────────────────

_UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
os.makedirs(_UPLOAD_DIR, exist_ok=True)


@app.post("/dataflow/upload")
async def upload_csv(file: UploadFile = File(...)):
    """
    Upload a CSV file and return a DuckDB source config that reads it.

    The file is saved to Agents/DataFlow/uploads/{uuid}_{filename}.
    Returns a ConnectionConfig that can be used as source_config in /dataflow/run.
    """
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are supported")

    safe_name = f"{uuid.uuid4().hex[:8]}_{file.filename}"
    dest = os.path.join(_UPLOAD_DIR, safe_name)

    try:
        content = await file.read()
        with open(dest, "wb") as f:
            f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

    abs_path = dest.replace("\\", "/")
    table_expr = f"read_csv_auto('{abs_path}')"

    logger.info(f"UPLOAD_OK file={file.filename} path={abs_path} size={len(content)} bytes")

    return {
        "filename": file.filename,
        "path": abs_path,
        "size_bytes": len(content),
        "source_config": {
            "type": "duckdb",
            "connection_string": "duckdb:///",
            "tables": [table_expr],
            "schema": None,
        },
        "note": "Use the returned source_config as the source in /dataflow/run",
    }


@app.post("/dataflow/discover", response_model=DiscoveryResult)
async def discover_endpoint(req: DiscoverRequest):
    """
    Schema discovery only — introspect source, profile data, detect PII.
    """
    try:
        result = run_discovery(req.connection)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/dataflow/plan", response_model=PlanResponse)
async def plan_endpoint(req: PlanRequest):
    """
    Generate a workflow plan without executing it.
    Useful for preview-and-approve workflows.
    """
    try:
        request = WorkflowRunRequest(
            prompt=req.prompt,
            source_config=req.source_config,
            target_config=req.target_config,
            options=req.options,
        )
        plan = plan_agentic(request, req.discovery_result, use_llm=True)
        requires_approval = len(plan.steps) > 1
        return PlanResponse(plan=plan, requires_approval=requires_approval)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/dataflow/run", response_model=WorkflowRunResponse)
async def run_endpoint(req: WorkflowRunRequest):
    """
    Full agentic pipeline: discover → plan → execute each step → return results.
    If dry_run is True, only plans and returns the plan without executing.
    """
    run_id = req.request_id or f"df-{uuid.uuid4().hex[:12]}"
    run = WorkflowRunResponse(
        request_id=run_id,
        status="planned",
    )
    _runs[run_id] = run
    context: Dict[str, Any] = {}

    try:
        # Phase 1: Discover
        discovery_result: Optional[DiscoveryResult] = None
        if req.source_config and req.source_config.connection_string:
            logger.info("Phase 1: Discovery")
            disc = run_discovery(req.source_config)
            discovery_result = disc

            if disc.tables:
                context["source_table"] = disc.tables[0].table_name
                tbl = disc.tables[0]
                logger.info(f"  Found table: {tbl.table_name} ({tbl.row_count} rows, {len(tbl.columns)} cols)")
                pii_cols = [c.name for c in tbl.columns if c.pii_category]
                if pii_cols:
                    logger.info(f"  PII columns detected: {pii_cols}")

        # Phase 2: Plan
        logger.info("Phase 2: Planning")
        plan = plan_agentic(req, discovery_result, use_llm=True)
        run.plan = plan
        run.status = "planned"

        if req.options.dry_run:
            run.status = "planned"
            return run

        # Phase 3: Execute
        logger.info(f"Phase 3: Execution ({len(plan.steps)} steps)")
        run.status = "running"

        for step in plan.steps:
            step.started_at = datetime.utcnow()
            _execute_step(step, run, req, discovery_result, context)
            if step.status == "failed":
                if step.agent == "quality":
                    # Quality failures don't stop the pipeline
                    logger.warning(f"Quality check warnings: {step.error}")
                    step.status = "completed"
                else:
                    logger.error(f"Pipeline stopped at step {step.step_id}: {step.agent}")
                    break

        # Determine final status
        failed_steps = [s for s in plan.steps if s.status == "failed"]
        if failed_steps:
            run.status = "failed"
            run.error = f"Failed at step(s): {', '.join(s.agent for s in failed_steps)}"
        else:
            run.status = "completed"

        run.completed_at = datetime.utcnow()
        return run

    except Exception as e:
        logger.error(f"Pipeline run failed: {e}")
        run.status = "failed"
        run.error = str(e)
        run.completed_at = datetime.utcnow()
        return run


@app.get("/dataflow/runs/{request_id}", response_model=WorkflowRunResponse)
async def get_run(request_id: str):
    """Get the status/result of a pipeline run."""
    return _get_run(request_id)


# ── Main ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("DATAFLOW_PORT", "8007"))
    print(f"[DataFlow] Starting on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)