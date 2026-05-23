# Universal Synthesizer Agent App

A domain-agnostic full-stack application that receives a structured JSON payload,
executes SQL queries, runs PgVector RAG similarity searches, synthesizes everything
with an LLM (Gemma 4 26B via Google AI Studio), and renders a beautiful dashboard.

---

## Prerequisites

| Requirement | Version  | Download |
|-------------|----------|----------|
| Python      | 3.10+    | https://www.python.org/downloads/ |
| Node.js     | 18+ (LTS)| https://nodejs.org/en/download — **needed only once to enable Tailwind CDN in browsers; no npm install required otherwise** |

> **Note:** This app does NOT use npm or a React build step.  
> The frontend is plain HTML + Tailwind CDN + vanilla JS served by FastAPI.  
> Node.js is NOT required to run this app.

---

## One-Time Setup

### 1 — Clone / Extract the project

The project lives at:
```
C:\Synthesizer_Agent\
```

### 2 — Create a Python virtual environment

Open **Command Prompt** or **PowerShell** and run:

```cmd
cd C:\Synthesizer_Agent\backend
python -m venv venv
venv\Scripts\activate
```

### 3 — Install Python dependencies

```cmd
pip install -r requirements.txt
```

### 4 — Verify the .env file

The `.env` file in `backend\` is pre-configured with your credentials.  
To inspect or change them:

```
backend\.env
```

Key variables:
- `DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASSWORD` — Supabase PostgreSQL
- `GEMINI_API_KEY` / `GEMINI_MODEL` — Google AI Studio (Gemma 4 26B)

---

## Running the App

```cmd
cd C:\Synthesizer_Agent\backend
venv\Scripts\activate
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Then open your browser at:

```
http://localhost:8000
```

---

## Using the App

### From the UI (manual JSON paste)

1. The JSON editor on the left is pre-loaded with the **Sales domain sample JSON**
2. Edit the JSON or paste a new one from the upstream agent
3. Click **Validate JSON** to check for errors before running
4. Click **Run Synthesis** — watch the progress tracker light up in real time
5. View results in the **Dashboard** tab (tables, charts, LLM answer)
6. Inspect raw data in the **Raw Data** tab
7. Check execution timing in the **Logs** tab
8. Use **Copy Answer** or **Download** to export results

### From the upstream agent (API)

POST the JSON payload directly to:
```
POST http://localhost:8000/api/submit-json
Content-Type: application/json
```

The UI will detect the new submission within 5 seconds and load it into the editor automatically.

---

## API Endpoints

| Method | Path                     | Description                                      |
|--------|--------------------------|--------------------------------------------------|
| GET    | `/api/health`            | Database, PgVector, and LLM health check         |
| POST   | `/api/validate-json`     | Validate JSON contract (returns errors/warnings) |
| POST   | `/api/synthesize`        | Full pipeline — SSE streaming response           |
| POST   | `/api/submit-json`       | Upstream agent submits JSON payload              |
| GET    | `/api/latest-submission` | Frontend polls for new agent submissions         |

### SSE Event format (`POST /api/synthesize`)

The endpoint streams Server-Sent Events:

```json
{ "event": "progress", "step": "validate_json", "status": "in_progress", "message": "…" }
{ "event": "progress", "step": "execute_sql",   "status": "completed",   "data": [SQL results] }
{ "event": "complete",  "data": { "sql_results": […], "rag_results": […], "llm_response": {…} } }
{ "event": "error",     "step": "execute_sql",   "message": "…", "errors": ["…"] }
```

---

## JSON Contract

The full expected JSON structure:

```json
{
  "request_id": "REQ-DOMAIN-001",
  "app_context":         { "domain": "Sales", "objective": "…", … },
  "persona":             { "role": "…", "instruction": "…" },
  "user_query":          "Your question here",
  "input_contract":      { "structured_tables_allowed": […], "rag_table": "…", … },
  "sql_parameters":      { … },
  "structured_inputs":   { "sql_scripts": [{ "query_id": "SQL_001", "sql": "SELECT …", … }] },
  "unstructured_inputs": { "similarity_search_inputs": [{ "embedding_id": "EMB_001", "embedding": […], … }] },
  "execution_flow":      { "steps": […], "parallel_sql_execution": true, … },
  "synthesis_instruction": { "treat_structured_as": "source_of_truth", … },
  "expected_output_schema": { "sections": [{ "section_id": "…", "display_type": "text|table_and_chart|list", "source": "sql|rag|llm" }] },
  "error_handling":      { "on_sql_error": "continue_with_warning", … }
}
```

A fully populated Sales example is pre-loaded in the editor when the app starts.

---

## Project Structure

```
C:\Synthesizer_Agent\
├── backend\
│   ├── main.py                  ← FastAPI app entry point
│   ├── config.py                ← Pydantic settings (reads .env)
│   ├── requirements.txt
│   ├── .env                     ← Your credentials (pre-configured)
│   ├── routes\
│   │   ├── health.py            ← GET  /api/health
│   │   ├── validate.py          ← POST /api/validate-json
│   │   ├── synthesize.py        ← POST /api/synthesize  (SSE)
│   │   └── submit.py            ← POST /api/submit-json
│   ├── services\
│   │   ├── json_validator.py    ← SQL safety + contract validation
│   │   ├── sql_service.py       ← PostgreSQL SELECT execution
│   │   ├── rag_service.py       ← PgVector similarity search
│   │   └── llm_service.py       ← Google AI Studio (Gemma) synthesis
│   └── static\
│       ├── index.html           ← Single-page frontend (no build step)
│       ├── js\app.js            ← All frontend JavaScript
│       └── css\custom.css       ← Custom styles
├── .env.example                 ← Template (credentials redacted)
└── README.md
```

---

## Supported Domains

The app is fully domain-agnostic. Pass any domain in `app_context.domain`:

`Sales` · `Finance` · `HR` · `Marketing` · `Operations` · `Procurement` · `Legal` · `Support` · `Inventory` · `Supply Chain` · _any other_

Each domain gets a unique colour badge in the UI automatically.

---

## Security Notes

- Only `SELECT` SQL statements are permitted — all others are rejected
- Every table is validated against `input_contract.structured_tables_allowed`
- Database credentials live in `.env` on the server — never exposed to the browser
- Embedding vectors are validated as numeric-only before SQL interpolation
