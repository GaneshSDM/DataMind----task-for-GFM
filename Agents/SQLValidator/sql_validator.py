# =============================================================================
#   V A L K Y R I E -Validation and Logical Knowledge Yielding Rigorous Intelligent Execution
# =============================================================================
#
#   "I stand between creation and execution, judging every query that seeks passage."
#   I inspect each statement for accuracy, compliance, and logical integrity.
#   I challenge assumptions, uncover flaws, and reject what cannot be trusted.
#   I uphold the laws of governance, security, and data correctness without compromise.
#   Only the worthy SQL shall pass beyond my watch.
# =============================================================================


"""
SQL Validator — enforces Row-Level Security (RLS) and Column-Level Security (CLS).

Given user identity + SQL query, determines:
- Which columns the user can access (CLS)
- Which WHERE predicates must be applied (RLS)
- Date constraint violations
- Overall pass/fail verdict
"""

import json
import re
import logging
from datetime import date, datetime
from typing import Optional

from groq_client import GroqClient, get_query_fingerprint

logger = logging.getLogger(__name__)

# ─── SQL Parsing Helpers (lightweight, no external deps) ───


def _check_syntax(sql: str) -> list[dict]:
    """Lightweight SQL syntax check — catches structural errors."""
    errors = []
    s = sql.strip()

    # Empty query
    if not s:
        errors.append({"type": "SYNTAX", "detail": "Empty query", "fix": "Provide a SQL statement"})
        return errors

    # Must start with SELECT
    if not re.match(r"^\s*SELECT\b", s, re.IGNORECASE):
        errors.append({"type": "SYNTAX", "detail": "Query must start with SELECT", "fix": "Only SELECT statements are supported"})

    # Must have FROM
    if not re.search(r"\bFROM\b", s, re.IGNORECASE):
        errors.append({"type": "SYNTAX", "detail": "Missing FROM clause", "fix": "Add 'FROM table_name' after SELECT columns"})

    # Unbalanced parentheses
    depth = 0
    for i, ch in enumerate(s):
        if ch == "(": depth += 1
        elif ch == ")": depth -= 1
        if depth < 0:
            errors.append({"type": "SYNTAX", "detail": f"Unbalanced parentheses: unexpected ')' at position {i}", "fix": "Check your parentheses"})
            break
    if depth > 0:
        errors.append({"type": "SYNTAX", "detail": f"Unbalanced parentheses: {depth} unclosed '('", "fix": "Close all open parentheses"})

    # Unterminated single-quoted string
    in_single = False
    for ch in s:
        if ch == "'" and not in_single:
            in_single = True
        elif ch == "'" and in_single:
            in_single = False
    if in_single:
        errors.append({"type": "SYNTAX", "detail": "Unterminated string literal (missing closing ')", "fix": "Close the string with a single quote"})

    # Double semicolons
    if ";;" in s:
        errors.append({"type": "SYNTAX", "detail": "Double semicolons found", "fix": "Use a single semicolon or remove it"})

    # Table alias applied to a numeric literal (e.g. mc.0.05, t1.3.14)
    # LLMs sometimes prefix float/int literals with a table alias — always invalid SQL.
    alias_on_literal = re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\.(\d)", s)
    for alias, digit in alias_on_literal:
        errors.append({
            "type": "SYNTAX",
            "detail": f"Table alias '{alias}' incorrectly applied to a numeric literal (e.g. '{alias}.{digit}...'). Numeric literals must not be prefixed with a table alias.",
            "fix": f"Remove the '{alias}.' prefix from the numeric literal — use the bare number (e.g. 0.05, not {alias}.0.05)",
        })

    # SELECT * FROM with no safety (just a warning, not an error)
    if re.search(r"SELECT\s+\*", s, re.IGNORECASE):
        errors.append({"type": "WARNING", "detail": "SELECT * is discouraged — explicitly list columns for security review", "fix": "Replace * with explicit column names"})

    # Missing semicolons (not an error, but note it)
    if not s.rstrip().endswith(";"):
        pass  # acceptable, just noting

    # ── Undefined table alias / qualifier check ──────────────────────────────
    # Collect all aliases and schema prefixes defined in FROM / JOIN / CTEs.
    # Flag any  x.y  reference where x is neither a known alias nor a schema prefix.
    _defined: set[str] = set()
    _schemas: set[str] = set()

    # FROM [schema.]table[ [AS] alias]
    for _m in re.finditer(
        r'\bFROM\b\s+((?:\w+\.)*\w+)(?:\s+(?:AS\s+)?(\w+))?',
        s, re.IGNORECASE,
    ):
        _parts = _m.group(1).split('.')
        _defined.add(_parts[-1].lower())
        if len(_parts) > 1:
            _schemas.add(_parts[0].lower())
        _alias = _m.group(2)
        if _alias and _alias.upper() not in (
            'WHERE', 'GROUP', 'ORDER', 'HAVING', 'LIMIT',
            'UNION', 'JOIN', 'LEFT', 'RIGHT', 'INNER', 'OUTER',
            'CROSS', 'ON', 'SET', 'WITH',
        ):
            _defined.add(_alias.lower())

    # JOIN [schema.]table[ [AS] alias]
    for _m in re.finditer(
        r'\bJOIN\b\s+((?:\w+\.)*\w+)(?:\s+(?:AS\s+)?(\w+))?',
        s, re.IGNORECASE,
    ):
        _parts = _m.group(1).split('.')
        _defined.add(_parts[-1].lower())
        if len(_parts) > 1:
            _schemas.add(_parts[0].lower())
        _alias = _m.group(2)
        if _alias and _alias.upper() not in ('ON', 'WHERE', 'GROUP', 'ORDER', 'HAVING'):
            _defined.add(_alias.lower())

    # WITH cte_name AS (...)  and  , cte_name AS (...)
    for _m in re.finditer(r'(?:\bWITH\b|,)\s*(\w+)\s+AS\s*\(', s, re.IGNORECASE):
        _defined.add(_m.group(1).lower())

    # Flag any qualifier.column reference whose qualifier is unknown
    _seen_undef: set[str] = set()
    for _m in re.finditer(r'\b(\w+)\.(\w+)\b', s, re.IGNORECASE):
        _ref = _m.group(1).lower()
        if _ref not in _defined and _ref not in _schemas and _ref not in _seen_undef:
            _seen_undef.add(_ref)
            errors.append({
                "type": "SYNTAX",
                "detail": (
                    f"Undefined table alias or reference: '{_m.group(1)}'. "
                    f"All qualifier.column references must use an alias or table name "
                    f"declared in the FROM or JOIN clause."
                ),
                "fix": (
                    f"Replace '{_m.group(1)}.' with the correct alias defined in FROM/JOIN, "
                    f"or add a JOIN for '{_m.group(1)}' if a new table is intended."
                ),
            })

    return errors


def _extract_columns_from_select(sql: str) -> list[str]:
    """Extract column names from SELECT clause."""
    sql = sql.strip().rstrip(";")
    # Handle SELECT * or SELECT column1, column2 ...
    m = re.search(
        r"\bSELECT\s+(.*?)\s+FROM\b",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return []
    cols_raw = m.group(1).strip()
    if cols_raw == "*":
        return ["*"]
    # Split by commas, but respect parentheses for functions
    cols = []
    depth = 0
    current = ""
    for ch in cols_raw:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            cols.append(current.strip())
            current = ""
        else:
            current += ch
    if current.strip():
        cols.append(current.strip())
    return cols


def _normalize_column_name(raw: str) -> str:
    """Strip table prefix and aliases: 't.salary' -> 'salary', 'salary AS s' -> 'salary'."""
    raw = raw.strip()
    # Remove AS alias
    raw = re.sub(r"\s+AS\s+\S+$", "", raw, flags=re.IGNORECASE)
    # Strip table prefix
    if "." in raw:
        parts = raw.split(".")
        raw = parts[-1]
    # Remove function wrapping: COUNT(salary) -> salary
    m = re.match(r"\w+\((.+)\)", raw)
    if m:
        raw = m.group(1)
    return raw.strip()


def _extract_table_names(sql: str) -> list[str]:
    """Extract table names from FROM and JOIN clauses."""
    tables = set()
    # Simple FROM match
    for m in re.finditer(
        r"\bFROM\s+(\w+)", sql, re.IGNORECASE
    ):
        tables.add(m.group(1))
    # JOIN matches
    for m in re.finditer(
        r"\bJOIN\s+(\w+)", sql, re.IGNORECASE
    ):
        tables.add(m.group(1))
    return list(tables)


def _has_where_clause(sql: str) -> bool:
    """Check if query has a WHERE clause."""
    return bool(re.search(r"\bWHERE\b", sql, re.IGNORECASE))


def _find_date_comparisons(sql: str) -> list[dict]:
    """Find date column comparisons in the query."""
    results = []
    # Pattern: date_column OP 'value' or date_column OP value
    for m in re.finditer(
        r"(\w+)\s*(=|>=|<=|>|<|<>|!=|BETWEEN)\s*('[^']*'|\d{4}-\d{2}-\d{2}|CURRENT_DATE|NOW\(\))",
        sql,
        re.IGNORECASE,
    ):
        col = m.group(1).lower()
        # Skip non-date columns (heuristic: ends with _date, _at, _year)
        if any(
            col.endswith(suffix)
            for suffix in ("_date", "_at", "_year", "date")
        ):
            results.append({
                "column": col,
                "operator": m.group(2),
                "value": m.group(3).strip("'"),
            })
    return results


# ─── Schema Loader ───


class SchemaStore:
    """Loads and queries domain schema + RLS/CLS rules from config."""

    def __init__(
        self, schema_path: str = "schemas/domain_schema.json", config_path: str = "config.yaml"
    ):
        import yaml

        with open(schema_path) as f:
            self.schema = json.load(f)
        with open(config_path) as f:
            self.config = yaml.safe_load(f)

        self.rls = self.config.get("row_level_security", {})
        self.cls = self.config.get("column_level_security", {})
        self.date_constraints = self.config.get("date_constraints", {})

        # Build column -> table mapping
        self._column_to_table: dict[str, str] = {}
        for domain, d_info in self.schema["domains"].items():
            for subdomain, sd_info in d_info["subdomains"].items():
                for col in sd_info["columns"]:
                    self._column_to_table[col] = sd_info["table"]

    def get_table_for_column(self, column: str) -> Optional[str]:
        return self._column_to_table.get(column)

    def get_columns_for_domain(
        self, domain: str, subdomain: str
    ) -> list[str]:
        """Get all columns for a domain/subdomain."""
        try:
            return self.schema["domains"][domain]["subdomains"][subdomain][
                "columns"
            ]
        except KeyError:
            return []

    def get_sensitive_columns(
        self, domain: str, subdomain: str
    ) -> list[str]:
        """Get sensitive columns for a domain/subdomain."""
        try:
            return self.schema["domains"][domain]["subdomains"][subdomain][
                "sensitive_columns"
            ]
        except KeyError:
            return []

    def resolve_domain_from_table(self, table_name: str) -> Optional[tuple]:
        """Given a table name, return (domain, subdomain)."""
        for domain, d_info in self.schema["domains"].items():
            for subdomain, sd_info in d_info["subdomains"].items():
                if sd_info["table"] == table_name:
                    return (domain, subdomain)
        return None

    def get_allowed_columns(
        self, role: str, domain: str, subdomain: str = "*"
    ) -> list[str]:
        """Get columns allowed for a role in a domain/subdomain."""
        cls_rules = self.cls.get(role, {})

        # Try exact domain.subdomain match
        key = f"{domain}.{subdomain}"
        if key in cls_rules:
            result = cls_rules[key]
            if result == "*":
                return self.get_columns_for_domain(domain, subdomain)
            return result

        # Try domain.* wildcard
        key = f"{domain}.*"
        if key in cls_rules:
            result = cls_rules[key]
            if result == "*":
                # Gather all columns across all subdomains
                all_cols = []
                for sd in self.schema["domains"][domain]["subdomains"]:
                    all_cols.extend(self.get_columns_for_domain(domain, sd))
                return all_cols
            return result

        # Try global wildcard
        if "*" in cls_rules:
            result = cls_rules["*"]
            if result == "*":
                return self.get_columns_for_domain(domain, subdomain)
            return result

        return []  # nothing allowed by default

    def get_rls_predicates(self, role: str) -> list[str]:
        """Get RLS predicates for a role."""
        return self.rls.get(role, ["1=0"])  # default: deny all

    def check_date_constraints(
        self, column: str, value: str
    ) -> list[dict]:
        """Check all date constraints against a column+value pair. Returns violations."""
        violations = []
        for constraint in self.date_constraints.get("global", []):
            if column in constraint.get("columns", []):
                rule_name = constraint["description"]
                # Simple heuristic checks
                if constraint["rule"] == "no_future_birth":
                    try:
                        d = date.fromisoformat(value)
                        if d > date.today():
                            violations.append({
                                "column": column,
                                "rule": rule_name,
                                "value": value,
                                "issue": "Date is in the future",
                            })
                    except (ValueError, TypeError):
                        pass
                elif constraint["rule"] == "no_future_create":
                    try:
                        dt = datetime.fromisoformat(value)
                        if dt > datetime.now():
                            violations.append({
                                "column": column,
                                "rule": rule_name,
                                "value": value,
                                "issue": "Timestamp is in the future",
                            })
                    except (ValueError, TypeError):
                        pass
                elif constraint["rule"] == "reasonable_age":
                    try:
                        d = date.fromisoformat(value)
                        age = (date.today() - d).days / 365.25
                        if age < 18:
                            violations.append({
                                "column": column,
                                "rule": rule_name,
                                "value": value,
                                "issue": f"Age {age:.0f} is under 18",
                            })
                        elif age > 120:
                            violations.append({
                                "column": column,
                                "rule": rule_name,
                                "value": value,
                                "issue": f"Age {age:.0f} exceeds 120",
                            })
                    except (ValueError, TypeError):
                        pass
        return violations


# ─── Main Validator ───


class SQLValidator:
    """Core validation engine."""

    def __init__(self, schema_store: SchemaStore):
        self.schema = schema_store

    def validate(
        self,
        sql: str,
        user_id: str,
        role: str,
        tenant_id: str = "default",
        domain: str = "",
        subdomain: str = "",
        use_groq: bool = False,
        groq_client: GroqClient = None,
    ) -> dict:
        """
        Validate a SQL query against RLS, CLS, and date constraints.

        Returns a dict with:
        - fingerprint
        - user: {id, role, tenant}
        - domain, subdomain
        - status: pass | fail | warn
        - cls_checks: list of column checks
        - rls_checks: list of row-level checks
        - date_checks: list of date constraint checks
        - groq_analysis (if use_groq)
        - violations: list of all violations
        - recommendations: list of fix suggestions
        """
        fingerprint = get_query_fingerprint(sql)
        violations = []
        recommendations = []
        date_checks = []

        # ── 0. Syntax check ──
        syntax_errors = _check_syntax(sql)
        for se in syntax_errors:
            violations.append(se)

        # ── 1. Determine domain from table references ──
        tables = _extract_table_names(sql)
        resolved_domains = []
        for tbl in tables:
            res = self.schema.resolve_domain_from_table(tbl)
            if res:
                resolved_domains.append(res)

        if not domain and resolved_domains:
            domain, subdomain = resolved_domains[0]

        # ── 2. CLS: Column-level security check ──
        cls_checks = []
        extracted_cols = _extract_columns_from_select(sql)
        normalized_cols = [_normalize_column_name(c) for c in extracted_cols]

        # Determine which columns user is allowed to see
        allowed_cols = set()
        if domain and subdomain:
            allowed = self.schema.get_allowed_columns(role, domain, subdomain)
            allowed_cols.update(allowed)
        else:
            # Cross-domain: check all resolved
            for d, sd in resolved_domains:
                allowed = self.schema.get_allowed_columns(role, d, sd)
                allowed_cols.update(allowed)

        blocked_cols = []
        if "*" not in normalized_cols:
            for col in normalized_cols:
                # Skip function-like expressions, literals, aliases
                if col in ("*", "1", "") or "(" in col:
                    continue
                if col not in allowed_cols:
                    blocked_cols.append(col)

        cls_checks.append({
            "allowed_columns": sorted(allowed_cols) if len(allowed_cols) < 30 else f"{len(allowed_cols)} columns",
            "referenced_columns": [c for c in normalized_cols if c != "*"],
            "blocked_columns": blocked_cols,
        })

        if blocked_cols:
            for bc in blocked_cols:
                violations.append({
                    "type": "CLS",
                    "detail": f"Column '{bc}' is blocked for role '{role}'",
                    "fix": f"Remove '{bc}' from SELECT or request elevated access",
                })

        # ── 3. RLS: Row-level security check ──
        rls_checks = []
        rls_predicates = self.schema.get_rls_predicates(role)

        # Substitute placeholders
        resolved_predicates = []
        for pred in rls_predicates:
            resolved = pred.replace(
                ":user_id", str(user_id) if user_id.isdigit() else f"'{user_id}'"
            )
            resolved = resolved.replace(":user_tenant_id", f"'{tenant_id}'")
            resolved = resolved.replace(":user_department_id", "(SELECT department_id FROM users WHERE id = " + (user_id if user_id.isdigit() else f"'{user_id}'") + ")")
            resolved_predicates.append(resolved)

        rls_checks.append({
            "role_rules": rls_predicates,
            "resolved_predicates": resolved_predicates,
        })

        # Check if WHERE clause exists and covers RLS requirements
        if not _has_where_clause(sql):
            if rls_predicates and rls_predicates != ["1=1"]:
                violations.append({
                    "type": "RLS",
                    "detail": "Query has no WHERE clause but RLS predicates are required",
                    "fix": f"Add WHERE clause with: {' AND '.join(resolved_predicates[:2])}",
                })
                recommendations.append(
                    "Add WHERE clause to enforce row-level security"
                )

        # ── 4. Date constraints ──
        date_comparisons = _find_date_comparisons(sql)
        for dc in date_comparisons:
            violation_list = self.schema.check_date_constraints(
                dc["column"], dc["value"]
            )
            if violation_list:
                date_checks.append({
                    "column": dc["column"],
                    "value": dc["value"],
                    "violations": violation_list,
                })
                for v in violation_list:
                    violations.append({
                        "type": "DATE",
                        "detail": f"{v['column']}: {v['issue']} ({v['rule']})",
                        "fix": f"Adjust {v['column']} to satisfy: {v['rule']}",
                    })

        # ── 5. Groq LLM analysis (optional) ──
        groq_analysis = None
        if use_groq and groq_client:
            try:
                schema_context = {
                    "allowed_columns": list(allowed_cols),
                    "rls_predicates": resolved_predicates,
                    "domain": domain,
                    "subdomain": subdomain,
                }
                groq_analysis = groq_client.validate_permissions(
                    sql,
                    {"user_id": user_id, "role": role, "tenant_id": tenant_id},
                    schema_context,
                )
                # Merge Groq violations
                for bc in groq_analysis.get("blocked_columns", []):
                    if bc not in [v["detail"] for v in violations]:
                        violations.append({
                            "type": "CLS (Groq)",
                            "detail": f"LLM detected blocked column: {bc}",
                            "fix": f"Remove '{bc}' from query",
                        })
                for mf in groq_analysis.get("missing_filters", []):
                    violations.append({
                        "type": "RLS (Groq)",
                        "detail": f"Missing filter: {mf}",
                        "fix": f"Add: {mf}",
                    })
            except Exception as e:
                logger.warning(f"Groq analysis skipped: {e}")

        # ── 6. Determine verdict ──
        # WARNING-type violations are advisory only — don't fail the query
        hard_violations = [v for v in violations if v.get("type") != "WARNING"]
        if hard_violations:
            status = "fail"
            verdict_reason = "Query has hard violations that must be fixed before execution"
        elif violations:
            status = "warn"
            verdict_reason = "Query passes security checks but has advisories (e.g. SELECT *)"
        else:
            status = "pass"
            verdict_reason = "Query passes all RLS, CLS, syntax, and date checks"

        return {
            "fingerprint": fingerprint,
            "user": {"id": user_id, "role": role, "tenant": tenant_id},
            "domain": domain,
            "subdomain": subdomain,
            "status": status,
            "verdict_reason": verdict_reason,
            "cls_checks": cls_checks,
            "rls_checks": rls_checks,
            "date_checks": date_checks,
            "groq_analysis": groq_analysis,
            "violations": violations,
            "recommendations": recommendations,
        }

    def format_report(self, result: dict) -> str:
        """Format validation result as a readable report."""
        lines = []
        sep = "=" * 60

        lines.append(sep)
        lines.append("SQL VALIDATION REPORT")
        lines.append(sep)
        lines.append(
            f"User:        {result['user']['id']} | Role: {result['user']['role']} | Tenant: {result['user']['tenant']}"
        )
        lines.append(
            f"Domain:      {result['domain']} / {result['subdomain']}"
        )
        lines.append(f"Query Hash:  {result['fingerprint']}")
        lines.append("")

        # Status banner
        status = result["status"].upper()
        if status == "PASS":
            lines.append(f"STATUS:  \033[92m✓ PASS\033[0m")
        elif status == "FAIL":
            lines.append(f"STATUS:  \033[91m✗ FAIL\033[0m")
        else:
            lines.append(f"STATUS:  \033[93m⚠ WARN\033[0m")
        lines.append("")

        # Violations
        if result["violations"]:
            lines.append("--- Violations ---")
            for i, v in enumerate(result["violations"], 1):
                lines.append(
                    f"[{i}] Type: {v['type']} | Detail: {v['detail']}"
                )
                lines.append(f"    Fix: {v['fix']}")
            lines.append("")

        # Date checks
        if result["date_checks"]:
            lines.append("--- Date Constraints ---")
            for dc in result["date_checks"]:
                lines.append(f"  Column: {dc['column']} = {dc['value']}")
                for v in dc["violations"]:
                    lines.append(f"  → {v['issue']}  [{v['rule']}]")
            lines.append("")

        # CLS
        lines.append("--- Column-Level Security ---")
        for cls in result["cls_checks"]:
            allowed = cls["allowed_columns"]
            if isinstance(allowed, list):
                lines.append(
                    f"  Allowed:      {', '.join(allowed[:15])}{'...' if len(allowed) > 15 else ''}"
                )
            else:
                lines.append(f"  Allowed:      {allowed}")
            refs = cls["referenced_columns"]
            lines.append(
                f"  Referenced:   {', '.join(refs) if refs else '(none found)'}"
            )
            blocked = cls["blocked_columns"]
            if blocked:
                lines.append(f"  Blocked:      {', '.join(blocked)}")
            else:
                lines.append("  Blocked:      (none)")
        lines.append("")

        # RLS
        lines.append("--- Row-Level Security ---")
        for rls in result["rls_checks"]:
            lines.append(f"  Role Rules:   {' AND '.join(rls['role_rules'])}")
            lines.append(
                f"  Resolved:     {' AND '.join(rls['resolved_predicates'])}"
            )
        lines.append("")

        # Recommendations
        if result["recommendations"]:
            lines.append("--- Recommendations ---")
            for r in result["recommendations"]:
                lines.append(f"  → {r}")
            lines.append("")

        # Groq analysis
        if result.get("groq_analysis"):
            lines.append("--- Groq LLM Analysis ---")
            lines.append(f"  Verdict: {result['groq_analysis'].get('verdict', 'N/A')}")
            lines.append(f"  Reason:  {result['groq_analysis'].get('reason', 'N/A')}")
            lines.append("")

        # Summary
        lines.append("--- Summary ---")
        if result["status"] == "pass":
            lines.append(
                "Verdict: PASS — Query complies with all security policies."
            )
        elif result["status"] == "fail":
            lines.append(
                f"Verdict: FAIL — {len(result['violations'])} violation(s) found."
            )
            lines.append(
                "Fix the violations above before executing this query."
            )
        lines.append(sep)

        return "\n".join(lines)
