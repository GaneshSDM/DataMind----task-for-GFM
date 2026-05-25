# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Backend (main app)
```bash
# From backend/
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Run migrations
alembic upgrade head

# Seed initial admin user and DB connection
python seed.py
```

### Heimdall — Guardrail Microservice
```bash
# From Agents/Guardrail/
pip install fastapi uvicorn langgraph sentence-transformers psycopg2-binary python-dotenv numpy
python watchman.py
# → http://localhost:8001
# → POST /guardrail/check
# → GET  /health
```

### ARIA — IntentClassifier Microservice
```bash
# From Agents/IntentClassifier/

# Step 1 — generate schema reference (run once, or after schema/RAG changes)
python bootstrap_schema.py
# → writes schema_reference.json — CANONICAL shared schema (also used by SAGE)

# Step 2 — start service
pip install fastapi uvicorn sentence-transformers psycopg2-binary python-dotenv httpx
python aria.py
# → http://localhost:8002
# → POST /intent/classify
# → POST /schema/reload   (hot-reload schema_reference.json without restart)
# → GET  /health
```

### SAGE — SQL Generator Microservice
```bash
# From Agents/SQLGenerator/
pip install fastapi uvicorn groq python-dotenv psycopg2-binary
python sage.py
# → http://localhost:8003
# → POST /sql/generate
# → GET  /health
# Reads shared schema from Agents/IntentClassifier/schema_reference.json (resolved in sage.py)
```

### Frontend
```bash
# From frontend/
npm install
npm run dev        # dev server on :5173
npm run build
npm run preview
```

## Running the Full Stack

```bash
# Terminal 1 — Heimdall (guardrail microservice)
cd Agents/Guardrail && python watchman.py                  # :8001

# Terminal 2 — ARIA (intent classifier microservice)
cd Agents/IntentClassifier && python aria.py               # :8002

# Terminal 3 — SAGE (SQL generator microservice)
cd Agents/SQLGenerator && python sage.py                   # :8003

# Terminal 4 — VALKYRIE (SQL validator microservice)
cd Agents/SQLValidator && python valkyrie.py             # :8004

# Terminal 5 — SPYDER (synthesizer microservice)
cd Agents/Synthesizer/backend && uvicorn main:app --host 0.0.0.0 --port 8005 --reload  # :8005

# Terminal 6 — RAVEN (RAG query agent)
cd Agents/VectorDBagent && uvicorn raven:app --host 0.0.0.0 --port 8006 --reload       # :8006

# Terminal 7 — Main backend
cd backend && uvicorn app.main:app --reload --port 8000    # :8000

# Terminal 8 — Frontend
cd frontend && npm run dev                                  # :5173
```

## Architecture

Full-stack SLM (Small Language Model) management platform with governance/security features.

**Stack:** React 18 + Vite (frontend) · FastAPI + SQLAlchemy 2.0 (backend) · PostgreSQL via Supabase · JWT auth

### Backend (`backend/app/`)

- `main.py` — FastAPI app, CORS, router registration, table auto-create on startup; loads `app.state.guardrails` cache; pre-warms RAG embedder
- `core/config.py` — Pydantic Settings; reads `.env`
- `core/security.py` — bcrypt hashing, JWT encode/decode, `get_current_user` dependency
- `db/session.py` — SQLAlchemy engine + `SessionLocal` + `get_db` dependency
- `models/user.py` — All 25+ ORM models in `schema="tracopp"`
- `schemas/schemas.py` — All Pydantic request/response models
- `api/routes/` — One file per domain: `auth`, `users`, `geo_domain`, `security`, `guardrails`, `chat`, `config`, `rag`, `agents`, `reports`
- `api/routes/reports.py` — `POST /api/reports/export` → branded PDF via reportlab; accepts `{title, prompt, synthesis, sql_results[]}`; returns `application/pdf` stream

API prefixes: `/api/auth`, `/api/users`, `/api/geographies`, `/api/domains`, `/api/subdomains`, `/api/security-groups`, `/api/rls`, `/api/cls`, `/api/guardrails`, `/api/chats`, `/api/slm-config`, `/api/db-connections`, `/api/rag`, `/api/agents`, `/api/reports`

All protected routes use `current_user = Depends(get_current_user)`. Admin-only ops call `check_admin()`.

### Agent Orchestration (`backend/app/agents/`)

LangGraph pipeline invoked from `chat.py` on every prompt send.

**Current flow (Phase 4):**
```
guardrail_check → [blocked/error → END]
               → intent_classify → [error → END]
               → save_to_queue → sql_generate → [no SQL → END]
                                              → validate_sql → END
```

- `orchestrator.py` — `StateGraph` wiring; `run_pipeline()` public entry point
- `guardrail_node.py` — HTTP POST → Heimdall `:8001`; returns `guardrail_status`, `blocked_by`, `guardrail_message`
- `intent_node.py` — HTTP POST → ARIA `:8002`; returns `intent_status`, `intent_result`, `intent_error`
- `queue_writer.py` — writes `Agents/pipeline_queue/{request_id}.json`; `stage: "intent_classified"`, `next_agent: "sql_generator"`
- `sql_node.py` — HTTP POST → SAGE `:8003`; returns `sql_status`, `sql_result`, `sql_error`; routes to `validate_sql` if any SQL results succeeded, else END
- `valkyrie_node.py` — HTTP POST → VALKYRIE `:8004`; correction loop max 2 (calls SAGE `/sql/correct` per failed intent); returns `valkyrie_status`, `valkyrie_result`, `synthesizer_context`

**Chat response by outcome:**
- `blocked` → red bubble, policy name pill, block reason
- `guardrail error` → amber bubble
- `intent error` → ✅ guardrails passed + amber intent error
- `sql error` → ✅ guardrails + intents passed + amber SQL error
- `success` → ✅ bubble + SQL code blocks (with RLS/CLS badges) + intent cards

### Heimdall Guardrail Microservice (`Agents/Guardrail/`)

Port **8001**. LangGraph `StateGraph`: `embed_prompt → threshold → keyword → semantic → context → END`

- `watchman.py` — FastAPI app + graph + endpoints; loads `backend/.env` at startup
- `models.py` — `WatchmanRequest`, `WatchmanState`, `SecurityProfile`
- `embedder.py` — `all-MiniLM-L6-v2` (384-dim) singleton
- `db.py` — psycopg2 ThreadedConnectionPool; reads `tracopp.prompt_policies`

Check types (UPPERCASE in DB): `THRESHOLD`, `KEYWORD`, `SEMANTIC`, `CONTEXT`
- CONTEXT node: case-insensitive match; blocks if user has no domains (fail-safe)

### ARIA IntentClassifier Microservice (`Agents/IntentClassifier/`)

Port **8002**. Groq LLM (`llama-3.3-70b-versatile`) + pgvector RAG retrieval.

**Key files:**
- `aria.py` — FastAPI app; loads `backend/.env` BEFORE sub-module imports (config.settings reads GROQ_API_KEY at module level); extracts `allowed_domains`, `allowed_domain_ids` from security_profile
- `core/intent_processor.py` — loads `schema_reference.json` at startup; builds domain-constrained prompt; calls Groq; post-processes Unstructured/Both intents with RAG retrieval
- `core/groq_client.py` — httpx Groq API client with retry
- `core/rag_retriever.py` — `BAAI/bge-large-en-v1.5` embed + pgvector cosine search on `tracopp.rag_document_chunks`; filters to user's `allowed_domain_ids`; returns top-5 chunks
- `bootstrap_schema.py` — one-time: reads tracopp domains/subdomains/RAG files, introspects `sales` schema → writes `schema_reference.json` (canonical, shared with SAGE)
- `config/settings.py` — reads env vars at module level; must be imported AFTER `load_dotenv`

**ARIA output per intent:**
```json
{
  "intent_id": 1, "description": "...", "domain": "Sales", "sub_domain": "...",
  "data_source": "Structured|Unstructured|Both",
  "structured_table": "fact_orders", "relevant_columns": ["col1", "col2"],
  "unstructured_source": "filename — description",
  "intent_types": ["Data","Reasoning"], "requires_data_fetch": true,
  "retrieved_context": [
    {"filename": "...", "chunk_text": "...", "page_number": 3, "similarity": 0.91}
  ]
}
```

### SAGE SQL Generator Microservice (`Agents/SQLGenerator/`)

Port **8003**. Groq LLM (`llama-3.3-70b-versatile`). Converts ARIA structured intents → PostgreSQL.

**Key files:**
- `sage.py` — FastAPI app; loads `backend/.env`; resolves `SCHEMA_FILE_PATH` to ARIA's `schema_reference.json` before importing `sql_agent`; adapts pipeline security_profile → SAGE input per intent
- `sql_agent.py` — core SQL generation: `get_llm_client()`, `resolve_tables()`, `generate_sql()`, `build_output()`, `run_correction(llm_config=None)`; reads `SCHEMA_FILE_PATH` env var at module level
- `examples.json` — 30 few-shot SQL examples (Sales domain)
- `correction_examples.json` — 30 validation error correction examples (SCHEMA/SYNTAX/RLS/CLS/FILTER)
- `sync_schema.py` — one-time schema sync from live DB (use ARIA's `bootstrap_schema.py` instead for shared schema)

**Security adapters in `sage.py`:**
- `_adapt_rls()` — pipeline RLS `{"table", "filter": "SQL expression"}` → SAGE `{"expression": "..."}` format
- `_adapt_cls()` — pipeline CLS `{"columns": [{"can_read": false}]}` → SAGE `{"restricted_columns": [...]}`
- `_normalize_schema()` — converts ARIA flat schema `{domains, tables}` → SAGE nested `{catalog}` format at startup

**SAGE output per intent:**
```json
{
  "intent_id": 1, "status": "success",
  "generated_sql": "SELECT ...",
  "rls_applied": {"enabled": true, "policy_name": "...", "where_clause_injected": "country IN ('India')"},
  "cls_applied": {"enabled": true, "columns_excluded": ["profit_usd"]},
  "tables_in_scope": ["sales.fact_orders"],
  "model_used": "llama-3.3-70b-versatile"
}
```

**Production embedding:** Set `HF_HOME=/models` + mount persistent volume. Model cached on first run.

### VALKYRIE SQL Validator Microservice (`Agents/SQLValidator/`)

Port **8004**. Validates SAGE-generated SQL against security policy before surfacing to frontend.

**Key files:**
- `valkyrie.py` — FastAPI app; loads `backend/.env`; imports utility functions from `sql_validator.py`

**Validation approach:**
- Rule-based: syntax check, CLS (restricted cols from pipeline `security_profile`), RLS (filter expression presence in WHERE)
- LLM semantic analysis via `validate_permissions()` using `LLM_API_KEY`/`LLM_MODEL` (with `GROQ_*` fallback) from `backend/.env`
- Correction loop: `valkyrie_node.py` calls SAGE `/sql/correct` per failed intent, re-validates (max 2 rounds)
- Synthesizer context: packages `{request_id, prompt, security_profile, intents, validated_sql_results, retrieved_context}` on pass

### VALKYRIE — SQL Validator Microservice
```bash
# VALKYRIE — SQL Validator
cd Agents/SQLValidator
pip install fastapi uvicorn python-dotenv pyyaml
python valkyrie.py               # :8004
```

### RAVEN — RAG Query Agent
```bash
# RAVEN — Retrieval and Vector Exploration Network
cd Agents/VectorDBagent
pip install -r requirements.txt
uvicorn raven:app --host 0.0.0.0 --port 8006 --reload   # :8006
# → POST /rag/query
# → GET  /health
# Embeds unstructured intents (BAAI/bge-large-en-v1.5, 1024-dim)
# Validates domain access against security_profile
# Returns similarity_search_inputs[] for SPYDER
```

### Pipeline Queue (`Agents/pipeline_queue/`)

`{request_id}.json` per passed + classified prompt. Git-ignored (`*.json`). Contains full pipeline state: guardrails, security_profile, intent_result with retrieved_context. `next_agent: "sql_generator"`.

### RAG Pipeline (`backend/app/rag/`)

- `embedder.py` — `BAAI/bge-large-en-v1.5` (1024-dim L2-norm); `warmup()` at startup
- `extractor.py` — PDF/DOCX/TXT/CSV/XLSX extraction
- `chunker.py` — recursive splitter, 800 chars / 100 overlap
- `storage.py` — DB writes: file record, chunks+embeddings, job/run lifecycle
- `pipeline.py` — background per-file orchestrator; per-file error isolation

`POST /api/rag/runs` → multipart/form-data → 202 + BackgroundTask.

### Frontend (`frontend/src/`)

- `main.jsx` — React Router v6, routes, auth wrapper, Toast provider
- `api/client.js` — Axios + JWT interceptor; all API functions here; `exportReport(data)` sends blob request to `/api/reports/export`
- `contexts/AuthContext.jsx` — Auth state, localStorage token, `theme`/`toggleTheme` (dark mode)
- `components/common/CRUDPage.jsx` — generic list/create/edit/delete
- `pages/Chats.jsx` — SpyderPanel: Recharts bar/line/pie charts + KPI tiles (single-row auto-detect) + data tables; export menu: CSV (Blob), Excel (SheetJS), PDF snapshot (html2canvas+jsPDF), Branded Report (backend reportlab); 👍👎 feedback buttons; `prompt` prop passed from prior user message
- `pages/UserProfile.jsx` — read-only profile (name/email/role/SGs) + change password form
- `pages/AgentManagement.jsx` — 3-section layout: **Agents** (two-panel config editor), **Observability** (KPI tiles, agent health grid, pipeline traces placeholder), **Evaluation** (feedback KPIs, SQL quality, intent classification, RAG quality — all placeholder)
- `pages/AppMapping.jsx` — Application User Mapping (admin only, dummy/frontend-only): left panel app list (seeded: Salesforce/Oracle/Outlook); right panel: user selector, per-API Read/Write checkboxes, auth-type-specific credential fields (Basic/API Key/OAuth2) with show/hide; Add Application + Add API modals; no backend wiring yet

Role-based nav: `User` role sees Chats + My Profile only. `Admin` sees all.

Frontend deps (key): `react`, `react-router-dom`, `axios`, `react-hot-toast`, `lucide-react`, `recharts`, `xlsx`, `html2canvas`, `jspdf`

Vite proxies `/api/*` → `http://localhost:8000`.

### Database

PostgreSQL, `tracopp` schema:
- **Auth/Users:** `User`, `Role`, `Permission`, `UserRole`, `RolePermission`, `UserSession`
- **Security:** `SecurityGroup`, `RowLevelSecurity`, `ColumnLevelSecurity` + mapping tables
- **Governance:** `Domain`, `SubDomain`, `Geography`
- **LLM:** `SLMConfig`, `DBConnection`, `PromptPolicy`, `PromptPolicyCheck`
- **Chat:** `ChatHistory`, `ChatMessage`
- **RAG:** `RagCategory`, `RagSubCategory`, `RagIngestionRun`, `RagFile`, `RagIngestionJob`, `RagIngestionError`, `RagDocumentChunk` (VECTOR 1024)
- **Audit:** `AuditLog`

## Environment

**Single source of truth: `backend/.env`** — all agents load from this file.

| Key | Used by |
|-----|---------|
| `DATABASE_URL` | Backend, ARIA, SAGE |
| `SECRET_KEY`, `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES` | Backend |
| `LLM_API_KEY` | All LLM agents (ARIA, SAGE, VALKYRIE, SPYDER) + Backend |
| `LLM_BASE_URL` | All LLM agents — default `https://api.groq.com/openai/v1`; swap to any OpenAI-compat endpoint |
| `LLM_MODEL` | All LLM agents — default `llama-3.3-70b-versatile` |
| `GROQ_API_KEY`, `GROQ_MODEL` | Fallback if `LLM_API_KEY`/`LLM_MODEL` not set (backward compat) |
| `EMBEDDER_BASE_URL` | ARIA, RAVEN, Heimdall — if set, calls remote `/v1/embeddings` instead of local model |
| `EMBEDDER_MODEL` | Remote embedder model name (default `BAAI/bge-large-en-v1.5`) |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_SSLMODE` | Heimdall |
| `TARGET_SCHEMA` | ARIA bootstrap, SAGE |

All agents use `LLM_*` env vars with `GROQ_*` as fallback — switching LLM provider only requires updating `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` in `backend/.env`.

Agent `.env` files (`Agents/*/env`) are empty stubs — all config comes from `backend/.env`.

`SCHEMA_FILE_PATH` is not in any `.env` — resolved in `sage.py` at startup as absolute path to `Agents/IntentClassifier/schema_reference.json`.

**Frontend** (`frontend/.env`): `VITE_BACKEND_URL`

Default admin: `admin@slm.local` / `Admin@1234` (created by `seed.py`).

## Known Issues

- **Pydantic Settings `extra='forbid'` (v2 default)** — `backend/app/core/config.py` uses `extra = "ignore"` so agent-only `.env` keys (`DB_HOST`, `GROQ_API_KEY`, `DB_SSLMODE`, etc.) don't crash backend startup. Do not remove this setting after single-`.env` consolidation.
- **`bootstrap_schema.py` must load from `backend/.env`** — uses absolute `_BACKEND_ENV` path (same pattern as `aria.py`). Plain `load_dotenv()` with no path reads the local empty stub and fails with `DATABASE_URL not set`.
- **`LLM_BASE_URL` must be base URL only** — e.g. `https://api.groq.com/openai/v1`. Code appends `/chat/completions`. Including the suffix causes double-path 404: `…/chat/completions/chat/completions`.
- **reportlab required for `/api/reports/export`** — add to backend venv: `pip install reportlab`. No system dependencies (pure Python). Already in `requirements.txt`.
