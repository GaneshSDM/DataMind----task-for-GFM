"""
dataflow_node.py — LangGraph node for the Data Workflow Agent.

Calls the DataFlow microservice (port 8007) to run an agentic data
engineering pipeline: discover source tables, ingest, transform, mask
PII, check quality, and publish.

This node is invoked when the prompt contains a data-engineering task
with source/target configs in the metadata. It fires *after* validation
(or in parallel with raven) and *before* spyder synthesis, so its
results flow into the final synthesis.

Node name: "dataflow_run"
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from app.agents.http_clients import get_dataflow_client

logger = logging.getLogger("orchestrator.dataflow")


def _skip() -> dict:
    return {
        "dataflow_status": None,
        "dataflow_result": None,
        "dataflow_error": None,
        "dataflow_plan": None,
    }


def _error(msg: str) -> dict:
    return {
        "dataflow_status": "error",
        "dataflow_result": None,
        "dataflow_error": msg,
        "dataflow_plan": None,
    }


async def dataflow_node(state: dict) -> dict:
    """
    LangGraph node for the Data Workflow Agent.

    Reads source/target config from state['metadata'] (inline one-time config).
    Calls POST /dataflow/run on the DataFlow microservice.
    Returns status + full result dict.

    State keys consumed:
      metadata.source_config     — inline source connection config
      metadata.target_config     — inline target connection config
      metadata.dataflow_options  — PipelineOptions dict
      prompt                     — natural-language task description

    State keys produced:
      dataflow_status   — "completed" | "failed" | "error" | None (skipped)
      dataflow_result   — full WorkflowRunResponse dict
      dataflow_error    — error message if failed
      dataflow_plan     — the generated workflow plan (for preview)
    """
    metadata = state.get("metadata", {})
    source_config = metadata.get("source_config")
    target_config = metadata.get("target_config")

    # Skip if no data engineering config provided
    if not source_config and not target_config:
        logger.info("dataflow_run SKIP — no source/target config in metadata")
        return _skip()

    # Also skip if explicitly flagged (e.g., a regular chat query)
    if metadata.get("skip_dataflow", False):
        logger.info("dataflow_run SKIP — skip_dataflow flag set")
        return _skip()

    prompt = state.get("prompt", "")
    dataflow_options = metadata.get("dataflow_options", {})

    payload = {
        "request_id": metadata.get("request_id", "df-backend"),
        "prompt": prompt,
        "source_config": source_config,
        "target_config": target_config,
        "options": {
            "pii_mask": dataflow_options.get("pii_mask", False),
            "quality_rules": dataflow_options.get("quality_rules"),
            "dbt_model": dataflow_options.get("dbt_model"),
            "dbt_project_dir": dataflow_options.get("dbt_project_dir"),
            "materialization": dataflow_options.get("materialization", "table"),
            "chunk_size": dataflow_options.get("chunk_size", 10000),
            "dry_run": dataflow_options.get("dry_run", False),
        },
        "security_profile": state.get("security_profile"),
        "metadata": metadata,
    }

    logger.info(
        "dataflow_run START prompt=%.60s source=%s target=%s pii=%s dbt=%s",
        prompt,
        json.dumps(source_config.get("type") if source_config else None),
        json.dumps(target_config.get("type") if target_config else None),
        dataflow_options.get("pii_mask", False),
        dataflow_options.get("dbt_model"),
    )

    try:
        client = get_dataflow_client()
        resp = await client.post("/dataflow/run", json=payload)
        resp.raise_for_status()
        result = resp.json()

        status = result.get("status", "failed")
        logger.info(f"dataflow_run DONE status={status}")

        return {
            "dataflow_status": status,
            "dataflow_result": result,
            "dataflow_error": result.get("error"),
            "dataflow_plan": result.get("plan"),
        }

    except Exception as e:
        logger.error(f"dataflow_run ERROR: {e}")
        return _error(str(e))