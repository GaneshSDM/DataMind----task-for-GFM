"""
QUALITY Agent — Data quality validation engine.

Supports configurable quality rules:
  - no_nulls:<col>          Column must have no NULL values
  - unique:<col>            Column values must be unique
  - not_empty:<table>       Table must have at least 1 row
  - min:<col>:<val>         Column minimum must be >= val
  - max:<col>:<val>         Column maximum must be <= val
  - referential:<col>:<ref_table>:<ref_col>  Foreign-key style check
  - custom:<name>:<sql>     Custom SQL that returns 0 for pass, >0 for failure

Each rule generates a QualityCheck with passed/failed counts.
"""

from __future__ import annotations

import re
from typing import List, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from models import ConnectionConfig, QualityCheck, QualityResult

_RULE_PATTERN = re.compile(
    r"^(?P<rule>no_nulls|unique|not_empty|min|max|referential|custom)"
    r"(?::(?P<args>.+))?$",
    re.IGNORECASE,
)


def _create_engine(config: ConnectionConfig) -> Engine:
    return create_engine(config.connection_string, pool_pre_ping=True)


def _resolve_table(table: str, schema: Optional[str] = None) -> str:
    return f"{schema}.{table}" if schema else table


def _check_no_nulls(
    engine: Engine,
    full_table: str,
    column: str,
) -> QualityCheck:
    """Check that a column has no NULL values."""
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text(f"SELECT COUNT(*) FROM {full_table} WHERE \"{column}\" IS NULL")
            )
            null_count = result.scalar() or 0
            total = conn.execute(
                text(f"SELECT COUNT(*) FROM {full_table}")
            ).scalar() or 0
        return QualityCheck(
            rule="no_nulls",
            column=column,
            passed=null_count == 0,
            detail=f"Found {null_count} NULL values out of {total} rows" if null_count > 0
                   else f"All {total} rows have non-NULL values",
            rows_checked=total,
            rows_failed=null_count,
        )
    except Exception as e:
        return QualityCheck(
            rule="no_nulls", column=column, passed=False,
            detail=f"Check error: {str(e)}",
        )


def _check_unique(
    engine: Engine,
    full_table: str,
    column: str,
) -> QualityCheck:
    """Check that all values in a column are unique."""
    try:
        with engine.connect() as conn:
            total = conn.execute(
                text(f"SELECT COUNT(*) FROM {full_table}")
            ).scalar() or 0
            distinct = conn.execute(
                text(f"SELECT COUNT(DISTINCT \"{column}\") FROM {full_table}")
            ).scalar() or 0
            duplicates = total - distinct
        return QualityCheck(
            rule="unique",
            column=column,
            passed=duplicates == 0,
            detail=f"Found {duplicates} duplicate values out of {total} rows (distinct: {distinct})"
                   if duplicates > 0 else f"All {total} values are unique",
            rows_checked=total,
            rows_failed=duplicates,
        )
    except Exception as e:
        return QualityCheck(
            rule="unique", column=column, passed=False,
            detail=f"Check error: {str(e)}",
        )


def _check_not_empty(
    engine: Engine,
    full_table: str,
    _args: str = "",
) -> QualityCheck:
    """Check that a table has at least one row."""
    try:
        with engine.connect() as conn:
            count = conn.execute(
                text(f"SELECT COUNT(*) FROM {full_table}")
            ).scalar() or 0
        return QualityCheck(
            rule="not_empty",
            passed=count > 0,
            detail=f"Table contains {count} rows" if count > 0
                   else "Table is empty",
            rows_checked=1,
            rows_failed=0 if count > 0 else 1,
        )
    except Exception as e:
        return QualityCheck(
            rule="not_empty", passed=False,
            detail=f"Check error: {str(e)}",
        )


def _check_min(
    engine: Engine,
    full_table: str,
    args: str,
) -> QualityCheck:
    """Check that column minimum is >= threshold."""
    parts = args.split(":", 1)
    col = parts[0].strip()
    threshold = parts[1].strip() if len(parts) > 1 else "0"
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text(f"SELECT MIN(\"{col}\") FROM {full_table}")
            )
            min_val = result.scalar()
            passed = min_val is not None and min_val >= float(threshold)
        return QualityCheck(
            rule="min", column=col, passed=passed,
            detail=f"MIN({col}) = {min_val}, threshold = {threshold}",
        )
    except Exception as e:
        return QualityCheck(
            rule="min", column=col, passed=False,
            detail=f"Check error: {str(e)}",
        )


def _check_max(
    engine: Engine,
    full_table: str,
    args: str,
) -> QualityCheck:
    """Check that column maximum is <= threshold."""
    parts = args.split(":", 1)
    col = parts[0].strip()
    threshold = parts[1].strip() if len(parts) > 1 else "0"
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text(f"SELECT MAX(\"{col}\") FROM {full_table}")
            )
            max_val = result.scalar()
            passed = max_val is not None and max_val <= float(threshold)
        return QualityCheck(
            rule="max", column=col, passed=passed,
            detail=f"MAX({col}) = {max_val}, threshold = {threshold}",
        )
    except Exception as e:
        return QualityCheck(
            rule="max", column=col, passed=False,
            detail=f"Check error: {str(e)}",
        )


def _check_referential(
    engine: Engine,
    full_table: str,
    args: str,
) -> QualityCheck:
    """Check referential integrity: column values must exist in ref_table.ref_column."""
    parts = args.split(":", 2)
    col = parts[0].strip() if len(parts) >= 1 else ""
    ref_table = parts[1].strip() if len(parts) >= 2 else ""
    ref_col = parts[2].strip() if len(parts) >= 3 else col

    try:
        with engine.connect() as conn:
            orphan_sql = text(
                f"SELECT COUNT(*) FROM {full_table} t "
                f"WHERE t.\"{col}\" IS NOT NULL "
                f"AND t.\"{col}\" NOT IN (SELECT \"{ref_col}\" FROM {ref_table})"
            )
            orphan_count = conn.execute(orphan_sql).scalar() or 0
        return QualityCheck(
            rule="referential", column=col, passed=orphan_count == 0,
            detail=f"Found {orphan_count} orphan values in {col} (ref: {ref_table}.{ref_col})"
                   if orphan_count > 0 else f"All values in {col} exist in {ref_table}.{ref_col}",
            rows_failed=orphan_count,
        )
    except Exception as e:
        return QualityCheck(
            rule="referential", column=col, passed=False,
            detail=f"Check error: {str(e)}",
        )


def _check_custom(
    engine: Engine,
    full_table: str,
    args: str,
) -> QualityCheck:
    """Custom SQL check: result > 0 means failure."""
    parts = args.split(":", 1)
    check_name = parts[0].strip() if len(parts) >= 1 else "custom"
    custom_sql = parts[1].strip() if len(parts) >= 2 else "SELECT 0"
    try:
        with engine.connect() as conn:
            result = conn.execute(text(custom_sql))
            failed = result.scalar() or 0
        return QualityCheck(
            rule="custom", column=check_name, passed=failed == 0,
            detail=f"Custom check returned {failed} failures",
            rows_failed=failed,
        )
    except Exception as e:
        return QualityCheck(
            rule="custom", column=check_name, passed=False,
            detail=f"Check error: {str(e)}",
        )


_CHECK_DISPATCH = {
    "no_nulls":    _check_no_nulls,
    "unique":      _check_unique,
    "not_empty":   _check_not_empty,
    "min":         _check_min,
    "max":         _check_max,
    "referential": _check_referential,
    "custom":      _check_custom,
}


def run_quality_checks(
    config: ConnectionConfig,
    table: str,
    rules: List[str],
) -> QualityResult:
    """
    Execute quality checks against a table.

    Args:
        config: Target database connection config.
        table: Table name to validate.
        rules: List of rule strings, e.g. ["no_nulls:order_id", "unique:order_id"].

    Returns:
        QualityResult with per-check details and overall pass/warn/fail.
    """
    engine = _create_engine(config)
    full_table = _resolve_table(table, config.schema)
    checks: List[QualityCheck] = []

    try:
        for rule_str in rules:
            match = _RULE_PATTERN.match(rule_str.strip())
            if not match:
                checks.append(QualityCheck(
                    rule="unknown",
                    passed=False,
                    detail=f"Unrecognized rule format: {rule_str}",
                ))
                continue

            rule_name = match.group("rule").lower()
            rule_args = (match.group("args") or "").strip()

            checker = _CHECK_DISPATCH.get(rule_name)
            if not checker:
                checks.append(QualityCheck(
                    rule=rule_name, passed=False,
                    detail=f"No checker implemented for rule: {rule_name}",
                ))
                continue

            check_result = checker(engine, full_table, rule_args)
            checks.append(check_result)

    except Exception as e:
        checks.append(QualityCheck(
            rule="unknown", passed=False,
            detail=f"Quality check batch error: {str(e)}",
        ))
    finally:
        engine.dispose()

    # Determine overall status
    failures = [c for c in checks if not c.passed]
    if not failures:
        overall = "pass"
        summary = f"All {len(checks)} checks passed"
    elif len(failures) <= len(checks) * 0.3:
        overall = "warn"
        summary = f"{len(failures)}/{len(checks)} checks failed"
    else:
        overall = "fail"
        summary = f"{len(failures)}/{len(checks)} checks failed"

    return QualityResult(checks=checks, overall=overall, summary=summary)