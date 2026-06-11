---
name: add-database-driver
description: How to extend the DataMind db_connections feature to support a new warehouse/driver (Snowflake, BigQuery, Redshift, etc.) alongside PostgreSQL
source: auto-skill
extracted_at: '2026-06-11T13:40:27.240Z'
---

# Adding a new database driver to DBConnection

The `DBConnection` model in `backend/app/models/user.py` is the single point that stores user-defined data source connections. PostgreSQL was the only type originally. When a new driver is needed (Snowflake, BigQuery, Redshift, etc.), use this four-step pattern.

## When to use

User asks to "add Snowflake / BigQuery / Redshift support", "connect to a new database type", or wants to make the DB Connections UI support anything beyond host/port/db/user/password.

## Steps

### 1. Model — `backend/app/models/user.py`

Add two columns to the `DBConnection` class:

```python
db_type        = Column(String, nullable=False, server_default="postgres")  # 'postgres' | 'snowflake' | ...
extra_config   = Column(JSONB, nullable=True)                                # driver-specific knobs
```

`server_default="postgres"` keeps existing rows valid. The `extra_config` JSONB holds fields that don't fit the base columns (account, warehouse, project, dataset, role, authenticator, etc.).

### 2. Pydantic schemas — `backend/app/schemas/schemas.py`

Extend `DBConnectionCreate` and `DBConnectionOut`:

```python
class DBConnectionCreate(BaseModel):
    ConnectionName: str
    DbType: str = "postgres"          # 'postgres' | 'snowflake' | ...
    Host: str
    Port: int = 5432
    DatabaseName: str
    Username: str
    Password: Optional[str] = None
    # driver-specific (flat, not nested — easier on frontend)
    Account: Optional[str] = None
    Warehouse: Optional[str] = None
    Role: Optional[str] = None
    Schema: Optional[str] = None
    Authenticator: Optional[str] = None
```

Flat fields beat nested JSON for the form. Add the same fields to `DBConnectionOut` so the list endpoint returns them.

### 3. Route — `backend/app/api/routes/config.py`

`list`, `create`, and `test` all branch on `db_type`. Important patterns:

- Build a `_serialize_connection(c: DBConnection)` helper that flattens `extra_config` into the response. Reuse it in both `list` and `create` to avoid drift.
- In `create`, build the `extra_config` dict from the driver-specific fields only when the type matches (e.g. only for `snowflake`).
- In `test`, import the driver lazily inside the branch so a missing optional dep doesn't break the whole route:
  ```python
  if db_type == "snowflake":
      import snowflake.connector
      conn = snowflake.connector.connect(account=..., user=..., ...)
  ```
- For drivers that support SSO/ODBC (`externalbrowser`, OAuth), don't require a password — only pass it if explicitly set.
- Always return `db_type` in the test response so the frontend can label the toast.

### 4. Frontend — `frontend/src/pages/AdminPages.jsx` (`DBConnectionsPage`)

- Add a `DbType` dropdown at the top of the modal. On change, swap the form to a type-specific default (define `EMPTY_PG_FORM` and `EMPTY_SF_FORM` constants). Preserve `ConnectionName` / `Username` / `Password` across switches.
- Render driver-specific field groups conditionally: `{form.DbType === 'snowflake' ? <SnowflakeFields /> : <PostgresFields />}`.
- In the list table, show a `Type` column tag and the driver-specific host key (Account for Snowflake, Project for BigQuery, etc.).
- For Snowflake specifically: `Host` field is replaced by `Account` on the form, but the backend still expects a non-null `Host`, so the frontend maps `Host: form.Account || form.Host, Port: 443` in the save/test payload.

## Migration reminder

`Base.metadata.create_all` only creates **missing tables**, not missing columns. After adding columns, you need either:
- Alembic: `alembic revision --autogenerate -m "add db_type + extra_config to db_connections"` + `alembic upgrade head`, or
- One-shot SQL: `ALTER TABLE tracopp.db_connections ADD COLUMN IF NOT EXISTS db_type VARCHAR(32) NOT NULL DEFAULT 'postgres', ADD COLUMN IF NOT EXISTS extra_config JSONB;`

## Don't forget

- Add the new connector to `backend/requirements.txt` (e.g. `snowflake-connector-python>=3.7.0`).
- The agent env vars (`DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`) in `backend/.env` are the **app's own Postgres** (Supabase). They are NOT the same thing as the `DBConnection` rows the user creates — those are separate user data source connections stored in the `tracopp.db_connections` table.

## Env gotcha

`LLM_BASE_URL` must be base URL only (e.g. `https://api.groq.com/openai/v1`) — the code appends `/chat/completions`. Including the suffix causes `…/chat/completions/chat/completions` 404s. `CLAUDE.md` documents this. The default in `backend/app/core/config.py` was wrong (`/chat/completions` suffix) and was fixed.
