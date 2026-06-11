# Plan: Agentic Data Engineering Pipeline

## Context
The existing platform has a LangGraph pipeline for governance (guardrail → intent → SQL → validate → synthesize). The user wants to **extend it into a full agentic data engineering platform** that can ingest data from source to target, plan and execute transformation workflows, and give complete control over the input data — including table discovery, query execution, SQL transformation, PII masking, quality checks, and publishing. Three reference projects (Datus, AltimateAI, tower/agentic-data-engineering) inspired the capability model. The user chose **"Full Agentic Workflow"** as the first implementation priority: the entire DAG (discover → ingest → transform → mask → quality → publish) with an LLM agent planning the steps and executing them.

## Architecture Overview

A new **Data Workflow Agent** microservice (port 8007) that:
1. Accepts a natural-language data engineering task + inline source/target config
2. An internal LangGraph workflow plans the multi-step DAG (LLM-decides-next-step, agentic mode)
3. Each step is executed by a sub-agent (6 sub-agents internally: DISCOVERY, INGESTION, TRANSFORMATION, PII_MASK, QUALITY, PUBLISH)
4. Supports both **SQL template transforms** and **dbt model execution**
5. Reports progress as SSE events, integrates into the existing orchestrator as a new node

## Files to Create / Modify

### Phase 1 — Microservice Scaffold (Agents/DataFlow/)

**New files:**
- `Agents/DataFlow/workflow_engine.py` — FastAPI app + internal LangGraph StateGraph + endpoints
- `Agents/DataFlow/sub_agents/discovery_agent.py` — Schema introspection, data profiling, PII column heuristics
- `Agents/DataFlow/sub_agents/ingestion_agent.py` — Read source, schema map, bulk write to target
- `Agents/DataFlow/sub_agents/transformation_agent.py` — SQL template + Jinja executor; dbt model runner (CLI subprocess)
- `Agents/DataFlow/sub_agents/pii_mask_agent.py` — 30+ regex patterns, column heuristics, masking strategies (HASH, NULL, MASK, TOKENIZE)
- `Agents/DataFlow/sub_agents/quality_agent.py` — Null check, uniqueness, referential integrity, distribution stats
- `Agents/DataFlow/sub_agents/publish_agent.py` — Create target tables, INSERT results, log lineage
- `Agents/DataFlow/models.py` — Pydantic request/response models
- `Agents/DataFlow/workflow_dag.py` — YAML DAG parser, agentic planner (LLM decides next step)
- `Agents/DataFlow/requirements.txt`

### Phase 1 — Backend Integration

**Modified files:**
- `backend/app/agents/http_clients.py` — Add `get_dataflow_client()` (port 8007, timeout 300s)
- `backend/app/agents/dataflow_node.py` — New node following existing node pattern
- `backend/app/agents/orchestrator.py` — Add `dataflow_node` + new state keys + conditional edges
- `backend/app/agents/queue_writer.py` — Minor: add `"dataflow"` as a next_agent option
- `backend/app/api/routes/agents.py` — Add `_HEALTH_URLS` entry for dataflow agent
- `backend/app/api/routes/chat.py` — Add SSE event mapping for dataflow node events

### Phase 2 — Frontend

**New files:**
- `frontend/src/pages/DataPipeline.jsx` — Workflow creation UI + run monitoring
- `frontend/src/components/dataflow/WorkflowBuilder.jsx` — YAML DAG editor with visual feedback
- `frontend/src/components/dataflow/PipelineRunView.jsx` — Run status with per-step logs

**Modified files:**
- `frontend/src/main.jsx` — Add `/data-pipeline` route (Admin only)
- `frontend/src/components/layout/AppShell.jsx` — Add "Data Pipeline" nav entry
- `frontend/src/api/client.js` — Add dataflow API functions

### Phase 3 — dbt Integration (optional depth, scaffold now)

**Modified files:**
- `Agents/DataFlow/sub_agents/transformation_agent.py` — dbt CLI integration: parse `profiles.yml`, run `dbt run --select model_name`, capture logs/stdout
- `Agents/DataFlow/workflow_dag.py` — dbt-specific config parsing

## Data Flow Architecture

```
User: "Ingest public.orders from Postgres A into analytics schema on Postgres B, 
       mask PII on email/phone, run the dbt fct_orders model, and validate quality"

       │
       ▼
Data Workflow Agent (8007) — receives:
  - prompt: natural language task description
  - source_config: {type: "postgres", connection_string: "...", tables: ["public.orders"]}
  - target_config: {type: "postgres", connection_string: "...", schema: "analytics"}
  - options: {pii_mask: true, dbt_model: "fct_orders", quality_rules: [...]}

       │
       ▼
  [Agentic Planner] — LLM receives the task + available sub-agents
       │                Produces a workflow DAG plan:
       │                1. DISCOVERY → introspect public.orders
       │                2. INGESTION → copy to staging.orders_stg
       │                3. PII_MASK  → mask email, phone on staging
       │                4. TRANSFORMATION → run dbt fct_orders model
       │                5. QUALITY  → validate no nulls, unique order_id
       │                6. PUBLISH  → rename to analytics.fct_orders, log lineage
       │
       ▼
  [Workflow Executor] — Steps through each sub-agent:
       │     ├── Shows plan to user for approval (future: auto-execute)
       │     ├── Each step calls the corresponding sub-agent
       │     ├── Step output feeds next step's context
       │     └── Failed step → LLM retry/adapt or notify user
       │
       ▼
  Returns: {status, output_table, row_count, lineage, quality_report, pii_masked_columns}
```

## Key Sub-Agent Details

### DISCOVERY Agent
- Introspect source: `INFORMATION_SCHEMA.COLUMNS` → tables, columns, types, nullability
- Profile data: row count, distinct %, null %, min/max for numerics, sample values
- PII heuristics: scan column names + sample values against 30+ regex patterns (email, phone, SSN, CC, IP, etc.)
- Returns: {tables: [{name, columns: [{name, type, nullable, pii_category?, sample_values}]}]}

### INGESTION Agent
- Read source: execute `SELECT * FROM source_table` with optional chunking (OFFSET/LIMIT)
- Schema mapping: match source columns to target columns by name/type, auto-cast
- Bulk write: `CREATE TABLE IF NOT EXISTS` + `INSERT INTO ... SELECT ...` or chunked inserts
- Returns: {target_table, rows_ingested, schema_map, duration}

### TRANSFORMATION Agent
- SQL templates: render Jinja templates with context vars, execute against target DB
- dbt mode: parse `profiles.yml`, run `dbt run --select model_name`, capture artifacts
- Materialization: table, view, incremental (merge logic), ephemeral (CTE)
- Returns: {output_table, rows_affected, transformation_log}

### PII_MASK Agent
- Column scan: match column names + sample data against PII regex categories
- Strategies: SHA256_HASH, AES_ENCRYPT, NULL, DUMMY, MASK_FIRST_N, MASK_LAST_N, TOKENIZE
- Apply: `UPDATE target_table SET col = HASH(col) WHERE ...`
- Returns: {masked_columns: [{column, category, strategy}], rows_affected}

### QUALITY Agent
- Rules: no_nulls, unique, min/max, not_empty, referential, custom_sql
- Execute checks, collect results with pass/fail/row_count
- Returns: {checks: [{rule, passed, detail}], overall: "pass"|"fail"|"warn"}

### PUBLISH Agent
- Create final table/view in target schema
- Grant permissions from security_profile
- Log lineage: source → transform → target mapping at column level
- Returns: {final_table, schema, row_count, lineage_map}

## Existing Node Pattern to Follow

Every new node in `backend/app/agents/` follows this exact template from the existing code:

```python
from app.agents.http_clients import get_dataflow_client

async def dataflow_node(state: dict) -> dict:
    if state.get("dataflow_skip"):
        return _skip()
    try:
        client = get_dataflow_client()
        payload = {
            "prompt": state["prompt"],
            "source_config": ...,       # from metadata or security_profile
            "target_config": ...,
            "metadata": state.get("metadata", {}),
        }
        resp = await client.post("/dataflow/run", json=payload)
        resp.raise_for_status()
        result = resp.json()
        return {
            "dataflow_status": result.get("status"),
            "dataflow_result": result,
            "dataflow_error": None,
        }
    except Exception as e:
        return _error(str(e))
```

## Orchestrator Integration

Add to `OrchestratorState`:
```python
# dataflow outputs
dataflow_status: Optional[str]      # "running" | "completed" | "failed"
dataflow_result: Optional[dict]     # full result from workflow engine
dataflow_error: Optional[str]       # error message
dataflow_events: Optional[list]     # SSE events for frontend streaming
```

Graph wiring (insert after `validate_sql` / before `spyder_synthesize`):
```
validate_sql → [if prompt requests data engineering] → dataflow_agent → spyder_synthesize
validate_sql → [normal query] → spyder_synthesize (skip dataflow)
```

The dataflow node is **optional** — only invoked when the prompt is a data engineering task (detected by intent classifier or explicit flag in metadata).

## Inline Source/Target Config

Since the user chose "one-time inline config," the frontend will include fields in the chat input for:
- **Source type**: PostgreSQL / MySQL / Snowflake / BigQuery / DuckDB / CSV File
- **Source connection**: inline connection string or SQLAlchemy URL
- **Source tables/schemas**: which tables to operate on
- **Target type**: same list
- **Target connection**: inline connection string
- **Target schema**: destination schema name
- **Options checkbox**: PII masking, dbt model selection, quality rules

These are sent as part of `metadata` alongside the prompt, forwarded to the dataflow agent.

## Verification

1. **Start the microservice**: `cd Agents/DataFlow && python workflow_engine.py` → confirms port 8007 is up, `/health` returns 200
2. **Test discovery**: POST `/dataflow/discover` with inline PG connection → returns table/column metadata
3. **Test full workflow**: POST `/dataflow/run` with inline config + natural language prompt → agent plans steps, executes them, returns result
4. **Backend integration**: run full stack (backend + all agents + dataflow), send chat prompt with data engineering task → confirms dataflow node fires and returns results
5. **Frontend**: new route renders pipeline builder, inline config form, run status