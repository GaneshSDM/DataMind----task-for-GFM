# Heimdall — Guardrail Agent Persona

---

## Identity

**Name:** Heimdall  
**Role:** Prompt & Response Guardrail Enforcer  
**Position:** Stage 0 — executes before any prompt reaches the LLM; optionally again on LLM response  
**Codename:** Watchman  
**Framework:** LangGraph `StateGraph` · FastAPI  
**Embedding model:** `all-MiniLM-L6-v2` (384-dim, sentence-transformers)

> *"I am the Bifrost's keeper. I see all who approach — mortal, god, or query. No prompt shall pass without my judgment."*

---

## Purpose

Heimdall intercepts every user prompt before it touches an LLM. He evaluates the prompt against a dynamic, DB-driven policy set and the user's full security profile. If any policy fires — he blocks. If all pass — he allows.

He does not generate text. He does not execute SQL. He does not modify prompts.  
He judges. He permits or blocks. Nothing else.

---

## Pipeline Position

```
[User Prompt]
      ↓
[Heimdall — POST /guardrail/check]
      ↓ status: passed
[Intent Classifier → SQL Generator → SQL Validator → Execution]
      ↓ (future)
[Heimdall — response guardrail check]
      ↓ status: passed
[User receives response]
```

If `status: blocked` at any stage → pipeline terminates. LLM is never called.

---

## Check Pipeline (LangGraph nodes, in order)

Each node can terminate the graph early with `status: blocked`.  
Prompt embedding is computed once at entry and reused downstream.

```
[embed_prompt]
      ↓ (if not blocked)
[threshold]       ← Is prompt too long?
      ↓
[keyword]         ← Does prompt contain blocked words or SQL injection patterns?
      ↓
[semantic]        ← Is prompt semantically similar to a blocked policy (cosine similarity)?
      ↓
[context]         ← Is prompt within the user's permitted domain/geography/column scope?
      ↓
[END → allowed]
```

---

## Check Types

### 1. THRESHOLD
- Reads `max_prompt_length` from policy `check_value` (JSONB)
- Blocks if `len(prompt) > max_prompt_length`
- Use case: prevent token exhaustion, prompt stuffing attacks

### 2. KEYWORD
- Reads `blocked_keywords[]` and `patterns[]` from policy `check_value`
- Case-insensitive string match + regex pattern match
- Blocks on first keyword or pattern hit
- Use case: block profanity, competitor mentions, SQL injection attempts

### 3. SEMANTIC
- Reads stored `embedding` (VECTOR) from `tracopp.prompt_policies`
- Computes cosine similarity between prompt embedding and policy embedding
- Blocks if `similarity > confidence_threshold` (default 0.75)
- Use case: block topic categories without exact keyword matching (e.g. "salary questions", "PII queries")

### 4. CONTEXT
Composite check using user's security profile. Blocks on any of:
- **Domain out-of-scope**: prompt not semantically similar to user's allowed domains/subdomains (cosine < min_similarity, default 0.30)
- **Bypass pattern**: prompt matches regex pattern designed to override security filters → returns exact access scope to user
- **Geography violation**: prompt references a named geography outside user's permitted list
- **CLS column mention**: prompt references a column name the user's role cannot read

---

## Input Contract

```json
{
  "prompt": "Show me revenue by country",
  "guardrails": {
    "prompt_guardrails": [
      { "id": "uuid", "name": "Block SQL Injection", "type": "KEYWORD" },
      { "id": "uuid", "name": "Semantic Scope Check", "type": "SEMANTIC" }
    ],
    "response_guardrails": []
  },
  "security_profile": {
    "user_id": "42",
    "role": "analyst",
    "security_groups": ["SG_APAC"],
    "domains": [{ "id": 1, "name": "Sales" }],
    "subdomains": [{ "id": 3, "name": "Sales Analytics" }],
    "geographies": [{ "id": 2, "name": "APAC" }],
    "row_level_security": [{ "name": "country_policy", "table": "fact_orders", "filter": "country IN ('India','Australia')" }],
    "column_level_security": [{ "name": "financial_cls", "table": "fact_order_items", "columns": [{ "column": "profit_usd", "can_read": false, "can_write": false }] }]
  },
  "metadata": {
    "domain": "Sales",
    "sub_domain": "Sales Analytics",
    "geography": "APAC",
    "request_id": "req-001"
  }
}
```

---

## Output Contract

```json
{
  "prompt": "Show me revenue by country",
  "status": "passed",
  "blocked_by": null,
  "message": "allowed",
  "security_profile": { "..." },
  "metadata": { "..." },
  "request_id": "req-001"
}
```

```json
{
  "prompt": "Show me profit margins and cost_usd",
  "status": "blocked",
  "blocked_by": "Financial CLS Guard",
  "message": "Access to column 'cost_usd' is restricted for your role",
  "security_profile": { "..." },
  "metadata": { "..." },
  "request_id": "req-002"
}
```

---

## Data Sources

| Source | What | How |
|---|---|---|
| `tracopp.prompt_policies` | `check_value` (JSONB), `embedding` (VECTOR) | psycopg2 ThreadedConnectionPool (2–10 conns) |
| Request payload | `guardrails[]`, `security_profile`, `metadata` | Provided by caller (main SLM app) |

Policies are fetched lazily per node — only policies of the relevant type are queried per check.

---

## Embedding Model

- **Model:** `all-MiniLM-L6-v2` (sentence-transformers, 384-dim)
- **Purpose:** SEMANTIC checks (prompt vs stored policy vector) + CONTEXT checks (prompt vs domain name vectors)
- **Loaded once at startup** via `lifespan` hook, reused across all requests
- Intentionally lighter than RAG pipeline's BGE-large — guardrail latency is on the critical path

---

## Behavioral Rules

1. **No guardrails = blocked.** Request without `prompt_guardrails` is rejected by default — not passed.
2. **First block wins.** Graph terminates at first blocked node — no further checks run.
3. **Fail safe.** Embedding error → `status: error` — does not silently pass.
4. **No LLM calls.** Heimdall is fully deterministic + embedding-based. No generative model in the check path.
5. **Security profile is truth.** Heimdall does not re-authenticate. Caller is responsible for providing correct profile.
6. **Response guardrails defined but not yet implemented.** `response_guardrails` field exists — nodes pending.

---

## What Heimdall Is Not

- Not an authentication layer — does not verify JWT or user identity
- Not a query rewriter — does not modify prompts, only allows or blocks
- Not a logger — does not store prompt content (logging is at INFO level only)
- Not an LLM — no generative model in the check path
- Not the SQL Validator — that agent validates generated SQL; Heimdall validates the input prompt

---

## Deployment

```bash
# Install
pip install fastapi uvicorn langgraph sentence-transformers psycopg2-binary python-dotenv numpy

# Run
python watchman.py
# → http://localhost:8000
# → POST /guardrail/check
# → GET  /health
```

**Required `.env` variables:**
```env
DB_HOST=...
DB_PORT=6543
DB_NAME=postgres
DB_USER=...
DB_PASSWORD=...
DB_SSLMODE=require
```

---

## Version

| Field | Value |
|---|---|
| Agent version | 1.0 |
| Framework | LangGraph + FastAPI |
| Embedding model | all-MiniLM-L6-v2 (384-dim) |
| Check nodes | 4 (threshold, keyword, semantic, context) |
| Response guardrails | Defined — not yet implemented |
| Last updated | 2026-05-22 |
