"""
INGESTION Agent — Read from source, map schema, bulk write to target.

Supports PostgreSQL, DuckDB, and any SQLAlchemy-accessible source.
Handles schema mapping (auto-cast types), chunked reads for large tables,
and basic error recovery per chunk.
"""

from __future__ import annotations

import time
from typing import List, Optional

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from models import (
    ConnectionConfig,
    IngestionResult,
    SchemaMapping,
    TableProfile,
)


def _create_engine_from_config(config: ConnectionConfig) -> Engine:
    return create_engine(config.connection_string, pool_pre_ping=True)


def _derive_target_type(source_type: str) -> str:
    """Map source SQL types to generic target types."""
    type_lower = source_type.lower()
    if "int" in type_lower or "serial" in type_lower:
        return "BIGINT" if "big" in type_lower else "INTEGER"
    if "float" in type_lower or "double" in type_lower or "real" in type_lower:
        return "DOUBLE PRECISION"
    if "decimal" in type_lower or "numeric" in type_lower:
        return source_type.upper()
    if "bool" in type_lower:
        return "BOOLEAN"
    if "char" in type_lower or "text" in type_lower:
        return "TEXT"
    if "date" in type_lower or "timestamp" in type_lower:
        return source_type.upper()  # preserve date/timestamp variants
    if "json" in type_lower or "jsonb" in type_lower:
        return "JSONB"
    if "uuid" in type_lower:
        return "UUID"
    return "TEXT"


def _build_create_sql(
    table_name: str,
    columns: List[SchemaMapping],
    schema: Optional[str] = None,
) -> str:
    """Generate CREATE TABLE IF NOT EXISTS DDL from column mappings."""
    full_name = f"{schema}.{table_name}" if schema else table_name
    col_defs = ",\n  ".join(
        f"{m.target_column} {m.target_type}" for m in columns
    )
    return f"CREATE TABLE IF NOT EXISTS {full_name} (\n  {col_defs}\n);"


def _build_insert_sql(
    table_name: str,
    columns: List[SchemaMapping],
    schema: Optional[str] = None,
) -> str:
    """Generate INSERT INTO ... SELECT DML with casts."""
    full_name = f"{schema}.{table_name}" if schema else table_name
    target_cols = ", ".join(m.target_column for m in columns)
    source_exprs = ", ".join(
        m.cast_expression if m.cast_expression else m.source_column
        for m in columns
    )
    return f"INSERT INTO {full_name} ({target_cols})\nSELECT {source_exprs}"


def _build_schema_mappings(
    source_table: str,
    source_engine: Engine,
    source_schema: Optional[str],
    target_table: str,
    target_engine: Engine,
    target_schema: Optional[str],
) -> List[SchemaMapping]:
    """Build column mappings by matching source and target schemas."""
    src_inspector = inspect(source_engine)
    src_columns = src_inspector.get_columns(source_table, schema=source_schema)

    # If target already has the table, map columns; else derive from source
    tgt_inspector = inspect(target_engine)
    try:
        tgt_columns_list = tgt_inspector.get_columns(target_table, schema=target_schema)
        tgt_map = {c["name"].lower(): c for c in tgt_columns_list}
    except Exception:
        tgt_map = {}

    mappings: List[SchemaMapping] = []
    for col in src_columns:
        src_name = col["name"]
        src_type = str(col["type"])
        src_type_lower = src_type.lower()

        if tgt_map:
            # map by name
            tgt_col = tgt_map.get(src_name.lower())
            if tgt_col is None:
                continue
            tgt_type = str(tgt_col["type"])
            tgt_type_lower = tgt_type.lower()
            cast_expr = None
            if src_type_lower != tgt_type_lower:
                cast_expr = f"CAST({src_name} AS {tgt_type})"
            mappings.append(SchemaMapping(
                source_column=src_name,
                target_column=tgt_col["name"],
                source_type=src_type,
                target_type=tgt_type,
                cast_expression=cast_expr,
            ))
        else:
            # derive target type from source
            target_type = _derive_target_type(src_type)
            cast_expr = None
            if src_type_lower != target_type.lower():
                cast_expr = f"CAST({src_name} AS {target_type})"
            mappings.append(SchemaMapping(
                source_column=src_name,
                target_column=src_name,
                source_type=src_type,
                target_type=target_type,
                cast_expression=cast_expr,
            ))

    return mappings


def ingest(
    source_config: ConnectionConfig,
    target_config: ConnectionConfig,
    source_table: Optional[str] = None,
    target_table: Optional[str] = None,
    chunk_size: int = 10000,
) -> IngestionResult:
    """
    Main entry point: copy data from source → target with schema mapping.

    If source_table is None, uses the first table from source_config.tables.
    If target_table is None, uses the same name as source_table.
    """
    src_engine = _create_engine_from_config(source_config)
    tgt_engine = _create_engine_from_config(target_config)
    start = time.time()

    try:
        resolved_source = source_table or (source_config.tables or [None])[0]
        if not resolved_source:
            return IngestionResult(
                source_table="",
                target_table=target_table or "",
                rows_ingested=0,
                warnings=["No source table specified"],
            )

        resolved_target = target_table or resolved_source

        mappings = _build_schema_mappings(
            resolved_source, src_engine, source_config.schema,
            resolved_target, tgt_engine, target_config.schema,
        )

        if not mappings:
            return IngestionResult(
                source_table=resolved_source,
                target_table=resolved_target,
                rows_ingested=0,
                warnings=["No column mappings could be derived"],
            )

        # Create target table if needed
        create_sql = _build_create_sql(
            resolved_target, mappings, target_config.schema,
        )
        with tgt_engine.connect() as tgt_conn:
            tgt_conn.execute(text(create_sql))
            tgt_conn.commit()

        # Read source in chunks and write to target
        full_source = f"{source_config.schema}.{resolved_source}" if source_config.schema else resolved_source
        full_target = f"{target_config.schema}.{resolved_target}" if target_config.schema else resolved_target
        total_rows = 0
        offset = 0
        warnings_list: List[str] = []

        while True:
            select_cols = ", ".join(m.source_column for m in mappings)
            chunk_sql = text(
                f"SELECT {select_cols} FROM {full_source} "
                f"ORDER BY (SELECT NULL) LIMIT {chunk_size} OFFSET {offset}"
            )

            with src_engine.connect() as src_conn:
                rows = src_conn.execute(chunk_sql).fetchall()

            if not rows:
                break

            # Build insert with CAST expressions
            target_cols = ", ".join(m.target_column for m in mappings)
            insert_cols = ", ".join(
                m.cast_expression if m.cast_expression else m.source_column
                for m in mappings
            )

            placeholders = ", ".join(f":{i}" for i in range(len(mappings)))
            insert_sql = text(
                f"INSERT INTO {full_target} ({target_cols}) VALUES ({placeholders})"
            )

            with tgt_engine.connect() as tgt_conn:
                for row in rows:
                    tgt_conn.execute(insert_sql, list(row))
                tgt_conn.commit()

            total_rows += len(rows)
            offset += chunk_size

        elapsed = time.time() - start
        return IngestionResult(
            source_table=resolved_source,
            target_table=resolved_target,
            rows_ingested=total_rows,
            schema_mappings=mappings,
            duration_seconds=round(elapsed, 2),
            warnings=warnings_list,
        )

    except Exception as e:
        return IngestionResult(
            source_table=source_table or "",
            target_table=target_table or "",
            rows_ingested=0,
            duration_seconds=round(time.time() - start, 2),
            warnings=[f"Ingestion failed: {str(e)}"],
        )
    finally:
        src_engine.dispose()
        tgt_engine.dispose()