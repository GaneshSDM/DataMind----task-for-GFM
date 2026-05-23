"""
Tests for SQL Validator Agent.
Run: python -m pytest tests/ -v
"""

import sys
import os
import json
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sql_validator import (
    SQLValidator,
    SchemaStore,
    _extract_columns_from_select,
    _normalize_column_name,
    _extract_table_names,
    _has_where_clause,
    _find_date_comparisons,
    get_query_fingerprint,
)
from synthetic_data import (
    generate,
    GENERATORS,
    generate_finance_budgets,
    generate_hr_employees,
    generate_sales_deals,
    generate_support_tickets,
    generate_eng_bugs,
)


@pytest.fixture
def schema():
    base = os.path.dirname(os.path.dirname(__file__))
    return SchemaStore(
        schema_path=os.path.join(base, "schemas", "domain_schema.json"),
        config_path=os.path.join(base, "config.yaml"),
    )


@pytest.fixture
def validator(schema):
    return SQLValidator(schema)


# ─── Schema Tests ───


class TestSchemaStore:
    def test_loads_domains(self, schema):
        domains = schema.schema["domains"]
        assert "finance" in domains
        assert "hr" in domains
        assert "sales" in domains
        assert "inventory" in domains
        assert "support" in domains
        assert "engineering" in domains

    def test_get_columns(self, schema):
        cols = schema.get_columns_for_domain("sales", "deals")
        assert "id" in cols
        assert "deal_stage" in cols
        assert "deal_value" in cols
        assert "margin" in cols
        assert "commission_pct" in cols

    def test_get_sensitive_columns(self, schema):
        sensitive = schema.get_sensitive_columns("sales", "deals")
        assert "margin" in sensitive
        assert "commission_pct" in sensitive
        assert "competitor_notes" in sensitive

    def test_get_table_for_column(self, schema):
        assert schema.get_table_for_column("deal_value") == "sales_deals"
        assert schema.get_table_for_column("salary") == "hr_employees"
        assert schema.get_table_for_column("stock_level") == "inventory_products"

    def test_resolve_domain_from_table(self, schema):
        assert schema.resolve_domain_from_table("hr_employees") == ("hr", "employees")
        assert schema.resolve_domain_from_table("sales_deals") == ("sales", "deals")
        assert schema.resolve_domain_from_table("eng_bugs") == ("engineering", "bugs")

    def test_get_allowed_columns_admin(self, schema):
        cols = schema.get_allowed_columns("admin", "finance", "payroll")
        assert len(cols) > 0
        assert "salary" in cols
        assert "ssn" in cols

    def test_get_allowed_columns_sales_rep(self, schema):
        cols = schema.get_allowed_columns("sales_rep", "sales", "deals")
        assert "deal_value" in cols
        assert "deal_stage" in cols
        assert "margin" not in cols  # should be blocked
        assert "commission_pct" not in cols
        assert "competitor_notes" not in cols

    def test_get_allowed_columns_viewer_restricted(self, schema):
        cols = schema.get_allowed_columns("viewer", "sales", "deals")
        assert "deal_stage" in cols
        # Viewer shouldn't see deal_value
        assert "deal_value" not in cols

    def test_get_rls_predicates(self, schema):
        admin = schema.get_rls_predicates("admin")
        assert "1=1" in admin[0]

        sales_rep = schema.get_rls_predicates("sales_rep")
        assert any("assigned_to" in p for p in sales_rep)
        assert any("tenant_id" in p for p in sales_rep)


# ─── SQL Parsing Tests ───


class TestSQLParsing:
    def test_extract_simple_columns(self):
        assert _extract_columns_from_select(
            "SELECT id, name, salary FROM hr_employees"
        ) == ["id", "name", "salary"]

    def test_extract_star(self):
        assert _extract_columns_from_select("SELECT * FROM hr_employees") == ["*"]

    def test_extract_columns_multiline(self):
        cols = _extract_columns_from_select(
            """SELECT
                id,
                employee_name,
                salary
            FROM hr_employees"""
        )
        assert "id" in cols
        assert "employee_name" in cols
        assert "salary" in cols

    def test_extract_columns_with_where(self):
        cols = _extract_columns_from_select(
            "SELECT id, title FROM hr_employees WHERE department_id = 5"
        )
        assert cols == ["id", "title"]

    def test_normalize_column_name(self):
        assert _normalize_column_name("salary") == "salary"
        assert _normalize_column_name("t.salary") == "salary"
        assert _normalize_column_name("salary AS s") == "salary"
        assert _normalize_column_name("COUNT(salary)") == "salary"
        assert _normalize_column_name("SUM(deal_value) AS total") == "deal_value"

    def test_extract_table_names(self):
        tables = _extract_table_names(
            "SELECT * FROM hr_employees JOIN hr_performance ON hr_employees.id = hr_performance.employee_id"
        )
        assert "hr_employees" in tables
        assert "hr_performance" in tables

    def test_has_where_clause(self):
        assert _has_where_clause("SELECT * FROM t WHERE id = 1")
        assert not _has_where_clause("SELECT * FROM t")

    def test_find_date_comparisons(self):
        comps = _find_date_comparisons(
            "SELECT * FROM hr_employees WHERE hire_date >= '2023-01-01' AND birth_date <= '2000-12-31'"
        )
        cols = [c["column"] for c in comps]
        assert "hire_date" in cols
        assert "birth_date" in cols

    def test_query_fingerprint(self):
        fp1 = get_query_fingerprint("SELECT * FROM sales_deals")
        fp2 = get_query_fingerprint("select * from   sales_deals  ")
        assert fp1 == fp2  # normalization works


# ─── Validator Tests ───


class TestSQLValidator:
    def test_admin_passes_all(self, validator):
        result = validator.validate(
            sql="SELECT id, employee_name, email, phone, title, department_id, manager_id, hire_date, termination_date, salary, ssn, birth_date, created_at, updated_at FROM hr_employees",
            user_id="admin1",
            role="admin",
            domain="hr",
            subdomain="employees",
        )
        assert result["status"] == "pass"

    def test_sales_rep_blocked_sensitive_columns(self, validator):
        result = validator.validate(
            sql="SELECT id, deal_stage, deal_value, margin, commission_pct FROM sales_deals",
            user_id="rep42",
            role="sales_rep",
            domain="sales",
            subdomain="deals",
        )
        assert result["status"] == "fail"
        violations = [v["detail"] for v in result["violations"]]
        assert any("margin" in v for v in violations)
        assert any("commission_pct" in v for v in violations)

    def test_sales_rep_passes_safe_query(self, validator):
        result = validator.validate(
            sql="SELECT id, lead_name, company FROM sales_leads WHERE assigned_to = 42",
            user_id="rep42",
            role="sales_rep",
            domain="sales",
            subdomain="leads",
        )
        assert result["status"] == "pass"

    def test_no_where_clause_for_restricted_role(self, validator):
        result = validator.validate(
            sql="SELECT * FROM sales_deals",
            user_id="rep42",
            role="sales_rep",
            domain="sales",
            subdomain="deals",
        )
        # Should have both CLS and RLS violations
        violations_types = [v["type"] for v in result["violations"]]
        assert "RLS" in violations_types

    def test_viewer_cannot_see_deal_value(self, validator):
        result = validator.validate(
            sql="SELECT id, company, deal_value FROM sales_deals",
            user_id="guest1",
            role="viewer",
            domain="sales",
            subdomain="deals",
        )
        assert result["status"] == "fail"
        assert any("deal_value" in v["detail"] for v in result["violations"])

    def test_finance_blocked_for_sales_rep(self, validator):
        result = validator.validate(
            sql="SELECT id, salary, ssn FROM hr_employees",
            user_id="rep42",
            role="sales_rep",
            domain="hr",
            subdomain="employees",
        )
        # sales_rep has very restricted HR access
        cls = result["cls_checks"][0]
        # They should see only a few HR columns
        assert "salary" in cls["blocked_columns"] or len(cls["allowed_columns"]) < 10

    def test_analyst_can_see_salary(self, validator):
        result = validator.validate(
            sql="SELECT id, department_id, salary FROM hr_employees",
            user_id="analyst5",
            role="analyst",
            domain="hr",
            subdomain="employees",
        )
        # analyst has salary access
        cls = result["cls_checks"][0]
        if isinstance(cls["blocked_columns"], list):
            assert "salary" not in cls["blocked_columns"]

    def test_report_format(self, validator):
        result = validator.validate(
            sql="SELECT id, deal_stage FROM sales_deals WHERE assigned_to = 42",
            user_id="rep42",
            role="sales_rep",
            domain="sales",
            subdomain="deals",
        )
        report = validator.format_report(result)
        assert "SQL VALIDATION REPORT" in report
        assert result["fingerprint"] in report
        assert "PASS" in report or "FAIL" in report


# ─── Synthetic Data Tests ───


class TestSyntheticData:
    def test_all_generators_registered(self):
        assert "finance" in GENERATORS
        assert "hr" in GENERATORS
        assert "sales" in GENERATORS
        assert "inventory" in GENERATORS
        assert "support" in GENERATORS
        assert "engineering" in GENERATORS

    def test_finance_budgets(self):
        rows = generate("finance", "budget", n=5)
        assert len(rows) == 5
        for row in rows:
            assert "id" in row
            assert "budget_allocated" in row
            assert "budget_spent" in row
            assert "fiscal_year" in row
            assert 2020 <= row["fiscal_year"] <= 2026

    def test_hr_employees(self):
        rows = generate("hr", "employees", n=10)
        assert len(rows) == 10
        for row in rows:
            assert "employee_name" in row
            assert "salary" in row
            assert row["salary"] > 0
            assert "@" in row["email"]

    def test_sales_deals(self):
        rows = generate("sales", "deals", n=10)
        assert len(rows) == 10
        stages = {"Prospecting", "Qualification", "Proposal", "Negotiation", "Closed Won", "Closed Lost"}
        for row in rows:
            assert row["deal_stage"] in stages
            assert row["deal_value"] > 0
            assert 0 < row["margin"] < 1

    def test_support_tickets(self):
        rows = generate("support", "tickets", n=10)
        assert len(rows) == 10
        for row in rows:
            assert "ticket_subject" in row
            assert "priority" in row
            assert row["priority"] in {"Low", "Medium", "High", "Critical"}

    def test_eng_bugs(self):
        rows = generate("engineering", "bugs", n=10)
        assert len(rows) == 10
        for row in rows:
            assert "severity" in row
            assert row["severity"] in {"Critical", "High", "Medium", "Low", "Cosmetic"}

    def test_finance_payroll_sensitive(self):
        rows = generate("finance", "payroll", n=5)
        for row in rows:
            assert "ssn" in row  # should exist (it's in the schema)
            assert "salary" in row

    def test_generate_invalid_domain(self):
        with pytest.raises(ValueError):
            generate("nonexistent", "table", n=5)


# ─── Date Constraint Tests ───


class TestDateConstraints:
    def test_check_future_birth_date(self, schema):
        violations = schema.check_date_constraints("birth_date", "2070-01-01")
        assert len(violations) > 0
        assert any("future" in v.get("issue", "").lower() for v in violations)

    def test_check_valid_birth_date(self, schema):
        violations = schema.check_date_constraints("birth_date", "1990-06-15")
        # Should have no violations for a reasonable date
        date_v = [v for v in violations if "future" in v.get("issue", "").lower()]
        assert len(date_v) == 0

    def test_check_underage(self, schema):
        # Birth date 5 years ago — age ~5
        from datetime import date, timedelta
        child_date = (date.today() - timedelta(days=365 * 5)).isoformat()
        violations = schema.check_date_constraints("date_of_birth", child_date)
        assert any("18" in v.get("issue", "") or "under" in v.get("issue", "").lower() for v in violations)

    def test_check_created_at_future(self, schema):
        violations = schema.check_date_constraints("created_at", "2099-12-31T00:00:00")
        assert any("future" in v.get("issue", "").lower() for v in violations)


# ─── Integration Test ───


class TestIntegration:
    def test_full_workflow(self, validator):
        """End-to-end: validate multiple queries across roles."""
        test_cases = [
            # (sql, role, domain, subdomain, expected_status)
            ("SELECT id, deal_stage, deal_value FROM sales_deals WHERE assigned_to = 1", "admin", "sales", "deals", "pass"),
            ("SELECT id, deal_stage, deal_value FROM sales_deals", "viewer", "sales", "deals", "fail"),  # viewer can't see deal_value
            ("SELECT id, title FROM hr_employees WHERE tenant_id = 'default'", "sales_rep", "hr", "employees", "pass"),  # sales_rep has basic HR view
        ]

        for sql, role, domain, subdomain, expected in test_cases:
            result = validator.validate(
                sql=sql,
                user_id="test_user",
                role=role,
                domain=domain,
                subdomain=subdomain,
            )
            assert result["status"] == expected, (
                f"\nSQL: {sql}\nRole: {role}\nExpected: {expected}, Got: {result['status']}"
                f"\nViolations: {result['violations']}"
            )

    def test_cross_domain_detection(self, validator):
        """Table auto-detection should resolve domain."""
        result = validator.validate(
            sql="SELECT id, deal_stage FROM sales_deals",
            user_id="admin1",
            role="admin",
            # domain left empty — should auto-detect
        )
        assert result["domain"] == "sales"
        assert result["subdomain"] == "deals"
        assert result["status"] == "pass"
