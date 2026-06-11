"""
TRANSFORMATION Agent — SQL template execution and dbt model runner.

Two modes:
1. SQL template mode: render Jinja2 templates with context variables, execute against target DB.
   Supports materialization strategies: table, view, incremental, ephemeral.
2. dbt mode: shell out to `dbt run --select <model>` in the specified project directory.

Both modes capture row counts and duration for observability.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from jinja2 import Environment, BaseLoader, TemplateNotFound
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from models import ConnectionConfig, TransformStep, TransformationResult

_JINJA_ENV = Environment(loader=BaseLoader(), autoescape=False)


def _create_engine(config: ConnectionConfig) -> Engine:
    return create_engine(config.connection_string, pool_pre_ping=True)


def _get_row_count(engine: Engine, table: str, schema: Optional[str] = None) -> int:
    """Get approximate row count for a table."""
    full = f"{schema}.{table}" if schema else table
    try:
        with engine.connect() as conn:
            result = conn.execute(text(f"SELECT COUNT(*) FROM {full}"))
            return result.scalar() or 0
    except Exception:
        return 0


def _get_table_names_from_sql(sql: str) -> List[str]:
    """
    Simple heuristic to extract referenced table names from SQL.
    Not a full parser — good enough for logging/lineage hints.
    """
    import re
    patterns = re.findall(
        r'\b(?:FROM|JOIN|INTO|TABLE|UPDATE)\s+["`]?(\w+(?:\.\w+)?)["`]?\b',
        sql, re.IGNORECASE
    )
    return list(set(patterns))


# ── SQL Template Mode ─────────────────────────────────────────────────────

def _render_template(
    sql_template: str,
    context: Dict[str, Any],
) -> str:
    """Render a Jinja2 SQL template with the given context variables."""
    template = _JINJA_ENV.from_string(sql_template)
    return template.render(**context)


def _execute_sql_template(
    engine: Engine,
    sql: str,
    output_table: str,
    materialization: str,
    schema: Optional[str] = None,
    dbt_run: bool = False,
) -> TransformStep:
    """Execute a rendered SQL template against the target engine."""
    full_output = f"{schema}.{output_table}" if schema else output_table
    start = time.time()
    log_lines: List[str] = []
    rows_affected = 0

    try:
        if materialization == "view":
            drop_sql = f"DROP VIEW IF EXISTS {full_output} CASCADE"
            create_sql = f"CREATE VIEW {full_output} AS\n{sql}"
            log_lines.append(f"Dropped existing view: {full_output}")

            with engine.connect() as conn:
                conn.execute(text(drop_sql))
                conn.execute(text(create_sql))
                conn.commit()
            log_lines.append(f"Created view: {full_output}")

        elif materialization == "ephemeral":
            # Ephemeral just returns the SQL as a CTE — caller wraps it
            log_lines.append("Ephemeral transform — no persistent output created")
            elapsed = round(time.time() - start, 2)
            return TransformStep(
                name=output_table,
                type="sql_template",
                output_table=output_table,
                materialization="ephemeral",
                sql=sql,
                rows_affected=0,
                duration_seconds=elapsed,
                log="; ".join(log_lines),
            )

        else:  # "table" or "incremental"
            if materialization == "incremental":
                # Check if table exists
                with engine.connect() as conn:
                    check = conn.execute(
                        text(f"SELECT to_regclass('{full_output}')")
                    ).scalar()
                is_new = check is None
            else:
                is_new = True
                with engine.connect() as conn:
                    conn.execute(text(f"DROP TABLE IF EXISTS {full_output} CASCADE"))
                    conn.commit()

            if is_new:
                create_sql = f"CREATE TABLE {full_output} AS\n{sql}"
                with engine.connect() as conn:
                    result = conn.execute(text(create_sql))
                    conn.commit()
                    rows_affected = result.rowcount
                    if rows_affected < 0:
                        rows_affected = _get_row_count(engine, output_table, schema)
                log_lines.append(f"Created table: {full_output} ({rows_affected} rows)")
            else:
                # Incremental: INSERT INTO ... SELECT
                insert_sql = f"INSERT INTO {full_output}\n{sql}"
                with engine.connect() as conn:
                    result = conn.execute(text(insert_sql))
                    conn.commit()
                    rows_affected = result.rowcount or 0
                log_lines.append(f"Incremental insert: {full_output} (+{rows_affected} rows)")

        elapsed = round(time.time() - start, 2)
        return TransformStep(
            name=output_table,
            type="sql_template",
            output_table=output_table,
            materialization=materialization,
            sql=sql,
            rows_affected=rows_affected,
            duration_seconds=elapsed,
            log="; ".join(log_lines),
        )

    except Exception as e:
        elapsed = round(time.time() - start, 2)
        return TransformStep(
            name=output_table,
            type="sql_template",
            output_table=output_table,
            materialization=materialization,
            sql=sql,
            rows_affected=0,
            duration_seconds=elapsed,
            log=f"ERROR: {str(e)}",
        )


# ── dbt Mode ──────────────────────────────────────────────────────────────

def _run_dbt_model(
    project_dir: str,
    model_name: str,
    profiles_dir: Optional[str] = None,
) -> TransformStep:
    """Shell out to dbt CLI for model execution."""
    start = time.time()
    log_lines: List[str] = []

    try:
        cmd = ["dbt", "run", "--select", model_name]
        if profiles_dir:
            cmd.extend(["--profiles-dir", profiles_dir])

        log_lines.append(f"Running: {' '.join(cmd)} in {project_dir}")

        result = subprocess.run(
            cmd,
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=600,
        )

        elapsed = round(time.time() - start, 2)
        log_lines.append(f"dbt exit code: {result.returncode}")

        if result.stdout:
            log_lines.append(result.stdout[-2000:])
        if result.stderr:
            log_lines.append(f"stderr: {result.stderr[-1000:]}")

        if result.returncode == 0:
            return TransformStep(
                name=model_name,
                type="dbt_model",
                output_table=model_name,
                materialization="dbt",
                dbt_model_name=model_name,
                rows_affected=0,
                duration_seconds=elapsed,
                log="; ".join(log_lines),
            )
        else:
            return TransformStep(
                name=model_name,
                type="dbt_model",
                output_table=model_name,
                materialization="dbt",
                dbt_model_name=model_name,
                rows_affected=0,
                duration_seconds=elapsed,
                log=f"dbt failed: {'; '.join(log_lines)}",
            )

    except subprocess.TimeoutExpired:
        return TransformStep(
            name=model_name,
            type="dbt_model",
            output_table=model_name,
            materialization="dbt",
            dbt_model_name=model_name,
            rows_affected=0,
            duration_seconds=round(time.time() - start, 2),
            log="dbt process timed out after 600s",
        )
    except FileNotFoundError:
        return TransformStep(
            name=model_name,
            type="dbt_model",
            output_table=model_name,
            materialization="dbt",
            dbt_model_name=model_name,
            rows_affected=0,
            duration_seconds=round(time.time() - start, 2),
            log="dbt CLI not found on PATH",
        )
    except Exception as e:
        return TransformStep(
            name=model_name,
            type="dbt_model",
            output_table=model_name,
            materialization="dbt",
            dbt_model_name=model_name,
            rows_affected=0,
            duration_seconds=round(time.time() - start, 2),
            log=f"dbt error: {str(e)}",
        )


# ── Public API ────────────────────────────────────────────────────────────

def run_transform(
    config: ConnectionConfig,
    sql_template: Optional[str] = None,
    context_vars: Optional[Dict[str, Any]] = None,
    output_table: Optional[str] = None,
    materialization: str = "table",
    dbt_model_name: Optional[str] = None,
    dbt_project_dir: Optional[str] = None,
    dbt_profiles_dir: Optional[str] = None,
) -> TransformationResult:
    """
    Execute a transformation step.

    Args:
        config: Target database connection config.
        sql_template: Jinja2 SQL template string (for SQL mode).
        context_vars: Variables to render into the template.
        output_table: Name of the output table/view.
        materialization: table | view | incremental | ephemeral | dbt.
        dbt_model_name: dbt model name (for dbt mode).
        dbt_project_dir: Path to dbt project (for dbt mode).
        dbt_profiles_dir: Path to dbt profiles directory (optional).

    Returns:
        TransformationResult with one or more steps.
    """
    steps: List[TransformStep] = []
    warnings: List[str] = []

    if dbt_model_name and dbt_project_dir:
        step = _run_dbt_model(dbt_project_dir, dbt_model_name, dbt_profiles_dir)
        steps.append(step)
        final = dbt_model_name

    elif sql_template:
        context = context_vars or {}
        rendered = _render_template(sql_template, context)

        if not output_table:
            warnings.append("No output_table specified; using 'transform_output'")
            output_table = "transform_output"

        engine = _create_engine(config)
        try:
            step = _execute_sql_template(
                engine, rendered, output_table, materialization, config.schema
            )
            steps.append(step)
        finally:
            engine.dispose()

        if step.log.startswith("ERROR"):
            warnings.append(step.log)
    else:
        warnings.append("No sql_template or dbt_model_name provided — nothing to transform")

    return TransformationResult(
        steps=steps,
        final_table=output_table if steps else None,
        warnings=warnings,
    )