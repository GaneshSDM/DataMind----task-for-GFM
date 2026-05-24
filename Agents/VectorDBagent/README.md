# Vector DB Agent

A Python CLI agent for managing vector embeddings in Supabase Postgres RAG tables.

## Overview

This tool connects to the Supabase Postgres database and provides:

- **Create** — Generate embeddings for document chunks using sentence-transformers
- **Check** — See which chunks have embeddings and which don't
- **Validate** — Check embedding quality (dimensions, nulls, coherence)
- **Report** — Full database status report with schema and coverage

## Database Tables

```
tracopp.rag_files           — Uploaded documents
tracopp.rag_category        — Document categories
tracopp.rag_sub_category    — Sub-categories
tracopp.rag_document_chunks — Chunked text with embeddings
```

## Setup

```bash
cd "vector db agent"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Copy and edit the .env file
cp .env.example .env
```

**Note for WSL users**: Supabase DB hostnames may only resolve to IPv6, which WSL can't route. The connector will attempt the pooler as fallback. If direct connection fails, try:

```bash
# Option 1: Use Supabase pooler (set in .env)
DB_POOLER_HOST=aws-0-ap-southeast-1.pooler.supabase.com
DB_POOLER_PORT=6543

# Option 2: Run from Windows PowerShell/Python instead
```


## Web UI

Start the UI server and open in your browser:

```bash
source .venv/bin/activate
pip install -r requirements.txt  # adds Flask

python webui.py
```

Then visit `http://localhost:5000` (or your WSL IP at `\`hostname -I\``:5000).

Dashboard tabs:
| Tab | What it does |
|-----|-------------|
| **Dashboard** | Live embedding counts, coverage %, per-category progress bars |
| **Schema** | Table columns, types, nullability, row counts |
| **Create** | Run embedding generation with optional limit and dry-run |
| **Validate** | Check dimensions, nulls, and sample vector quality |
| **Report** | Full text report of database state |

Press **Ctrl+C** to stop the server.

## CLI Usage

```bash
source .venv/bin/activate

# Show database schema and row counts
python -m vector_agent.cli schema

# Check embedding status
python -m vector_agent.cli check
python -m vector_agent.cli check --by-category

# Generate embeddings for chunks without them
python -m vector_agent.cli create
python -m vector_agent.cli create --limit 10 --dry-run

# Validate embeddings
python -m vector_agent.cli validate
python -m vector_agent.cli validate --sample 50

# Full report
python -m vector_agent.cli report
```

## Connection Flow

```
1. Try direct connection (IPv4)
   ↓ fails
2. Try pooler (aws-0-ap-southeast-1.pooler.supabase.com:6543)
   ↓
3. Connected! Query tracopp.* tables
```

## Embedding Model

Default: `all-MiniLM-L6-v2` (384 dimensions)

Change in `.env`:
```
EMBEDDING_MODEL=all-mpnet-base-v2
EMBEDDING_DIM=768
```
