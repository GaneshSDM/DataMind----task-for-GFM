# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Backend
```bash
# From backend/
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Run migrations
alembic upgrade head

# Seed initial admin user and DB connection
python seed.py
```

### Frontend
```bash
# From frontend/
npm install
npm run dev        # dev server on :5173
npm run build
npm run preview
```

## Architecture

Full-stack SLM (Small Language Model) management platform with governance/security features.

**Stack:** React 18 + Vite (frontend) · FastAPI + SQLAlchemy 2.0 (backend) · PostgreSQL via Supabase · JWT auth

### Backend (`backend/app/`)

- `main.py` — FastAPI app, CORS, router registration, table auto-create on startup
- `core/config.py` — Pydantic Settings; reads `.env`; Supabase URL hardcoded here
- `core/security.py` — bcrypt hashing, JWT encode/decode, `get_current_user` dependency
- `db/session.py` — SQLAlchemy engine + `SessionLocal` + `get_db` dependency
- `models/user.py` — All 25+ ORM models in `schema="tracopp"`
- `schemas/schemas.py` — All Pydantic request/response models
- `api/routes/` — One file per domain: `auth`, `users`, `geo_domain`, `security`, `guardrails`, `chat`, `config`

API prefixes: `/api/auth`, `/api/users`, `/api/geographies`, `/api/domains`, `/api/subdomains`, `/api/security-groups`, `/api/rls`, `/api/cls`, `/api/guardrails`, `/api/chats`, `/api/slm-config`, `/api/db-connections`

All protected routes use `current_user = Depends(get_current_user)`. Admin-only ops call `check_admin()`.

### Frontend (`frontend/src/`)

- `main.jsx` — React Router v6 setup, 13 routes, auth wrapper, Toast provider
- `api/client.js` — Axios instance with JWT request interceptor + 401 logout interceptor; all API call functions defined here
- `contexts/AuthContext.jsx` — Auth state, `login()`/`logout()`, token in localStorage
- `components/common/CRUDPage.jsx` — Generic list/create/edit/delete component reused across pages
- `pages/` — One file per page; admin pages in `AdminPages.jsx`, master data in `MasterData.jsx`

Vite proxies `/api/*` → `http://localhost:8000` in dev.

### Database

PostgreSQL, all tables in `tracopp` schema. Key model groups:
- **Auth/Users:** `User`, `Role`, `Permission`, `UserRole`, `RolePermission`, `UserSession`
- **Security:** `SecurityGroup`, `RowLevelSecurity`, `ColumnLevelSecurity`, plus mapping tables
- **Governance:** `Domain`, `SubDomain`, `Geography`
- **LLM:** `SLMConfig`, `DBConnection`, `PromptPolicy`, `PromptPolicyCheck`
- **Chat:** `ChatHistory`, `ChatMessage`
- **Audit:** `AuditLog`

Migrations managed by Alembic (`alembic/versions/`).

## Environment

Copy `.env.example` → `.env` in both `backend/` and `frontend/`. Backend needs `DATABASE_URL`, `SECRET_KEY`, `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`. Frontend needs `VITE_BACKEND_URL`.

Default admin: `admin@slm.local` / `Admin@1234` (created by `seed.py`).
