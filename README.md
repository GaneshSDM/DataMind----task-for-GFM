# SLM Application — DataMind / Decision Minds

Enterprise platform for governed Small Language Model interactions with multi-agent AI pipeline, security policies, guardrails, and role-based access control.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18 + Vite + React Router |
| Backend | Python 3.10+ · FastAPI · SQLAlchemy 2.0 |
| Database | PostgreSQL (Supabase) · pgvector |
| Auth | JWT tokens · bcrypt |
| AI Pipeline | LangGraph · OpenAI-compatible LLM (default: Groq llama-3.3-70b-versatile) · BAAI/bge-large-en-v1.5 |

---

## Agent Pipeline

```
User Prompt
    │
    ▼
Heimdall :8001       Guardrail check (threshold / keyword / semantic / context)
    │  blocked → blocked bubble
    ▼
ARIA :8002           Intent classification → atomic intents (Structured / Unstructured / Both)
    │                + receives chat context: [SUMMARY] + [RECENT TURNS] from prior turns
    │  error → intent error bubble
    │  out_of_scope → 🔒 scope message
    ▼
Pipeline Queue       Write {request_id}.json for audit trail
    ▼
SAGE :8003           NL → PostgreSQL per structured intent (RLS/CLS enforced)
    ▼
VALKYRIE :8004       SQL validation + correction loop (max 2 rounds via SAGE /sql/correct)
    ▼
RAVEN :8006          Domain access check + embed unstructured intents → pgvector inputs
    ▼
SPYDER :8005         Execute SQL + RAG retrieval + LLM synthesis → final response
    ▼
Frontend             Synthesized answer (SpyderPanel) or error bubbles
```

| Agent | Role | Port | LLM |
|-------|------|------|-----|
| Heimdall | Prompt guardrail enforcement | 8001 | all-MiniLM-L6-v2 (local) |
| ARIA | Intent classification | 8002 | Configurable via LLM_MODEL (default: Groq) |
| SAGE | SQL generation | 8003 | Configurable via LLM_MODEL (default: Groq) |
| VALKYRIE | SQL validation + correction | 8004 | Configurable via LLM_MODEL (default: Groq) |
| RAVEN | RAG domain access + embedding | 8006 | BAAI/bge-large-en-v1.5 (local) |
| SPYDER | SQL exec + RAG synthesis | 8005 | Configurable via LLM_MODEL (default: Groq) |

---

## Prerequisites

- Node.js 18+
- Python 3.10+
- PostgreSQL 14+ with pgvector extension

---

## Quick Start

### 1. Configure Environment

All configuration lives in a **single `.env` file** at `backend/.env`:

```env
DATABASE_URL=postgresql://user:password@host:port/dbname
SECRET_KEY=your-secret-key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=480

LLM_API_KEY=gsk_...
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_MODEL=llama-3.3-70b-versatile

# Optional — remote embedding API (default: local BAAI/bge-large-en-v1.5)
# EMBEDDER_BASE_URL=https://your-embedder-host/v1
# EMBEDDER_MODEL=BAAI/bge-large-en-v1.5

GROQ_API_KEY=gsk_...         # Fallback if LLM_API_KEY not set (backward compat)
GROQ_MODEL=llama-3.3-70b-versatile
TARGET_SCHEMA=sales

DB_HOST=...                  # Individual DB vars for Heimdall
DB_PORT=6543
DB_NAME=postgres
DB_USER=...
DB_PASSWORD=...
DB_SSLMODE=require
```

Agent `.env` files are empty stubs — all agents load from `backend/.env`.

> **Note:** The backend Pydantic Settings model uses `extra = "ignore"`, so agent-only keys in the same file (`DB_HOST`, `GROQ_API_KEY`, `DB_SSLMODE`, etc.) are safe and will not cause backend startup errors.

### 2.1 Frontend

```bash
cd frontend
npm install
npm run dev                  # :5173
```

### 2.2 Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
alembic upgrade head
python seed.py               # creates admin@slm.local / Admin@1234 + seeds agent configs
uvicorn app.main:app --reload --port 8000
```

### 3. Agents

**Option A — single launch script (recommended):**

```bash
python .\Agents\IntentClassifier\bootstrap_schema.py
python start_all.py   # starts all agents + backend + frontend in correct order
```

**Option B — manual:**

```bash
# Heimdall — Guardrail
cd Agents/Guardrail
pip install fastapi uvicorn langgraph sentence-transformers psycopg2-binary python-dotenv numpy
python watchman.py           # :8001

# ARIA — Intent Classifier
cd Agents/IntentClassifier
pip install fastapi uvicorn sentence-transformers psycopg2-binary python-dotenv httpx openai
python bootstrap_schema.py   # run once — generates schema_reference.json
python aria.py               # :8002

# SAGE — SQL Generator
cd Agents/SQLGenerator
pip install fastapi uvicorn openai python-dotenv psycopg2-binary
python sage.py               # :8003

# VALKYRIE — SQL Validator
cd Agents/SQLValidator
pip install fastapi uvicorn python-dotenv openai
python valkyrie.py           # :8004

# RAVEN — RAG Query Agent
cd Agents/VectorDBagent
pip install -r requirements.txt
uvicorn raven:app --host 0.0.0.0 --port 8006 --reload   # :8006

# SPYDER — Synthesizer
cd Agents/Synthesizer/backend
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8005 --reload     # :8005
```



---

## Default Login

| Role  | Email           | Password   |
|-------|-----------------|------------|
| Admin | admin@slm.local | Admin@1234 |

---

## Project Structure

```
slm-app/
├── backend/
│   ├── .env                          ← Single source of truth for all config
│   ├── app/
│   │   ├── agents/                   ← LangGraph orchestrator + nodes
│   │   │   ├── orchestrator.py       ← StateGraph: guardrail→intent→queue→sql→validate
│   │   │   ├── guardrail_node.py     ← → Heimdall :8001
│   │   │   ├── intent_node.py        ← → ARIA :8002
│   │   │   ├── sql_node.py           ← → SAGE :8003
│   │   │   ├── valkyrie_node.py      ← → VALKYRIE :8004 (correction loop, max 2 rounds)
│   │   │   └── queue_writer.py       ← writes pipeline_queue/{id}.json
│   │   ├── api/routes/               ← auth, users, chat, guardrails, agents, rag, ...
│   │   ├── core/                     ← config, security, JWT
│   │   ├── db/                       ← SQLAlchemy session
│   │   ├── models/                   ← 25+ ORM models (tracopp schema)
│   │   ├── rag/                      ← embedding pipeline (PDF/DOCX/CSV/XLSX)
│   │   └── schemas/                  ← Pydantic request/response models
│   └── seed.py
├── Agents/
│   ├── pipeline_queue/               ← {request_id}.json audit files (git-ignored)
│   ├── Guardrail/                    ← Heimdall :8001
│   │   └── watchman.py
│   ├── IntentClassifier/             ← ARIA :8002
│   │   ├── aria.py
│   │   ├── bootstrap_schema.py       ← generates canonical schema_reference.json
│   │   ├── schema_reference.json     ← shared with SAGE (not committed)
│   │   └── core/
│   ├── SQLGenerator/                 ← SAGE :8003
│   │   ├── sage.py
│   │   ├── sql_agent.py
│   │   ├── examples.json             ← 30 few-shot SQL examples
│   │   └── correction_examples.json  ← 31 correction examples
│   ├── SQLValidator/                 ← VALKYRIE :8004
│   │   └── valkyrie.py
│   ├── VectorDBagent/                ← RAVEN :8006
│   │   └── raven.py
│   └── Synthesizer/                  ← SPYDER :8005
│       └── backend/main.py
└── frontend/
    └── src/
        ├── pages/
        │   ├── Chats.jsx             ← SpyderPanel synthesis; right sidebar (chats/clear/delete); copy response
        │   ├── UserProfile.jsx       ← two-column: profile info + change password
        │   ├── AgentManagement.jsx   ← admin: agent config + observability + evaluation
        │   ├── AppMapping.jsx        ← admin: app user mapping (top dropdown + full-width detail)
        │   ├── AgentSkills.jsx       ← admin: custom skills (top selector bar + editor)
        │   └── ...                   ← admin CRUD pages
        ├── contexts/AuthContext.jsx  ← auth + dark mode (theme/toggleTheme)
        └── components/layout/AppShell.jsx ← role-based nav (User: Chats+Profile; Admin: all)
```

---

## Frontend UI

### Chat Window (`Chats.jsx`)
- **Right collapsible sidebar** — chat list (240px expanded / 40px collapsed); toggle with chevron
- **Clear Chat** — clears current chat messages from view
- **Delete All History** — bulk deletes all chats (with confirmation)
- **Copy response** — Copy/Check button below each assistant bubble; copies synthesis text + SQL rows as TSV; 2s "Copied" feedback
- **User message bubble** — subtle background (removed blue fill for readability)
- **SpyderPanel** — Recharts charts (bar/line/pie) + KPI tiles + data table; export CSV/Excel/PDF/Branded Report

### My Profile (`UserProfile.jsx`)
- Two-column layout: read-only profile info (left) + change password form (right)

### App User Mapping (`AppMapping.jsx`)
- Top dropdown selector bar replaces left sidebar: app dropdown + auth badge + active toggle + Add API / Delete
- Full-width detail panel: user selector, API permissions (Read/Write), credentials by auth type

### Agent Skills (`AgentSkills.jsx`)
- Top selector bar replaces left panel: search + filter pills (All/View/Template) + skill dropdown + New Skill
- Full-width editor: name/type/domain, SQL template, parameters, invocation preview

---

## Chat Memory

Each chat maintains persistent conversation context stored in the assistant message `payload` JSONB column — no DB migration required.

**Two-level context sent to ARIA per request:**
```
[SUMMARY] User has been querying HR workforce data. Department counts, attrition analysis.
[RECENT TURNS]
  [HR] employee_table | cols: department, emp_id | Q: "Get dept-wise employee count"
  [HR] attrition_table | Q: "Show attrition rate by dept"
```

- **Recent turns** — last 3 successful turns (`domain`, `table`, `columns`, `user_prompt`)
- **Rolling summary** — generated by LLM (background task) when snapshot evicts oldest entry; covers full history beyond 3 turns
- **Safety** — only `pipeline_success=True` turns injected into ARIA context; failed pipeline turns stored but excluded; no synthesis data stored (prevents guardrail bypass)
- **ARIA CONTEXT RULE** — locks domain+table on explicit back-references (`"from the above"`, `"those"`, `"same"`); treats domain-like terms in follow-up queries as data filter values not domain reclassification

**Query to inspect chat summaries:**
```sql
SELECT cm.chat_id, cm.payload->>'chat_summary' AS summary,
       jsonb_array_length(cm.payload->'context_snapshot') AS turns
FROM tracopp.chat_messages cm
WHERE cm.role = 'assistant' AND cm.payload ? 'chat_summary'
ORDER BY cm.created_date DESC;
```

---

## Security Model

- **Guardrails** — prompt policies checked before any LLM call (threshold/keyword/semantic/context)
- **RLS** — WHERE clause injected into generated SQL per user's row-level security policies
- **CLS** — restricted columns stripped from schema sent to LLM; never appear in SELECT
- **SQL Validation** — VALKYRIE re-checks every generated query for syntax, RLS, CLS compliance; auto-corrects via SAGE up to 2 rounds before surfacing to frontend
- **Chat Memory** — conversation context persisted in DB (`assistant_payload["context_snapshot"]`); ARIA receives prior turn domain/table/query metadata; rolling LLM summary for long conversations; failed pipeline turns excluded from context; Heimdall still checks every new prompt independently
- **Role-based nav** — `User` role: Chats + My Profile only; `Admin`: full access
- **Security Groups** — users assigned to groups; groups carry domain/RLS/CLS policies

---

## Key API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/login` | JWT login |
| GET | `/api/auth/me` | Current user profile |
| POST | `/api/auth/change-password` | Self-service password change |
| POST | `/api/chats/send` | Send prompt → full pipeline |
| POST | `/api/chats/send/stream` | Send prompt → SSE streaming pipeline |
| GET | `/api/chats/` | List user's chats |
| POST | `/api/rag/runs` | Ingest documents (multipart) |
| GET | `/api/guardrails/` | List guardrail policies |
| GET | `/api/agents/` | List all agents with config |
| GET | `/api/agents/statuses` | Live health status of all 6 agents |
| PUT | `/api/agents/{name}` | Update agent config (admin only) |

---

## Environment

**Single source of truth: `backend/.env`** — all agents load from this file.

| Key | Used by |
|-----|---------|
| `DATABASE_URL` | Backend, ARIA, SAGE |
| `SECRET_KEY`, `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES` | Backend |
| `LLM_API_KEY` | All LLM agents (ARIA, SAGE, VALKYRIE, SPYDER) + Backend |
| `LLM_BASE_URL` | All agents — set to base URL only, e.g. `https://api.groq.com/openai/v1` (no `/chat/completions`) |
| `LLM_MODEL` | All agents — e.g. `llama-3.3-70b-versatile` |
| `GROQ_API_KEY`, `GROQ_MODEL` | Fallback if `LLM_API_KEY`/`LLM_MODEL` not set |
| `EMBEDDER_BASE_URL` | Optional — remote embedding API; if unset, local model used |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_SSLMODE` | Heimdall |
| `TARGET_SCHEMA` | ARIA bootstrap, SAGE |

`SCHEMA_FILE_PATH` is not in any `.env` — resolved at runtime in `sage.py` as an absolute path to `Agents/IntentClassifier/schema_reference.json`.

**Frontend** (`frontend/.env`): `VITE_BACKEND_URL`
