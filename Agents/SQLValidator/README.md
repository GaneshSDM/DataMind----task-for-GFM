# SQL Validator Agent — Ganesh

> **"Every query must earn its right to see data."**

Ganesh is a security-focused SQL validation agent. It enforces **Row-Level Security (RLS)** and **Column-Level Security (CLS)** on SQL queries before they reach the database. It uses Groq LLM for additional reasoning and generates synthetic data across 6 business domains.

## Installation

```bash
cd "Groq Agent"

# Install dependencies (only 2 external packages)
pip install pyyaml python-dotenv

# Set Groq API key (required for LLM features, optional for rule-based)
cp .env.example .env
# Edit .env with your Groq API key from https://console.groq.com/keys
```

## Quick Start

```bash
# See the persona (who Ganesh is, what it can/can't do)
python agent.py persona

# Validate a safe query as sales_rep
python agent.py validate \
  --sql "SELECT id, lead_name, company FROM sales_leads WHERE assigned_to = 42" \
  --user rep42 --role sales_rep

# Validate a dangerous query (violations detected!)
python agent.py validate \
  --sql "SELECT id, deal_value, margin, commission_pct FROM sales_deals" \
  --user rep42 --role sales_rep

# Generate synthetic sales data
python agent.py generate --domain sales --subdomain deals --rows 30

# Generate all CSVs
python agent.py generate-all --rows 50
```

## Persona & Role Boundary

Ganesh enforces a strict boundary:

| **Within Boundary** (GIVEN)      | **Outside Boundary** (NOT GIVEN)     |
|-----------------------------------|--------------------------------------|
| User identity (id, role, tenant)  | Database connection                  |
| RLS rules (who sees what rows)    | User authentication                 |
| CLS rules (who sees what columns) | Query optimization                  |
| Date constraints                  | Data modification impacts           |
| Domain/subdomain metadata         | Cross-user data comparison          |
| SQL syntax validation             | Network-level access                |
| Table/column existence            |                                      |

## Architecture

```
Groq Agent/
├── persona.md           # Agent identity, role boundaries, tone
├── config.yaml          # RLS/CLS rules, date constraints, Groq config
├── agent.py             # Main entry point / orchestrator
├── sql_validator.py     # SQL validation engine (RLS + CLS + dates)
├── synthetic_data.py    # Synthetic data generator (6 domains, 14 subdomains)
├── groq_client.py       # Groq API client (stdlib only, no deps!)
├── schemas/
│   └── domain_schema.json  # Domain/subdomain/column definitions
├── data/                # Generated CSVs
└── tests/
    └── test_validator.py   # 30+ tests
```

## Data Domains

| Domain     | Subdomains                         | Sensitive Columns                       |
|------------|------------------------------------|-----------------------------------------|
| **finance**  | budget, payroll, transactions       | salary, bonus, ssn, bank_account       |
| **hr**       | employees, performance, benefits    | salary, ssn, performance_rating         |
| **sales**    | leads, deals, accounts              | margin, commission_pct, competitor_notes|
| **inventory**| products, warehouse                | cost_price, supplier_id                 |
| **support**  | tickets                            | customer_email, internal_notes, sla_breach_log |
| **engineering**| projects, bugs                   | reported_by                             |

## Roles

| Role             | Description                                      |
|------------------|--------------------------------------------------|
| `admin`         | Full access — all rows, all columns               |
| `manager`       | Department-scoped, blocked from SSN/salary in HR |
| `sales_rep`     | Own leads/deals only, blocked from margin/commission |
| `analyst`       | Tenant-scoped, can see salary but not SSN         |
| `support_agent` | Own tickets, limited cross-domain visibility      |
| `viewer`        | Most restricted — published data only             |

## Security Rules

### Row-Level Security (RLS)

Every role has mandatory WHERE predicates:

- `admin`: sees everything (`1=1`)
- `manager`: `department_id = :user_department_id AND tenant_id = :user_tenant_id`
- `sales_rep`: `assigned_to = :user_id AND tenant_id = :user_tenant_id AND deleted_at IS NULL`
- `analyst`: `tenant_id = :user_tenant_id AND deleted_at IS NULL AND is_archived = false`

### Column-Level Security (CLS)

Each role has a whitelist of allowed columns per domain. For example, `sales_rep` can see `deal_value` but NOT `margin`, `commission_pct`, or `competitor_notes`.

### Date Constraints

7 global rules enforced on date columns:
- `birth_date` must not be in the future
- `start_date` must precede `end_date`
- `created_at` must not be in the future
- `fiscal_year` must be within valid range
- `hire_date` must precede `termination_date`
- `effective_date` cannot be > 90 days in future
- `birth_date` must indicate age 18–120

## CLI Reference

```
Commands:
  persona         Display agent persona and role boundary

  validate        Validate a SQL query
    --sql TEXT    SQL query
    --file PATH   Read SQL from file
    --user ID     User ID (required)
    --role ROLE   User role (required)
    --tenant ID   Tenant ID
    --domain DOM  Data domain
    --subdomain S Data subdomain
    --groq        Use Groq LLM for analysis
    --json        Output raw JSON

  generate        Generate synthetic data
    --domain DOM  Data domain (required)
    --subdomain S Data subdomain (required)
    --rows N      Number of rows (default 20)
    --output PATH Output file
    --groq        Use Groq LLM for generation

  generate-all    Generate all CSVs
    --rows N      Rows per table (default 20)
    --output DIR  Output directory

  batch           Batch validate queries
    --input FILE  Input file (JSONL or SQL)
    --user ID     Default user
    --role ROLE   Default role
```

## Testing

```bash
pip install pytest
python -m pytest tests/ -v
```

```
tests/test_validator.py::TestSchemaStore::test_loads_domains PASSED
tests/test_validator.py::TestSchemaStore::test_get_columns PASSED
tests/test_validator.py::TestSQLParsing::test_extract_simple_columns PASSED
tests/test_validator.py::TestSQLValidator::test_sales_rep_blocked_sensitive_columns PASSED
tests/test_validator.py::TestSyntheticData::test_hr_employees PASSED
tests/test_validator.py::TestIntegration::test_full_workflow PASSED
...
```

## Example: Validation Report

```
============================================================
SQL VALIDATION REPORT
============================================================
User:        rep42 | Role: sales_rep | Tenant: default
Domain:      sales / deals
Query Hash:  a1b2c3d4e5f6

STATUS:  ✗ FAIL

--- Violations ---
[1] Type: CLS | Detail: Column 'margin' is blocked for role 'sales_rep'
    Fix: Remove 'margin' from SELECT or request elevated access
[2] Type: CLS | Detail: Column 'commission_pct' is blocked for role 'sales_rep'
    Fix: Remove 'commission_pct' from SELECT or request elevated access
[3] Type: CLS | Detail: Column 'competitor_notes' is blocked for role 'sales_rep'
    Fix: Remove 'competitor_notes' from SELECT or request elevated access

--- Column-Level Security ---
  Allowed:      id, lead_id, deal_stage, deal_value, assigned_to, created_at, updated_at
  Referenced:   id, deal_value, margin, commission_pct, competitor_notes
  Blocked:      margin, commission_pct, competitor_notes

--- Summary ---
Verdict: FAIL — 3 violation(s) found.
Fix the violations above before executing this query.
============================================================
```
