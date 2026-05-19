# SLM Application

A full-stack enterprise application for managing Small Language Model interactions with security policies, guardrails, and role-based access control.

## Tech Stack

- **Frontend**: React 18 + Vite + React Router
- **Backend**: Python (FastAPI)
- **Database**: PostgreSQL
- **Auth**: JWT tokens

---

## Prerequisites

- Node.js 18+
- Python 3.10+
- PostgreSQL 14+

---

## Quick Start

### 1. Clone & Setup Database

```bash
# Create PostgreSQL database
psql -U postgres -c "CREATE DATABASE slm_app;"
psql -U postgres -c "CREATE USER slm_user WITH PASSWORD 'slm_password';"
psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE slm_app TO slm_user;"
```

### 2. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your database credentials

# Run migrations
alembic upgrade head

# Seed initial admin user
python seed.py

# Start API server
uvicorn app.main:app --reload --port 8000
```

Backend runs at: http://localhost:8000  
API docs: http://localhost:8000/docs

### 3. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Configure environment
cp .env.example .env
# Edit .env if backend runs on a different port

# Start dev server
npm run dev
```

Frontend runs at: http://localhost:5173

---

## Default Login

| Role  | Email               | Password    |
|-------|---------------------|-------------|
| Admin | admin@slm.local     | Admin@1234  |

---

## Project Structure

```
slm-app/
├── backend/
│   ├── app/
│   │   ├── api/routes/       # FastAPI route handlers
│   │   ├── core/             # Config, security, JWT
│   │   ├── db/               # Database session
│   │   ├── models/           # SQLAlchemy ORM models
│   │   ├── schemas/          # Pydantic request/response schemas
│   │   └── services/         # Business logic
│   ├── alembic/              # DB migrations
│   ├── requirements.txt
│   └── seed.py
└── frontend/
    ├── src/
    │   ├── api/              # Axios API client
    │   ├── components/       # Reusable UI components
    │   ├── contexts/         # React contexts (Auth)
    │   ├── pages/            # Page-level components
    │   └── styles/           # Global CSS tokens
    ├── package.json
    └── vite.config.js
```
