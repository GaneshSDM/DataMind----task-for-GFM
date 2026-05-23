# SQL Generator Agent — Checkpoint

**Date:** 2026-05-21  
**Status:** Phase 1 + Phase 2 (correction loop) complete — Gemini provider live, two-tab UI running

---

## Agent Pipeline (Current State)

```
[Simulated Input]
      │  agent_input.json  OR  live agent_payload dict
      ▼
[SQL Generator Agent]  ← sql_agent.py :: run_agent()
      │  resolves tables from schema_reference.json
      │  6 random few-shot examples from examples.json
      │  injects RLS WHERE clause into system prompt
      │  strips CLS restricted columns from schema sent to LLM
      │  calls Gemini (primary) or Groq (fallback) → PostgreSQL SQL
      ▼
[output_<request_id>.json]
      │
      ▼
[SQL Validator Agent]   ← Phase 2 (external, feeds back)
      │  checks: syntax, RLS applied, CLS compliance, schema, filter intent
      │  produces: validation_errors[], suggested_corrections[]
      │  status: "validation_failed" if errors found
      ▼
[SQL Correction Agent]  ← sql_agent.py :: run_correction()
      │  receives correction input (output JSON + validation errors)
      │  rebuilds security context from rls_applied.filters_applied
      │  LLM re-call: original prompt + faulty SQL + errors + suggestions
      ▼
[corrected_sql]  → re-enter validation loop or pass downstream
```

### Future Full Pipeline
```
User Prompt
    → Classifier Agent       (domain / sub-domain / table resolution)
    → SQL Generator Agent    (this)
    → SQL Validation Agent   (syntax + security + schema check)
    → SQL Correction Agent   (this — run_correction mode)
    → Execution / Response
```

---

## File Structure

```
SQLGenerator/
├── sql_agent.py              Agent: NL → SQL + correction loop
├── app.py                    Streamlit test harness (2 tabs: Generate + Correct)
├── agent_input.json          Simulated upstream agent payload (slim)
├── schema_reference.json     Canonical schema catalog (domain → sub-domain → tables + columns)
├── examples.json             30 sales examples — few-shot + expected SQL + sample output
├── correction_examples.json  30 validation feedback examples — faulty SQL + errors + suggestions
├── sync_schema.py            One-time schema sync from live PostgreSQL DB
├── .env                      API keys + config (not committed)
├── requirements.txt          Dependencies
└── checkpoint.md             This file
```

---

## Key Design Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| Schema storage | `schema_reference.json` | Static, fast, versionable; not hit per request |
| Agent input | `agent_input.json` (slim) | Table names only — full schema resolved at runtime |
| SQL dialect | PostgreSQL | CTEs, window functions, DATE_TRUNC, EXTRACT |
| LLM provider | Gemini primary / Groq fallback (auto-detect from .env) | Key in env → pick provider; zero code changes to switch |
| RLS approach | Inject WHERE clause + document policy in output JSON | Runtime enforcement + audit trail |
| CLS approach | Exclude columns from schema sent to LLM + flag in output | Model never sees restricted column names |
| Few-shot count | 6 random examples per call | Balance context size vs quality |
| Correction | LLM re-call with faulty SQL + errors | Handles all 5 error types uniformly |
| Deprecated tables | `resolve_tables()` skips tables with `"deprecated"` tag | Live schema only; old tables ignored |

---

## LLM Provider Abstraction (sql_agent.py)

```python
# Auto-detect: GEMINI_API_KEY → Gemini; GROQ_API_KEY → Groq
provider, model, client = get_provider()

# .env controls:
GEMINI_API_KEY = AIzaSy...         # takes priority
GEMINI_MODEL   = gemma-4-26b-a4b-it
GROQ_API_KEY   = gsk_...           # fallback
GROQ_MODEL     = llama-3.1-8b-instant
```

`call_llm(provider, client, model, system_prompt, user_prompt)` — unified interface for both providers.

---

## schema_reference.json

**Active tables (domain: Sales, sub_domain: Sales Analytics):**

| Table / View | Key Columns |
|---|---|
| `fact_orders` | order_id, customer_id, order_date, total_order_value, order_status, payment_method, country |
| `fact_order_items` | order_item_id, order_id, product_id, customer_id, quantity, total_price_usd, cost_usd*, profit_usd*, profit_margin_percent*, fraud_risk_score*, delivery_days, shipping_cost_usd |
| `dim_customer` | customer_id, age, gender, country, customer_segment, customer_loyalty_score* |
| `dim_product` | product_id, product_name, category, sub_category, brand, product_rating_avg |
| `dim_date` | order_date, year, month, quarter, is_weekend |
| `dim_location` | location_id, warehouse_location, shipping_country |
| `dim_payment` | payment_method, payment_status, installment_plan |
| `sales_business_view` | order_id, customer_segment, country, total_order_value, campaign_source, device_type, traffic_source, coupon_used, profit_usd* |
| `raw_ecommerce` | 63 cols — order_priority, return_reason, delivery_days, customer_feedback*, fraud_risk_score* |
| `order_item_agg_view` | aggregated order item metrics |

`*` = commonly restricted by CLS policies

All original tables (orders, customers, order_items, products, salespeople, returns) marked `deprecated` — `resolve_tables()` skips them automatically.

---

## agent_input.json Structure

```json
{
  "request_id": "req-001",
  "prompt": "natural language question",
  "domain": "Sales",
  "sub_domain": "Sales Analytics",
  "tables": ["fact_orders", "dim_customer"],
  "row_level_security": {
    "policy_name": "country_access_policy",
    "enabled": true,
    "filters": [{"column": "country", "operator": "IN", "values": ["India", "USA"]}]
  },
  "column_level_security": {
    "policy_name": "financial_data_policy",
    "enabled": true,
    "restricted_columns": ["cost_usd", "profit_usd", "profit_margin_percent"]
  }
}
```

---

## SQL Generator Output JSON Structure

```json
{
  "request_id": "...",
  "status": "success",
  "generated_sql": "SELECT ...",
  "rls_applied": {
    "enabled": true,
    "policy_name": "country_access_policy",
    "where_clause_injected": "country IN ('India', 'USA')",
    "filters_applied": [...]
  },
  "cls_applied": {
    "enabled": true,
    "policy_name": "financial_data_policy",
    "columns_excluded": ["cost_usd", "profit_usd", "profit_margin_percent"]
  },
  "metadata": {
    "domain": "Sales",
    "sub_domain": "Sales Analytics",
    "tables_in_scope": ["sales.fact_orders"],
    "model_used": "gemma-4-26b-a4b-it",
    "generated_at": "2026-05-21T..."
  },
  "validation_hints": {
    "original_prompt": "...",
    "expected_tables": ["fact_orders", "dim_customer"]
  }
}
```

---

## Correction Input JSON Structure (from SQL Validator)

Same as output JSON above + validation fields:

```json
{
  "request_id": "corr-001",
  "status": "validation_failed",
  "validation_status": "failed",
  "error_type": "RLS",
  "generated_sql": "SELECT ... (faulty SQL) ...",
  "validation_errors": [
    {
      "type": "RLS",
      "detail": "RLS policy 'country_access_policy' not applied. Missing WHERE country IN ('India', 'USA').",
      "fix": "Add WHERE country IN ('India', 'USA') to the query"
    }
  ],
  "suggested_corrections": [
    "Add WHERE country IN ('India', 'USA') before GROUP BY"
  ],
  "rls_applied":  { "enabled": true, "policy_name": "...", "where_clause_injected": null, "filters_applied": [...] },
  "cls_applied":  { "enabled": true, "policy_name": "...", "columns_excluded": [...] },
  "metadata":     { "domain": "Sales", "sub_domain": "...", "tables_in_scope": [...], "model_used": "...", "generated_at": "..." },
  "validation_hints": { "original_prompt": "...", "expected_tables": [...] }
}
```

**5 error types:**

| Type | Description |
|------|-------------|
| `SCHEMA` | Wrong schema qualifier / nonexistent table or view name |
| `SYNTAX` | Missing paren, CASE END, JOIN ON, UNION column mismatch, bad window function |
| `RLS` | Row Level Security WHERE filter not injected |
| `CLS` | Restricted column appears in SELECT |
| `FILTER` | Extra / over-restrictive WHERE not requested by prompt |

---

## correction_examples.json (30 examples)

6 examples each of SCHEMA, SYNTAX, RLS, CLS, FILTER.

Each example has:
- `id`, `request_id`, `error_type`
- `generated_sql` — intentionally broken SQL
- `validation_errors[]` — `{type, detail, fix}`
- `suggested_corrections[]` — plain text hints for LLM
- `rls_applied`, `cls_applied` — security context (with `filters_applied` = what SHOULD be applied)
- `metadata`, `validation_hints`

---

## Correction Output JSON Structure

```json
{
  "request_id": "corr-001",
  "status": "corrected",
  "original_sql": "SELECT ... (faulty) ...",
  "corrected_sql": "SELECT ... (fixed) ...",
  "errors_addressed": [ { "type": "RLS", "detail": "...", "fix": "..." } ],
  "metadata": {
    "domain": "Sales",
    "sub_domain": "Sales Analytics",
    "tables_in_scope": [...],
    "model_used": "gemma-4-26b-a4b-it",
    "corrected_at": "2026-05-21T..."
  }
}
```

---

## sql_agent.py — Key Functions

| Function | Purpose |
|----------|---------|
| `get_provider()` | Auto-detects Gemini or Groq from `.env`, returns `(provider, model, client)` |
| `call_llm(provider, client, model, system, user)` | Unified LLM call — handles both providers |
| `load_schema_reference()` | Load `schema_reference.json` |
| `resolve_tables(schema_ref, domain, table_names)` | Resolve full table metadata, skip deprecated |
| `build_rls_where(rls_config)` | Build WHERE clause string from RLS filters |
| `build_system_prompt(tables, examples, rls_where, excluded_cols)` | Build full system prompt with schema + few-shot |
| `generate_sql(provider, client, model, input_data, resolved_tables, examples)` | Generate SQL — returns `(sql, excluded_cols, rls_where, rls_cfg, cls_cfg)` |
| `build_correction_prompt(correction_input, resolved_tables, examples)` | Build system + user prompts for correction mode |
| `run_correction(correction_input, schema_ref, examples)` | Apply validation feedback → corrected SQL |
| `run_agent(input_source, input_path, agent_payload)` | Main entry point for generation |

---

## examples.json (30 examples)

Tables: `fact_orders`, `fact_order_items`, `dim_customer`, `dim_product`, `dim_location`, `dim_payment`, `dim_date`, `sales_business_view`, `raw_ecommerce`

Each example has: `id`, `prompt`, `tables_used` (schema-qualified), `rls_filters`, `excluded_columns`, `expected_sql`, `sample_output {columns, rows}`

RLS columns used: `country`, `customer_segment`  
CLS columns used: `cost_usd`, `profit_usd`, `profit_margin_percent`, `fraud_risk_score`, `customer_loyalty_score`, `customer_feedback`

---

## Streamlit Test Harness (app.py)

### Tab 1 — Generate

1. Example selector — full prompt in dropdown (30 examples)
2. Security configuration
   - RLS: toggle + dynamic filter rows (column / operator / value) — pre-filled from example
   - CLS: toggle + multiselect from all columns of selected tables
3. Generate SQL → calls `generate_sql()` via detected provider
4. Accuracy Score — 4 metrics + combined:
   - **Combined** = SQL sim × 0.40 + token overlap × 0.20 + clause match × 0.15 + col match × 0.25
   - SQL Similarity (difflib SequenceMatcher)
   - Token Overlap (expected tokens in generated)
   - Clause Match (SELECT / WHERE / GROUP BY / JOIN / OVER etc.)
   - Column Match (expected output columns present in generated SQL)
5. SQL Comparison — generated vs expected side-by-side + unified diff
6. Output Comparison — expected sample rows vs generated SQL column schema
7. Security Context Applied — RLS/CLS JSON

### Tab 2 — Correct

1. Correction example selector — shows `[ERROR_TYPE] prompt` (30 examples)
2. Validation Errors — error detail + suggested corrections displayed
3. Faulty SQL displayed
4. Apply Correction button → calls `run_correction()` → LLM re-generates
5. Corrected vs faulty SQL side-by-side + diff
6. Errors Addressed list

**Run:**
```powershell
cd "C:\Users\Localuser\Desktop\Work\Training\SLM Project\SQLGenerator"
streamlit run app.py
# → http://localhost:8501
```

---

## .env Variables

```env
GEMINI_API_KEY=...               # primary provider (takes priority)
GEMINI_MODEL=gemma-4-26b-a4b-it
GROQ_API_KEY=...                 # fallback provider
GROQ_MODEL=llama-3.1-8b-instant
DB_SCHEMA=sales
DATABASE_URL=postgresql://...    # used by sync_schema.py only
SECRET_KEY=...
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=480
```

---

## How to Switch LLM Provider

Add/remove keys in `.env` — no code changes:
- `GEMINI_API_KEY` present → Gemini (primary)
- Only `GROQ_API_KEY` present → Groq (fallback)
- Neither → `EnvironmentError` at startup

---

## How to Use Live Agent Input

```python
# Dev / simulation (current)
run_agent()

# Live pipeline — receive dict from upstream classifier agent
run_agent(input_source="agent", agent_payload=<dict>)

# Correction mode — receive dict from SQL Validator Agent
run_correction(correction_input=<validation_feedback_dict>)
```

---

## sync_schema.py (One-Time Schema Sync)

Connects to Supabase PostgreSQL, introspects `information_schema` for tables/views in `sales` schema, diffs vs `schema_reference.json`, merges (preserves descriptions/pii/sensitive flags), marks removed tables as `deprecated`, regenerates examples via LLM, writes `sync_log.json`.

**Run once after DB schema changes:**
```powershell
python sync_schema.py
```

---

## Dependencies

```
groq>=0.9.0
python-dotenv>=1.0.0
streamlit>=1.35.0
psycopg2-binary>=2.9.0
google-genai>=1.0.0
```

Install: `pip install -r requirements.txt`

---

## Next Steps

| Phase | Task | Status |
|-------|------|--------|
| Phase 1 | SQL Generator Agent + Streamlit harness | DONE |
| Phase 2 | Correction loop (validation feedback → re-generation) | DONE |
| Phase 3 | SQL Validation Agent — actual syntax check + schema validation | TODO |
| Phase 4 | Classifier Agent — raw prompt → domain / sub-domain / tables | TODO |
| Phase 5 | Connect validation agent to correction agent (automated loop) | TODO |
| Phase 6 | Execution agent — run corrected SQL on live DB, return results | TODO |
| Future | Vector DB for semantic table/column search in classifier | TODO |
| Future | Prompt caching for schema reference (reduce LLM tokens) | TODO |
