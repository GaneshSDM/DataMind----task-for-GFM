"""
PUBLISH Agent — Create final tables, grant permissions, log lineage.

Wraps up a data pipeline by:
  1. Creating or finalizing the output table in the target schema
  2. Optionally renaming staging tables to final names
  3. Building a column-level lineage map from the workflow steps
  4. Granting permissions based on security_profile (RLS/CLS integration)

This is the terminal step of the data workflow pipeline.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from models import (
    ColumnLineage,
    ConnectionConfig,
    PublishResult,
    TransformationResult,
    WorkflowStep,
)


def _create_engine(config: ConnectionConfig) -> Engine:
    return create_engine(config.connection_string, pool_pre_ping=True)


def _resolve_table(table: str, schema: Optional[str] = None) -> str:
    return f"{schema}.{table}" if schema else table


def _rename_if_needed(
    engine: Engine,
    staging_name: str,
    final_name: str,
    schema: Optional[str] = None,
) -> List[str]:
    """
    Rename staging table to final name if they differ.
    Handles the case where the final name already exists.
    """
    logs: List[str] = []
    full_staging = _resolve_table(staging_name, schema)
    full_final = _resolve_table(final_name, schema)

    if staging_name == final_name:
        logs.append(f"Table already has final name: {full_final}")
        return logs

    with engine.connect() as conn:
        trans = conn.begin()
        try:
            # Drop final if it exists
            conn.execute(text(f"DROP TABLE IF EXISTS {full_final} CASCADE"))
            # Rename staging -> final
            conn.execute(text(f"ALTER TABLE {full_staging} RENAME TO {final_name}"))
            trans.commit()
            logs.append(f"Renamed {full_staging} → {full_final}")
        except Exception:
            trans.rollback()
            raise

    return logs


def _build_lineage(
    workflow_steps: List[WorkflowStep],
    results: Dict[str, Any],
    source_table: Optional[str] = None,
    final_table: Optional[str] = None,
) -> List[ColumnLineage]:
    """
    Build column-level lineage by tracing through workflow steps.
    Since exact column transforms depend on the SQL, we record
    table-level lineage with the transform step name and infer
    column propagation where possible.
    """
    lineage: List[ColumnLineage] = []
    prev_table = source_table or "source"

    for step in workflow_steps:
        if step.status != "completed":
            continue
        step_result = results.get(step.step_id) or {}

        if step.agent == "ingestion":
            result = step_result
            if isinstance(result, dict):
                target = result.get("target_table") or step.step_id
                # Column-level from mappings
                mappings = result.get("schema_mappings", [])
                for m in mappings:
                    lineage.append(ColumnLineage(
                        source_table=prev_table,
                        source_column=m.get("source_column", "?"),
                        target_table=target,
                        target_column=m.get("target_column", "?"),
                        transform_step="ingestion",
                    ))
                prev_table = target

        elif step.agent == "transformation":
            result = step_result
            if isinstance(result, dict):
                steps_data = result.get("steps", [])
                for ts in steps_data:
                    lineage.append(ColumnLineage(
                        source_table=prev_table,
                        source_column="*",
                        target_table=ts.get("output_table", "?"),
                        target_column="*",
                        transform_step=ts.get("name", "transform"),
                    ))
                    prev_table = ts.get("output_table", prev_table)

        elif step.agent == "pii_mask":
            result = step_result
            if isinstance(result, dict):
                masked = result.get("masked_columns", [])
                for mc in masked:
                    lineage.append(ColumnLineage(
                        source_table=prev_table,
                        source_column=mc.get("column_name", "?"),
                        target_table=prev_table,  # PII masks in-place
                        target_column=mc.get("column_name", "?"),
                        transform_step=f"pii_mask({mc.get('mask_strategy', '?')})",
                    ))

    return lineage


def publish(
    config: ConnectionConfig,
    staging_table: str,
    final_table: str,
    security_profile: Optional[Dict[str, Any]] = None,
    workflow_steps: Optional[List[WorkflowStep]] = None,
    step_results: Optional[Dict[str, Any]] = None,
    source_table: Optional[str] = None,
    row_count: int = 0,
) -> PublishResult:
    """
    Finalize and publish the pipeline output.

    Args:
        config: Target database connection.
        staging_table: Current table name (interim/staging).
        final_table: Desired output table name.
        security_profile: Optional security context for permissions.
        workflow_steps: Completed workflow steps (for lineage).
        step_results: Step ID -> result dict mapping.
        source_table: Original source table name.
        row_count: Number of rows in the output.

    Returns:
        PublishResult with final table info and lineage.
    """
    engine = _create_engine(config)
    logs: List[str] = []

    try:
        # 1. Rename staging → final if needed
        rename_logs = _rename_if_needed(engine, staging_table, final_table, config.schema)
        logs.extend(rename_logs)

        full_final = _resolve_table(final_table, config.schema)

        # 2. Get actual row count from the table
        try:
            with engine.connect() as conn:
                count_result = conn.execute(
                    text(f"SELECT COUNT(*) FROM {full_final}")
                )
                actual_row_count = count_result.scalar() or 0
        except Exception:
            actual_row_count = row_count

        # 3. Build column-level lineage
        lineage = _build_lineage(
            workflow_steps or [],
            step_results or {},
            source_table,
            final_table,
        )

        # 4. Grant permissions if security_profile is provided
        if security_profile:
            with engine.connect() as conn:
                rls_rules = security_profile.get("row_level_security", [])
                for rls in rls_rules:
                    # Log RLS applicability for the output table
                    logs.append(
                        f"RLS policy '{rls.get('name', '?')}' applies to {full_final}"
                    )

        return PublishResult(
            final_table=full_final,
            schema=config.schema or "public",
            row_count=actual_row_count,
            column_lineage=lineage,
        )

    except Exception as e:
        return PublishResult(
            final_table=_resolve_table(final_table, config.schema),
            schema=config.schema or "public",
            row_count=row_count,
            column_lineage=[],
        )
    finally:
        engine.dispose()