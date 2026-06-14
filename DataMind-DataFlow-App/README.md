# DataMind — DataFlow (agentic ELT prototype)

A self-contained, **chat-driven** data-engineering app: ask in plain English and it runs a real
pipeline — **discover → ingest → transform → aggregate** — executing SQL against a **real Supabase
Postgres** warehouse. Built to mirror the DataMind `DataFlow` agent, packaged to run on `localhost`.

Styled as DataMind / Decision Minds. Same demo story, but every table, every SQL statement, and every
number is read back from the live database — nothing is mocked.

## What it does
- **Upload CSV files** (or use the bundled samples) as sources.
- **Discovery** profiles each file (column types + PII flags).
- **Ingestion** infers a schema, generates `CREATE TABLE` DDL, and loads rows into Supabase.
- **Transformation** runs real lookup joins (replace `category_id` → `category_name`) and value
  mapping (`gender_code` 1/2 → Male/Female).
- **Aggregation** joins transactions × product × customer into a fact table and rolls up revenue,
  with a chart.
- Everything lands in an isolated **`dataflow_demo`** schema, so existing tables are untouched.

## Requirements
- Python 3.10+
- Network access to the Supabase Postgres (already configured in `.env`)

## Run
```bash
# macOS / Linux
./run.sh
# Windows
run.bat
```
Then open **http://localhost:8000**.

Manual alternative:
```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app:app --port 8000
```

## Demo script (for Monday)
Click the suggestion chips in order:
1. **Show my connections** — detects the existing Supabase connection, no credentials prompted.
2. **Load the product table** — Discovery profile + generated DDL + real load into Supabase.
3. **Clean it up: map gender codes & replace category IDs with names** — real joins + value mapping.
4. **Aggregate total sales by category** — fact build + rollup + chart (total **$2,278**).

Or just **Run the full pipeline end-to-end**. You can also free-type (e.g. "aggregate by customer")
or upload your own CSV and say "load the <name> table".

## API
`GET /api/health` · `GET /api/sources` · `POST /api/upload` · `POST /api/ingest` ·
`POST /api/transform` · `POST /api/aggregate` · `GET /api/catalog` · `POST /api/reset`

## Configuration (`.env`)
```
DATABASE_URL=postgresql://...:6543/postgres   # Supabase pooler connection
TARGET_SCHEMA=dataflow_demo
```
`.env` is git-ignored. To point at a different warehouse, change `DATABASE_URL`.

## ⚠ Security note
The connection here was taken from the DataMind repo, where it was **committed in
`backend/.env.example`** (and the `slm.db` `db_connections` table). That means the DB password and a
Groq-style key are in git history and should be **rotated**, then kept only in an un-committed `.env`.
This app keeps the secret out of source and ignores `.env`.

## How it maps to the real product
The flow mirrors the DataMind `Agents/DataFlow` agent (discovery / ingestion / transformation /
quality / publish). Ingestion is generic for any CSV; the transform + aggregate steps are tuned to the
retail demo schema (products / categories / customers / transactions). The same agent logic runs
against live Postgres/Snowflake in the full stack.
