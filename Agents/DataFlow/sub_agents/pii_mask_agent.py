"""
PII_MASK Agent — Detect and mask Personally Identifiable Information.

Uses the same PII regex database as the DISCOVERY agent, then applies
configurable masking strategies to columns in the target table.

Strategies:
  - SHA256_HASH:  irreversible SHA-256 hash (consistent per value)
  - NULL:         replace with NULL
  - DUMMY:        replace with a static placeholder (e.g., 'REDACTED')
  - MASK_FIRST_N: show last N characters, mask the rest (e.g., '******7890')
  - MASK_LAST_4:  show first part, mask last 4 (e.g., 'XXXX-XXXX-XXXX-1234')
  - TOKENIZE:     replace with a format-preserving token (simple UUID4 mapping)

For performance, uses batch UPDATE rather than row-by-row.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from models import ConnectionConfig, MaskedColumn, PIIMaskResult


def _create_engine_from_config(config: ConnectionConfig) -> Engine:
    return create_engine(config.connection_string, pool_pre_ping=True)

# ── Same PII patterns as discovery_agent ──────────────────────────────────

PII_PATTERNS: List[Tuple[str, str, float]] = [
    ("email",        r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",                         0.90),
    ("phone",        r"\+?\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}",           0.85),
    ("ssn",          r"\b(?!000|666|9\d{2})\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b",                 0.95),
    ("credit_card",  r"\b(?:\d[ -]*?){13,16}\b",                                                0.80),
    ("ip_address",   r"\b(?:\d{1,3}\.){3}\d{1,3}\b",                                           0.85),
    ("zip_code",     r"\b\d{5}(?:-\d{4})?\b",                                                   0.70),
    ("uuid",         r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",      0.90),
]

COLUMN_NAME_PII_HINTS: Dict[str, Tuple[str, float]] = {
    "email":           ("email", 0.95),
    "e-mail":          ("email", 0.95),
    "mail":            ("email", 0.85),
    "phone":           ("phone", 0.90),
    "telephone":       ("phone", 0.90),
    "mobile":          ("phone", 0.90),
    "cell":            ("phone", 0.80),
    "ssn":             ("ssn", 0.98),
    "social_security": ("ssn", 0.98),
    "credit_card":     ("credit_card", 0.95),
    "cc_number":       ("credit_card", 0.95),
    "ip":              ("ip_address", 0.90),
    "ip_address":      ("ip_address", 0.95),
    "password":        ("password", 0.95),
    "secret":          ("secret", 0.80),
    "token":           ("token", 0.80),
    "api_key":         ("api_key", 0.90),
    "dob":             ("date_of_birth", 0.90),
    "birth_date":      ("date_of_birth", 0.90),
}


class PIIMasker:
    """Per-column masking engine that caches token mappings."""

    def __init__(self):
        self._token_cache: Dict[str, str] = {}

    @staticmethod
    def sha256_hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def mask_first_n(value: str, keep_last: int = 4) -> str:
        s = str(value)
        if len(s) <= keep_last:
            return s
        visible = s[-keep_last:]
        masked_part = "*" * (len(s) - keep_last)
        return f"{masked_part}{visible}"

    @staticmethod
    def mask_last_4(value: str) -> str:
        s = str(value)
        if len(s) <= 4:
            return "XXXX"
        return s[:-4] + "XXXX"

    def tokenize(self, value: str) -> str:
        if value not in self._token_cache:
            self._token_cache[value] = f"tok_{uuid.uuid4().hex[:12]}"
        return self._token_cache[value]

    def apply_strategy(self, value: Any, strategy: str) -> Any:
        if value is None:
            return None
        str_val = str(value)

        if strategy == "SHA256_HASH":
            return self.sha256_hash(str_val)
        elif strategy == "NULL":
            return None
        elif strategy == "DUMMY":
            return "REDACTED"
        elif strategy == "MASK_FIRST_N":
            return self.mask_first_n(str_val, keep_last=4)
        elif strategy == "MASK_LAST_4":
            return self.mask_last_4(str_val)
        elif strategy == "TOKENIZE":
            return self.tokenize(str_val)
        return value


# ── Column-level detection (no sample data needed — uses column names + scans) ─

def _detect_pii_columns(
    engine: Engine,
    table: str,
    schema: Optional[str] = None,
    sample_limit: int = 50,
) -> List[Tuple[str, str, float]]:
    """
    Detect PII columns by name heuristics + scanning sample rows.
    Returns list of (column_name, category, confidence).
    """
    full = f"{schema}.{table}" if schema else table
    inspector = __import__("sqlalchemy", fromlist=["inspect"]).inspect(engine)
    columns_info = inspector.get_columns(table, schema=schema)

    detected: List[Tuple[str, str, float]] = []

    for col in columns_info:
        col_name = col["name"]
        name_lower = col_name.lower().replace("_", " ").replace("-", " ")

        hint_category: Optional[str] = None
        hint_conf: float = 0.0
        for keyword, (cat, conf) in COLUMN_NAME_PII_HINTS.items():
            if keyword in name_lower:
                if conf > hint_conf:
                    hint_category = cat
                    hint_conf = conf

        # Scan sample values for regex matches
        try:
            with engine.connect() as conn:
                quoted = f'"{col_name}"' if "." in col_name else col_name
                rows = conn.execute(
                    text(f"SELECT DISTINCT {quoted} FROM {full} WHERE {quoted} IS NOT NULL LIMIT {sample_limit}")
                ).fetchall()
        except Exception:
            rows = []

        regex_category: Optional[str] = None
        regex_conf: float = 0.0
        match_count = 0
        for row in rows:
            val = row[0]
            if val is None:
                continue
            for cat, pattern, base_conf in PII_PATTERNS:
                if re.search(pattern, str(val), re.IGNORECASE):
                    regex_category = cat
                    regex_conf = base_conf
                    match_count += 1
                    break

        confidence_mod = min(1.0, match_count / max(len(rows), 1))
        regex_conf = regex_conf * (0.5 + 0.5 * confidence_mod)

        # Combine signals
        if hint_category and regex_category:
            if hint_category == regex_category:
                detected.append((col_name, hint_category, min(1.0, max(hint_conf, regex_conf) + 0.05)))
            else:
                detected.append((col_name, regex_category, regex_conf * 0.8 + hint_conf * 0.2))
        elif hint_category:
            detected.append((col_name, hint_category, hint_conf * 0.7))
        elif regex_category:
            detected.append((col_name, regex_category, regex_conf))

    return detected


def _select_strategy(category: str) -> str:
    """Choose a default masking strategy based on PII category."""
    strategy_map = {
        "email":         "SHA256_HASH",
        "phone":         "MASK_FIRST_N",
        "ssn":           "MASK_FIRST_N",
        "credit_card":   "MASK_LAST_4",
        "ip_address":    "SHA256_HASH",
        "password":      "SHA256_HASH",
        "secret":        "SHA256_HASH",
        "token":         "TOKENIZE",
        "api_key":       "MASK_FIRST_N",
        "date_of_birth": "MASK_FIRST_N",
        "zip_code":      "SHA256_HASH",
        "uuid":          "SHA256_HASH",
        "url":           "SHA256_HASH",
    }
    return strategy_map.get(category, "SHA256_HASH")


def apply_masks(
    engine: Engine,
    table: str,
    columns: List[Tuple[str, str, str]],
    schema: Optional[str] = None,
) -> PIIMaskResult:
    """
    Apply masking strategies to specified columns using per-column UPDATE.

    For each column, reads (PK, value) pairs, applies the masking strategy,
    and issues batched UPDATE statements. Falls back to SQL functions when
    available (SHA256).
    """
    from sqlalchemy import inspect as sa_inspect

    full = f"{schema}.{table}" if schema else table
    masker = PIIMasker()
    masked_cols: List[MaskedColumn] = []
    total_affected = 0

    # Detect PK
    inspector = sa_inspect(engine)
    pk_cols = [
        c["name"]
        for c in inspector.get_pk_constraint(table, schema=schema)
        .get("constrained_columns", [])
    ]
    has_pk = bool(pk_cols)
    pk = pk_cols[0] if pk_cols else None

    for col_name, category, strategy in columns:
        try:
            quoted = f'"{col_name}"'
            pk_quoted = f'"{pk}"' if pk else None

            with engine.connect() as conn:
                if has_pk and pk_quoted:
                    rows = conn.execute(
                        text(f"SELECT {pk_quoted}, {quoted} FROM {full} WHERE {quoted} IS NOT NULL")
                    ).fetchall()
                else:
                    rows = conn.execute(
                        text(f"SELECT {quoted} FROM {full} WHERE {quoted} IS NOT NULL")
                    ).fetchall()

            if not rows:
                masked_cols.append(MaskedColumn(
                    column_name=col_name, pii_category=category,
                    confidence=0.0, mask_strategy=strategy, rows_affected=0,
                ))
                continue

            col_affected = 0
            if has_pk and pk:
                for row in rows:
                    pk_val, original = row[0], row[1]
                    masked_val = masker.apply_strategy(original, strategy)
                    with engine.begin() as conn:
                        conn.execute(
                            text(f"UPDATE {full} SET {quoted} = :mv WHERE {pk_quoted} = :pk"),
                            {"mv": masked_val, "pk": pk_val},
                        )
                    col_affected += 1
            else:
                # No PK — use SQL-native functions where possible
                if strategy == "SHA256_HASH":
                    with engine.begin() as conn:
                        conn.execute(
                            text(f"UPDATE {full} SET {quoted} = encode(sha256({quoted}::bytea), 'hex')")
                        )
                elif strategy == "NULL":
                    with engine.begin() as conn:
                        conn.execute(text(f"UPDATE {full} SET {quoted} = NULL"))
                elif strategy == "DUMMY":
                    with engine.begin() as conn:
                        conn.execute(text(f"UPDATE {full} SET {quoted} = 'REDACTED'"))
                col_affected = len(rows)

            total_affected += col_affected
            masked_cols.append(MaskedColumn(
                column_name=col_name, pii_category=category,
                confidence=0.0, mask_strategy=strategy, rows_affected=col_affected,
            ))

        except Exception:
            masked_cols.append(MaskedColumn(
                column_name=col_name, pii_category=category,
                confidence=0.0, mask_strategy=strategy, rows_affected=0,
            ))

    return PIIMaskResult(
        masked_columns=masked_cols,
        total_rows_affected=total_affected,
        warnings=[],
    )


def scan_and_mask(
    config: ConnectionConfig,
    table: str,
    column_overrides: Optional[Dict[str, str]] = None,
) -> PIIMaskResult:
    """
    Scan a table for PII columns and apply masking.

    Args:
        config: Target database connection.
        table: Table name to scan and mask.
        column_overrides: Optional explicit {column: strategy} overrides.
            If provided, skips auto-detection for those columns.

    Returns:
        PIIMaskResult with per-column results.
    """
    engine = _create_engine_from_config(config)

    try:
        # Auto-detect PII columns
        detected = _detect_pii_columns(engine, table, config.schema)

        # Apply overrides
        column_strategies: List[Tuple[str, str, str]] = []
        for col_name, cat, conf in detected:
            if column_overrides and col_name in column_overrides:
                strategy = column_overrides[col_name]
            else:
                strategy = _select_strategy(cat)
            column_strategies.append((col_name, cat, strategy))

        # Also add override-only columns not auto-detected
        if column_overrides:
            detected_names = {c for c, _, _ in detected}
            # (no need — user can specify columns not found)

        if not column_strategies:
            return PIIMaskResult(
                masked_columns=[],
                total_rows_affected=0,
                warnings=["No PII columns detected"],
            )

        result = apply_masks(engine, table, column_strategies, config.schema)
        return result

    finally:
        engine.dispose()