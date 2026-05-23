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

# Terminal 4 — Main backend
cd backend && uvicorn app.main:app --reload --port 8000    # :8000

# Terminal 5 — Frontend
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
- `api/routes/` — One file per domain: `auth`, `users`, `geo_domain`, `security`, `guardrails`, `chat`, `config`, `rag`

API prefixes: `/api/auth`, `/api/users`, `/api/geographies`, `/api/domains`, `/api/subdomains`, `/api/security-groups`, `/api/rls`, `/api/cls`, `/api/guardrails`, `/api/chats`, `/api/slm-config`, `/api/db-connections`, `/api/rag`

All protected routes use `current_user = Depends(get_current_user)`. Admin-only ops call `check_admin()`.

### Agent Orchestration (`backend/app/agents/`)

LangGraph pipeline invoked from `chat.py` on every prompt send.

**Current flow (Phase 3):**
```
guardrail_check → [blocked/error → END]
               → intent_classify → [error → END]
               → save_to_queue → sql_generate → END
```

- `orchestrator.py` — `StateGraph` wiring; `run_pipeline()` public entry point
- `guardrail_node.py` — HTTP POST → Heimdall `:8001`; returns `guardrail_status`, `blocked_by`, `guardrail_message`
- `intent_node.py` — HTTP POST → ARIA `:8002`; returns `intent_status`, `intent_result`, `intent_error`
- `queue_writer.py` — writes `Agents/pipeline_queue/{request_id}.json`; `stage: "intent_classified"`, `next_agent: "sql_generator"`
- `sql_node.py` — HTTP POST → SAGE `:8003`; returns `sql_status`, `sql_result`, `sql_error`

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
- `sql_agent.py` — core SQL generation: `get_provider()`, `resolve_tables()`, `generate_sql()`, `build_output()`, `run_correction()`; reads `SCHEMA_FILE_PATH` env var at module level
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
- `api/client.js` — Axios + JWT interceptor; all API functions here
- `contexts/AuthContext.jsx` — Auth state, localStorage token, `theme`/`toggleTheme` (dark mode)
- `components/common/CRUDPage.jsx` — generic list/create/edit/delete
- `pages/Chats.jsx` — reads `guardrail_status`, `blocked_by`, `intent_result`, `sql_result`; renders SQL code blocks (with RLS/CLS badges) then intent cards
- `pages/UserProfile.jsx` — read-only profile (name/email/role/SGs) + change password form

Role-based nav: `User` role sees Chats + My Profile only. `Admin` sees all.

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
| `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` | Backend chat route |
| `GROQ_API_KEY`, `GROQ_MODEL` | ARIA, SAGE |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_SSLMODE` | Heimdall |
| `TARGET_SCHEMA` | ARIA bootstrap, SAGE |

Agent `.env` files (`Agents/*/env`) are empty stubs — all config comes from `backend/.env`.

`SCHEMA_FILE_PATH` is not in any `.env` — resolved in `sage.py` at startup as absolute path to `Agents/IntentClassifier/schema_reference.json`.

**Frontend** (`frontend/.env`): `VITE_BACKEND_URL`

Default admin: `admin@slm.local` / `Admin@1234` (created by `seed.py`).
