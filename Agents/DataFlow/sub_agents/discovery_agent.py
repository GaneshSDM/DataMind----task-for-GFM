"""
DISCOVERY Agent — Schema introspection, data profiling, PII column heuristics.

Connects to a source database (via inline connection string), introspects
INFORMATION_SCHEMA, profiles sample data, and classifies PII columns using
regex patterns and column-name heuristics.
"""

from __future__ import annotations

import math
import re
import warnings
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from models import ColumnProfile, ConnectionConfig, DiscoveryResult, TableProfile

# ── PII Regex Patterns (inspired by AltimateAI's 30+ pattern approach) ───

PII_PATTERNS: List[Tuple[str, str, float]] = [
    # (category, regex, base_confidence)
    ("email",        r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",                         0.90),
    ("phone",        r"\+?\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}",           0.85),
    ("ssn",          r"\b(?!000|666|9\d{2})\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b",                 0.95),
    ("credit_card",  r"\b(?:\d[ -]*?){13,16}\b",                                                0.80),
    ("ip_address",   r"\b(?:\d{1,3}\.){3}\d{1,3}\b",                                           0.85),
    ("zip_code",     r"\b\d{5}(?:-\d{4})?\b",                                                   0.70),
    ("date",         r"\b\d{4}-\d{2}-\d{2}\b|\b\d{2}[/-]\d{2}[/-]\d{4}\b",                     0.60),
    ("url",          r"https?://[^\s]+",                                                         0.80),
    ("uuid",         r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",      0.90),
]

COLUMN_NAME_PII_HINTS: Dict[str, Tuple[str, float]] = {
    # column name keyword → (pii_category, confidence_boost)
    "email":         ("email", 0.95),
    "e-mail":        ("email", 0.95),
    "mail":          ("email", 0.85),
    "phone":         ("phone", 0.90),
    "telephone":     ("phone", 0.90),
    "mobile":        ("phone", 0.90),
    "cell":          ("phone", 0.80),
    "ssn":           ("ssn", 0.98),
    "social_security": ("ssn", 0.98),
    "credit_card":   ("credit_card", 0.95),
    "cc_number":     ("credit_card", 0.95),
    "card_number":   ("credit_card", 0.95),
    "ip":            ("ip_address", 0.90),
    "ip_address":    ("ip_address", 0.95),
    "zip":           ("zip_code", 0.85),
    "zip_code":      ("zip_code", 0.90),
    "postal_code":   ("zip_code", 0.85),
    "password":      ("password", 0.95),
    "passwd":        ("password", 0.90),
    "secret":        ("secret", 0.80),
    "token":         ("token", 0.80),
    "api_key":       ("api_key", 0.90),
    "dob":           ("date_of_birth", 0.90),
    "birth_date":    ("date_of_birth", 0.90),
    "birthday":      ("date_of_birth", 0.85),
}


def _create_engine(config: ConnectionConfig) -> Engine:
    """Create a SQLAlchemy engine from an inline connection config."""
    return create_engine(config.connection_string, pool_pre_ping=True)


def _introspect_tables(engine: Engine, config: ConnectionConfig) -> List[TableProfile]:
    """Use SQLAlchemy inspect to get table/column metadata."""
    inspector = inspect(engine)
    tables: List[TableProfile] = []

    target_tables = config.tables
    available_tables = inspector.get_table_names(schema=config.schema)

    for table_name in available_tables:
        if target_tables and table_name not in target_tables:
            continue

        columns_data = inspector.get_columns(table_name, schema=config.schema)
        pk_constraint = inspector.get_pk_constraint(table_name, schema=config.schema)
        pk_columns = set(pk_constraint.get("constrained_columns", []))

        cols: List[ColumnProfile] = []
        for col in columns_data:
            cols.append(ColumnProfile(
                name=col["name"],
                data_type=str(col["type"]),
                nullable=col.get("nullable", True),
                is_pk=col["name"] in pk_columns,
            ))

        tables.append(TableProfile(table_name=table_name, columns=cols))

    return tables


def _profile_sample_data(
    engine: Engine,
    table: TableProfile,
    schema: Optional[str] = None,
    sample_size: int = 100,
) -> TableProfile:
    """Run profiling queries: row count, sample values, null %, distinct %."""
    db_url = str(engine.url)
    is_duckdb = "duckdb" in db_url

    full_name = f"{schema}.{table.table_name}" if schema else table.table_name

    try:
        with engine.connect() as conn:
            # Row count
            row_result = conn.execute(text(f"SELECT COUNT(*) FROM {full_name}"))
            table.row_count = row_result.scalar() or 0

            if table.row_count == 0:
                return table

            for col in table.columns:
                quoted = f'"{col.name}"' if is_duckdb else f'"{col.name}"'

                # Null count
                null_sql = text(f"SELECT COUNT(*) FROM {full_name} WHERE {quoted} IS NULL")
                col.null_count = conn.execute(null_sql).scalar() or 0

                # Distinct count
                dist_sql = text(f"SELECT COUNT(DISTINCT {quoted}) FROM {full_name}")
                col.distinct_count = conn.execute(dist_sql).scalar() or 0

                # Sample values (first non-null values)
                sample_sql = text(
                    f"SELECT DISTINCT {quoted} FROM {full_name} "
                    f"WHERE {quoted} IS NOT NULL LIMIT {sample_size}"
                )
                samples = [row[0] for row in conn.execute(sample_sql).fetchall()]
                col.sample_values = samples[:10]  # keep first 10

                # Min/max for numeric and date types
                type_lower = col.data_type.lower()
                if any(t in type_lower for t in ("int", "float", "double", "decimal", "numeric", "date", "timestamp")):
                    try:
                        agg_sql = text(f"SELECT MIN({quoted}), MAX({quoted}) FROM {full_name}")
                        row = conn.execute(agg_sql).fetchone()
                        min_val, max_val = row
                        # Convert non-serializable types
                        if min_val is not None and hasattr(min_val, "isoformat"):
                            min_val = min_val.isoformat()
                        if max_val is not None and hasattr(max_val, "isoformat"):
                            max_val = max_val.isoformat()
                        col.min_value = str(min_val) if min_val is not None else None
                        col.max_value = str(max_val) if max_val is not None else None
                    except Exception:
                        pass

    except Exception as e:
        warnings.warn(f"Profiling failed for {full_name}: {e}")

    return table


def _classify_pii(column: ColumnProfile) -> Tuple[Optional[str], Optional[float]]:
    """
    Detect PII using column-name heuristics + sample data regex.
    Returns (category, combined_confidence) or (None, None).
    """
    name_lower = column.name.lower().replace("_", " ").replace("-", " ")

    # 1. Column-name hint
    hint_category: Optional[str] = None
    hint_confidence: float = 0.0
    for keyword, (cat, conf) in COLUMN_NAME_PII_HINTS.items():
        if keyword in name_lower:
            if conf > hint_confidence:
                hint_category = cat
                hint_confidence = conf

    # 2. Sample data regex scan
    regex_category: Optional[str] = None
    regex_confidence: float = 0.0
    for sample in column.sample_values:
        if sample is None:
            continue
        sample_str = str(sample)
        for cat, pattern, base_conf in PII_PATTERNS:
            if re.search(pattern, sample_str, re.IGNORECASE):
                # Boost confidence if multiple samples match
                regex_confidence = base_conf
                regex_category = cat
                break
        if regex_confidence >= 0.9:
            break

    # 3. Combine: if both agree, boost confidence; if disagree, take lower
    if hint_category and regex_category:
        if hint_category == regex_category:
            return (hint_category, min(1.0, max(hint_confidence, regex_confidence) + 0.05))
        else:
            # conflicting signals — prefer regex for content-based matches
            return (regex_category, regex_confidence * 0.8 + hint_confidence * 0.2)
    elif hint_category:
        return (hint_category, hint_confidence * 0.8)  # lower confidence without sample confirmation
    elif regex_category:
        return (regex_category, regex_confidence)

    return (None, None)


def discover(config: ConnectionConfig) -> DiscoveryResult:
    """
    Main entry point: connect, introspect, profile, classify PII.
    """
    engine = _create_engine(config)
    warnings_list: List[str] = []

    try:
        tables = _introspect_tables(engine, config)

        if not tables:
            return DiscoveryResult(
                tables=[],
                warnings=["No tables found in the specified schema/connection"],
            )

        profiled: List[TableProfile] = []
        for table in tables:
            table = _profile_sample_data(engine, table, config.schema)
            for col in table.columns:
                pii_cat, pii_conf = _classify_pii(col)
                col.pii_category = pii_cat
                col.pii_confidence = pii_conf
            profiled.append(table)

        return DiscoveryResult(tables=profiled, warnings=warnings_list)

    except Exception as e:
        return DiscoveryResult(
            tables=[],
            warnings=[f"Discovery failed: {str(e)}"],
        )
    finally:
        engine.dispose()