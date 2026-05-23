# SLM Application — DataMind / Decision Minds

Enterprise platform for governed Small Language Model interactions with multi-agent AI pipeline, security policies, guardrails, and role-based access control.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18 + Vite + React Router |
| Backend | Python 3.10+ · FastAPI · SQLAlchemy 2.0 |
| Database | PostgreSQL (Supabase) · pgvector |
| Auth | JWT tokens · bcrypt |
| AI Pipeline | LangGraph · Groq (llama-3.3-70b-versatile) · BAAI/bge-large-en-v1.5 |

---

## Agent Pipeline

```
User Prompt
    │
    ▼
Heimdall :8001          Guardrail check (threshold / keyword / semantic / context)
    │  blocked → return error bubble
    ▼
ARIA :8002              Intent classification → atomic intents with domain/table/RAG context
    │  error → return error bubble
    ▼
Pipeline Queue          Write {request_id}.json for audit
    ▼
SAGE :8003              NL → PostgreSQL per structured intent (RLS/CLS enforced)
    ▼
Frontend                SQL code blocks + intent cards + retrieved context chunks
```

| Agent | Role | Port | LLM |
|-------|------|------|-----|
| Heimdall | Guardrail enforcement | 8001 | sentence-transformers (local) |
| ARIA | Intent classification | 8002 | Groq llama-3.3-70b-versatile |
| SAGE | SQL generation | 8003 | Groq llama-3.3-70b-versatile |

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

LLM_API_KEY=gsk_...          # Groq API key (backend chat route)
LLM_BASE_URL=https://api.groq.com/openai/v1/chat/completions
LLM_MODEL=llama-3.3-70b-versatile

GROQ_API_KEY=gsk_...         # Groq API key (ARIA + SAGE agents)
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

### 2. Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
alembic upgrade head
python seed.py               # creates admin@slm.local / Admin@1234
uvicorn app.main:app --reload --port 8000
```

### 3. Agents

```bash
# Heimdall — Guardrail
cd Agents/Guardrail
pip install fastapi uvicorn langgraph sentence-transformers psycopg2-binary python-dotenv numpy
python watchman.py           # :8001

# ARIA — Intent Classifier
cd Agents/IntentClassifier
pip install fastapi uvicorn sentence-transformers psycopg2-binary python-dotenv httpx
python bootstrap_schema.py   # run once to generate schema_reference.json
python aria.py               # :8002

# SAGE — SQL Generator
cd Agents/SQLGenerator
pip install fastapi uvicorn groq python-dotenv psycopg2-binary
python sage.py               # :8003
```

### 4. Frontend

```bash
cd frontend
npm install
npm run dev                  # :5173
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
│   │   │   ├── orchestrator.py       ← StateGraph: guardrail→intent→queue→sql
│   │   │   ├── guardrail_node.py     ← → Heimdall :8001
│   │   │   ├── intent_node.py        ← → ARIA :8002
│   │   │   ├── sql_node.py           ← → SAGE :8003
│   │   │   └── queue_writer.py       ← writes pipeline_queue/{id}.json
│   │   ├── api/routes/               ← auth, users, chat, guardrails, rag, ...
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
│   └── SQLGenerator/                 ← SAGE :8003
│       ├── sage.py
│       ├── sql_agent.py
│       ├── examples.json             ← 30 few-shot SQL examples
│       └── correction_examples.json  ← 30 validation correction examples
└── frontend/
    └── src/
        ├── pages/
        │   ├── Chats.jsx             ← SQL blocks + intent cards + RAG chunks
        │   ├── UserProfile.jsx       ← read-only profile + change password
        │   └── ...                   ← admin CRUD pages
        ├── contexts/AuthContext.jsx  ← auth + dark mode
        └── components/layout/AppShell.jsx ← role-based nav
```

---

## Security Model

- **Guardrails** — prompt policies checked before any LLM call (threshold/keyword/semantic/context)
- **RLS** — WHERE clause injected into generated SQL per user's row-level security policies
- **CLS** — restricted columns stripped from schema sent to LLM; never appear in SELECT
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
| GET | `/api/chats/` | List user's chats |
| POST | `/api/rag/runs` | Ingest documents (multipart) |
| GET | `/api/guardrails/` | List guardrail policies |
