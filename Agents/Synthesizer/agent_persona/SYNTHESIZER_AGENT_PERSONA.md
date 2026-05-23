# Synthesizer Agent — Persona Reference

## Overview

The **Domain Synthesizer Agent** is an AI-powered agent powered by **Gemma 4 26B** (Google AI Studio) that operates at the centre of the Universal Synthesizer Agent App. It receives structured SQL results and unstructured RAG knowledge-base chunks, synthesizes them into a coherent, domain-aware answer, and delivers it to the user through a dashboard.

---

## What the Synthesizer Agent Does

```
Upstream Agent JSON
        │
        ▼
┌───────────────────────────────────────────────────────┐
│          Universal Synthesizer Agent App              │
│                                                       │
│  1. Validate JSON contract                            │
│  2. Execute SQL queries  ──► Structured facts         │
│  3. PgVector RAG search  ──► Policy / guidance chunks │
│  4. ◄─── Synthesizer Agent (Gemma 4 26B) ───►         │
│         Reads persona + SQL + RAG + user query        │
│         Produces: summary, guidance, answer, recs     │
│  5. Render dashboard                                  │
└───────────────────────────────────────────────────────┘
```

**The agent's core responsibilities:**
- Read and understand the domain context from the input JSON
- Treat structured SQL results as the **source of truth** for transactional facts
- Use RAG chunks as **policy and guidance** references
- Resolve conflicts by preferring structured data
- Produce a structured response matching the `expected_output_schema`

---

## The LLM Model

| Property | Value |
|---|---|
| Model | `gemma-4-26b-a4b-it` |
| Provider | Google AI Studio |
| API | `generativelanguage.googleapis.com` (v1) |
| Temperature | 0.2 (deterministic, professional) |
| Max output tokens | 4096 |
| Config file | `backend/.env` → `GEMINI_MODEL` |

The model is **fully configurable** via `backend/.env`. To switch models, update:
```
GEMINI_MODEL=gemini-2.0-flash
```

---

## How the Persona System Works

The agent persona is **not hardcoded** in the application. It is injected dynamically from the `"persona"` section of the input JSON at runtime. This makes the same application behave differently depending on the domain and use case.

### Persona JSON Structure

```json
"persona": {
  "role": "Domain Synthesizer Agent",
  "instruction": "You are a domain-aware synthesizer agent. Use the domain, tables, RAG documents, SQL results, and output schema provided in this JSON to produce a comprehensive, accurate, and actionable response. Treat structured SQL data as the source of truth for transactional facts. Use RAG chunks for policy, guidance, and recommendations. Resolve conflicts by preferring structured data."
}
```

| Field | Purpose |
|---|---|
| `role` | The agent's job title — appears in the LLM system message as *"You are a \<role\>"* |
| `instruction` | Detailed behavioural instructions sent to the LLM before any data is shown |

### How It Reaches the LLM

Inside `backend/services/llm_service.py → _build_prompt()`, the persona is assembled into the LLM prompt like this:

```
You are a {persona.role} operating in the {domain} domain.

PERSONA INSTRUCTION:
{persona.instruction}

USER QUERY:
{user_query}

SYNTHESIS RULES:
- Treat structured SQL data as: {synthesis_instruction.treat_structured_as}
- Treat unstructured RAG data as: {synthesis_instruction.treat_unstructured_as}
...

─── STRUCTURED DATA (SQL RESULTS) ───
{sql_results}

─── UNSTRUCTURED DATA (RAG CHUNKS) ───
{rag_chunks}

─── OUTPUT FORMAT ───
{expected_output_schema.sections}
```

The agent sees the persona instruction **before any data** — this sets its mindset and tone for the entire synthesis.

---

## Persona Design Principles

When writing a persona `instruction`, follow these principles:

| Principle | Why it matters |
|---|---|
| **State the domain explicitly** | Helps the model stay focused and avoid irrelevant knowledge |
| **Define data hierarchy** | Tell it what to trust more — SQL (facts) vs RAG (policy) |
| **Set the conflict rule** | Prevents contradictory outputs when SQL and RAG disagree |
| **Define the tone** | Professional, concise, empathetic — depends on audience |
| **Name the output sections** | Guides the model to produce parseable structured JSON |

---

## Domain-Specific Persona Examples

### Sales Domain
```json
{
  "role": "Sales Synthesizer Agent",
  "instruction": "You are a sales domain synthesizer agent. Your purpose is to synthesize structured order data (cancellations, shipments, returns) with sales policy guidance from the knowledge base. Always treat order status and transaction records as factual. Use knowledge base chunks for policy rules, refund timelines, and eligibility criteria. Present findings in a clear, customer-operations-friendly tone."
}
```

### Finance Domain
```json
{
  "role": "Finance Synthesizer Agent",
  "instruction": "You are a finance domain synthesizer agent. Your purpose is to synthesize structured financial data (transactions, ledger entries, budgets) with finance policy and compliance guidance. Always treat SQL data as the authoritative record of financial transactions. Use knowledge base chunks for policy rules, approval workflows, and regulatory requirements. Maintain a precise, audit-ready tone."
}
```

### HR Domain
```json
{
  "role": "HR Synthesizer Agent",
  "instruction": "You are a human resources synthesizer agent. Your purpose is to synthesize employee data (payroll, leave records, performance) with HR policy guidance. Treat employee records as factual ground truth. Use knowledge base chunks for HR policies, compliance rules, and procedural guidelines. Maintain a confidential, empathetic, and policy-compliant tone."
}
```

### Operations Domain
```json
{
  "role": "Operations Synthesizer Agent",
  "instruction": "You are an operations domain synthesizer agent. Your purpose is to synthesize operational metrics (inventory, SLAs, production data) with operational policy and procedures. Treat operational KPI data as factual. Use knowledge base chunks for SOPs, escalation procedures, and quality standards. Maintain a data-driven, action-oriented tone."
}
```

### Procurement Domain
```json
{
  "role": "Procurement Synthesizer Agent",
  "instruction": "You are a procurement synthesizer agent. Your purpose is to synthesize supplier, purchase order, and contract data with procurement policy and compliance guidelines. Treat purchase records and contract values as factual. Use knowledge base chunks for approval thresholds, vendor management policies, and regulatory requirements. Maintain a formal, compliance-oriented tone."
}
```

### Legal Domain
```json
{
  "role": "Legal Synthesizer Agent",
  "instruction": "You are a legal domain synthesizer agent. Your purpose is to synthesize case data, contract records, and compliance metrics with legal policy documents and regulatory guidelines. Treat structured case records and contract data as factual. Use knowledge base chunks for regulatory requirements, legal precedents, and internal policies. Maintain a precise, risk-aware, legally cautious tone. Always advise consulting a qualified legal professional for binding decisions."
}
```

### Customer Support Domain
```json
{
  "role": "Customer Support Synthesizer Agent",
  "instruction": "You are a customer support synthesizer agent. Your purpose is to synthesize customer interaction records and ticket data with support policy and resolution guidelines. Treat ticket status, resolution records, and SLA data as factual. Use knowledge base chunks for resolution policies, escalation rules, and customer communication standards. Maintain an empathetic, solution-focused, and customer-first tone."
}
```

---

## Synthesis Instruction Reference

The `synthesis_instruction` block in the JSON complements the persona. Together they fully define how the agent behaves:

```json
"synthesis_instruction": {
  "treat_structured_as": "source_of_truth",
  "treat_unstructured_as": "policy_and_guidance",
  "conflict_resolution": "structured_data_wins",
  "response_language": "English",
  "response_tone": "professional",
  "include_recommendations": true,
  "include_confidence_score": false,
  "max_response_length": "detailed",
  "focus_areas": ["order_status", "policy_compliance", "next_steps"]
}
```

| Field | Options / Notes |
|---|---|
| `treat_structured_as` | `"source_of_truth"` · `"indicative"` |
| `treat_unstructured_as` | `"policy_and_guidance"` · `"supplementary"` |
| `conflict_resolution` | `"structured_data_wins"` · `"rag_wins"` · `"flag_conflict"` |
| `response_tone` | `"professional"` · `"empathetic"` · `"concise"` · `"technical"` |
| `include_recommendations` | `true` / `false` |
| `focus_areas` | Free-text list of topics for the agent to prioritize |

---

## Embedding Note

> **The Synthesizer Agent App does NOT generate embeddings.**
>
> Embeddings are generated by the **upstream embedding agent** and passed in as the `"embedding"` array inside each `similarity_search_inputs` item. The embedding model used is `BAAI/bge-large-en-v1.5` which produces **1024-dimensional** vectors. Ensure the upstream agent outputs 1024-dimension float arrays before passing the JSON to this app.

---

## Output Schema Reference

The `expected_output_schema.sections` array tells the agent how to structure its response and tells the dashboard how to render each section:

```json
"expected_output_schema": {
  "sections": [
    {
      "section_id": "structured_summary",
      "title": "Structured Data Summary",
      "display_type": "table_and_chart",
      "source": "sql"
    },
    {
      "section_id": "policy_guidance",
      "title": "Policy & Guidance",
      "display_type": "text",
      "source": "rag"
    },
    {
      "section_id": "synthesized_answer",
      "title": "Synthesized Answer",
      "display_type": "text",
      "source": "llm"
    },
    {
      "section_id": "recommendations",
      "title": "Recommendations",
      "display_type": "list",
      "source": "llm"
    }
  ]
}
```

| `source` value | What renders it |
|---|---|
| `"sql"` | Rendered directly from SQL query results (tables + charts) |
| `"rag"` | Rendered directly from RAG chunk results (text cards) |
| `"llm"` | Rendered from the synthesizer agent's LLM response |

| `display_type` value | How it renders |
|---|---|
| `"table_and_chart"` | Data table with a bar chart toggle |
| `"text"` | Rich text / prose narrative |
| `"list"` | Bulleted checklist |
| `"table"` | Data table only (no chart) |

---

## Customising for a New Domain

To add a new domain, you only need to update the **input JSON** — no code changes required:

1. **Change `app_context.domain`** to your new domain name
2. **Update `persona.role` and `persona.instruction`** to match the new domain's context and tone
3. **Update `input_contract.structured_tables_allowed`** to list your domain's tables
4. **Update `input_contract.rag_table` and `allowed_rag_documents_only`** to your domain's knowledge base documents
5. **Update `structured_inputs.sql_scripts`** with your domain's SELECT queries
6. **Update `unstructured_inputs.similarity_search_inputs`** with your domain's search questions and embeddings (generated by upstream agent)
7. **Adjust `synthesis_instruction.focus_areas`** to match your domain's key concerns

The application code, dashboard, and LLM model remain unchanged.

---

*Last updated: May 2026 | App version: 1.0.0*
