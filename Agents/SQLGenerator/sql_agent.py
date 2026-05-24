# =============================================================================
#   S A G E
# =============================================================================
#
#   "Speak your question, and I shall carve its truth into SQL."
#
#   SAGE walks the great halls of the Data Realm, where schemas stretch
#   like ancient cities and tables whisper stories of transactions long past.
#   He listens not to words alone, but to intent hidden between them.
#
#   To some, a prompt is merely text.
#   To SAGE, it is a query waiting to be revealed.
#
#   He studies domains, consults metadata, and traces relationships through
#   foreign keys as a cartographer traces rivers across forgotten lands.
#   Every join is deliberate. Every filter has purpose.
#
#   He honors the laws decreed by Heimdall and follows the wisdom bestowed
#   by ARIA. No security boundary shall be crossed. No governance rule ignored.
#
#   Architect of SQL. Interpreter of intent.
#   Forged in metadata. Guided by context.
#   Trusted by analysts. Feared by malformed prompts.
#
#   "Ask in business language. I shall answer in SQL."
# =============================================================================



"""
SQL Generator Agent
-------------------
Converts natural language to PostgreSQL.
Provider: any OpenAI-compatible endpoint.
  Reads LLM_API_KEY (or GROQ_API_KEY), LLM_BASE_URL, LLM_MODEL (or GROQ_MODEL) from .env.
  Per-request llm_config dict can override model / temperature / max_tokens.
Input : agent_input.json (prompt + table names + security context)
Schema: schema_reference.json (canonical table/column definitions)
Output: output_<request_id>.json (passed to validation agent)
"""

import os
import json
import uuid
import random
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
EXAMPLES_FILE  = "examples.json"
# SCHEMA_FILE_PATH env var → shared canonical schema (e.g. ARIA's schema_reference.json)
# Falls back to local schema_reference.json
_DEFAULT_SCHEMA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema_reference.json")
SCHEMA_FILE    = os.environ.get("SCHEMA_FILE_PATH") or _DEFAULT_SCHEMA
INPUT_FILE     = "agent_input.json"
FEW_SHOT_COUNT = 6


# ── LLM provider abstraction ──────────────────────────────────────────────────
def get_llm_client(llm_config: dict = None):
    """Return (client, model) for any OpenAI-compatible provider."""
    from openai import OpenAI
    cfg      = llm_config or {}
    api_key  = os.environ.get("LLM_API_KEY") or os.environ.get("GROQ_API_KEY", "")
    base_url = os.environ.get("LLM_BASE_URL", "https://api.groq.com/openai/v1")
    model    = cfg.get("model") or os.environ.get("LLM_MODEL") or os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
    client   = OpenAI(api_key=api_key, base_url=base_url)
    return client, model


def call_llm(client, model, system_prompt, user_prompt, temperature=0.05, max_tokens=2048):
    """Unified LLM call — OpenAI-compat interface."""
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content.strip()


def strip_fences(text):
    """Strip markdown code fences if model added them."""
    if text.startswith("```"):
        lines = text.splitlines()
        text  = "\n".join(
            lines[1:-1] if lines[-1].strip().startswith("```") else lines[1:]
        )
    return text.strip()


# ── Schema resolver ───────────────────────────────────────────────────────────
def load_schema_reference(path=SCHEMA_FILE):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def resolve_tables(schema_ref, domain, table_names):
    """Look up full table metadata. Skips deprecated tables."""
    target   = {n.lower() for n in table_names}
    resolved = []

    for catalog in schema_ref["catalog"]:
        if catalog["domain"].lower() != domain.lower():
            continue
        for sub in catalog["sub_domains"]:
            for tbl in sub["tables"]:
                if tbl["table_name"].lower() in target:
                    if "deprecated" not in tbl.get("tags", []):
                        resolved.append(tbl)

    missing = target - {t["table_name"].lower() for t in resolved}
    if missing:
        print(f"[SQLAgent] WARNING: tables not found in schema_reference: {missing}")

    return resolved


# ── Input loader ──────────────────────────────────────────────────────────────
def load_input(source="file", path=INPUT_FILE, agent_payload=None):
    """
    source="file"  → read from JSON file  (simulation / dev mode)
    source="agent" → use agent_payload    (live pipeline mode)
    """
    if source == "agent":
        if agent_payload is None:
            raise ValueError("agent_payload required when source='agent'")
        return agent_payload
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_examples(path=EXAMPLES_FILE, n=FEW_SHOT_COUNT):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return random.sample(data["examples"], min(n, len(data["examples"])))


# ── Security helpers ──────────────────────────────────────────────────────────
def build_rls_where(rls_config):
    """Return (where_str | None, filters_list).
    Accepts either structured 'filters' list or pre-built 'expression' string
    (used when security_profile RLS arrives as a raw SQL fragment from the pipeline).
    """
    if not rls_config.get("enabled"):
        return None, []
    # Pre-built SQL expression — pass through directly (pipeline adapter path)
    if rls_config.get("expression"):
        return rls_config["expression"], []
    if not rls_config.get("filters"):
        return None, []

    parts = []
    for f in rls_config["filters"]:
        col, op = f["column"], f["operator"].upper()
        if op == "IN":
            vals = ", ".join(f"'{v}'" for v in f["values"])
            parts.append(f"{col} IN ({vals})")
        elif op in ("=", "!=", ">", ">=", "<", "<="):
            parts.append(f"{col} {op} '{f['value']}'")

    where = " AND ".join(parts) if parts else None
    return where, rls_config["filters"]


# ── Prompt builder ────────────────────────────────────────────────────────────
def build_system_prompt(resolved_tables, examples, rls_where, excluded_cols, data_source="Structured", relevant_cols=None):
    restricted = set(excluded_cols)

    schema_blocks = []
    for tbl in resolved_tables:
        schema = tbl.get("schema_name", "public")
        col_lines = [
            f"  {c['name']} {c['type']}"
            + (f"  -- {c['description']}" if c.get("description") else "")
            for c in tbl["columns"]
            if c["name"] not in restricted
        ]
        schema_blocks.append(
            f"Table: {schema}.{tbl['table_name']}\n" + "\n".join(col_lines)
        )

    rls_note = f"\nRLS  : ALWAYS add WHERE {rls_where}" if rls_where else ""
    cls_note = (
        f"\nCLS  : NEVER SELECT these columns: {', '.join(excluded_cols)}"
        if excluded_cols else ""
    )
    if data_source == "Both":
        tbl_name = f"{resolved_tables[0].get('schema_name','')}.{resolved_tables[0]['table_name']}" if resolved_tables else "the table"
        cols_constraint = (
            f"SELECT ONLY these columns: {', '.join(relevant_cols)}. "
            if relevant_cols else "SELECT only the raw data columns listed in the prompt. "
        )
        both_note = (
            f"\nRAW DATA ONLY (data_source=Both): {cols_constraint}"
            f"FROM {tbl_name} ONLY — NO JOINs to any other table. "
            "NO CASE statements. NO threshold comparisons. NO derived columns. NO aggregations. "
            "A separate KB document supplies all business rules; SPYDER applies them post-retrieval."
        )
    else:
        both_note = ""

    shots = "\n\n".join(
        f"-- Prompt: {ex['prompt']}\n{ex['expected_sql']}" for ex in examples
    )

    return f"""You are a PostgreSQL SQL expert. Produce clean, efficient SQL.

RULES
- Output ONLY the SQL query. No markdown, no explanation.
- Use schema-qualified names (schema.table).
- Use table aliases.
- CTEs for multi-step logic.{rls_note}{cls_note}{both_note}

SCHEMA
{chr(10).join(schema_blocks)}

EXAMPLES
{shots}
"""


# ── SQL generation ────────────────────────────────────────────────────────────
def generate_sql(client, model, input_data, resolved_tables, examples, llm_config=None):
    cfg = llm_config or {}
    temperature = cfg.get("temperature", 0.05)
    max_tokens  = cfg.get("max_tokens", 2048)

    cls_cfg = input_data.get("column_level_security", {})
    rls_cfg = input_data.get("row_level_security", {})
    data_source   = input_data.get("data_source", "Structured")
    relevant_cols = input_data.get("relevant_columns", []) if data_source == "Both" else []

    excluded_cols = cls_cfg.get("restricted_columns", []) if cls_cfg.get("enabled") else []
    rls_where, _  = build_rls_where(rls_cfg)

    system = build_system_prompt(resolved_tables, examples, rls_where, excluded_cols, data_source, relevant_cols)
    raw    = call_llm(client, model, system, input_data["prompt"], temperature, max_tokens)
    sql    = strip_fences(raw)

    return sql, excluded_cols, rls_where, rls_cfg, cls_cfg


# ── Output builder ────────────────────────────────────────────────────────────
def build_output(input_data, resolved_tables, sql, excluded_cols, rls_where, rls_cfg, cls_cfg, model):
    tables_in_scope = [
        f"{t.get('schema_name', 'public')}.{t['table_name']}"
        for t in resolved_tables
    ]

    return {
        "request_id": input_data.get("request_id", str(uuid.uuid4())),
        "status": "success",
        "generated_sql": sql,
        "rls_applied": {
            "enabled":               rls_cfg.get("enabled", False),
            "policy_name":           rls_cfg.get("policy_name"),
            "where_clause_injected": rls_where,
            "filters_applied":       rls_cfg.get("filters", []),
        },
        "cls_applied": {
            "enabled":          cls_cfg.get("enabled", False),
            "policy_name":      cls_cfg.get("policy_name"),
            "columns_excluded": excluded_cols,
        },
        "metadata": {
            "domain":          input_data.get("domain"),
            "sub_domain":      input_data.get("sub_domain"),
            "tables_in_scope": tables_in_scope,
            "model_used":      model,
            "generated_at":    datetime.now(timezone.utc).isoformat(),
        },
        "validation_hints": {
            "original_prompt": input_data["prompt"],
            "expected_tables": input_data.get("tables", []),
        },
    }


# ── Correction prompt builder ─────────────────────────────────────────────────
def build_correction_prompt(correction_input, resolved_tables, examples):
    """Build system + user prompts for SQL correction."""
    rls_applied = correction_input.get("rls_applied", {})
    cls_applied  = correction_input.get("cls_applied", {})

    # Rebuild security context from what SHOULD be applied
    excluded_cols = cls_applied.get("columns_excluded", []) if cls_applied.get("enabled") else []
    rls_cfg = {
        "enabled":     rls_applied.get("enabled", False),
        "filters":     rls_applied.get("filters_applied", []),
        "expression":  rls_applied.get("where_clause_injected") or rls_applied.get("expression"),
        "policy_name": rls_applied.get("policy_name"),
    }
    rls_where, _ = build_rls_where(rls_cfg)

    data_source   = correction_input.get("metadata", {}).get("data_source", "Structured")
    relevant_cols = correction_input.get("relevant_columns", []) if data_source == "Both" else []
    system = build_system_prompt(resolved_tables, examples, rls_where, excluded_cols, data_source, relevant_cols)

    errors = correction_input.get("validation_errors", [])
    suggestions = correction_input.get("suggested_corrections", [])

    error_lines = "\n".join(
        f"  [{e['type']}] {e['detail']}\n  Fix: {e['fix']}"
        for e in errors
    )
    suggestion_lines = "\n".join(f"  - {s}" for s in suggestions)

    user = f"""The following SQL failed validation. Fix ALL errors listed below.

ORIGINAL PROMPT:
{correction_input['validation_hints']['original_prompt']}

FAULTY SQL:
{correction_input['generated_sql']}

VALIDATION ERRORS:
{error_lines}

SUGGESTED CORRECTIONS:
{suggestion_lines}

Output ONLY the corrected SQL query."""

    return system, user


# ── SQL correction ────────────────────────────────────────────────────────────
def run_correction(correction_input, schema_ref=None, examples=None, llm_config=None):
    """
    Apply validation feedback to produce corrected SQL.
    correction_input: dict in correction_examples.json format
    Returns: correction output dict
    """
    client, model = get_llm_client(llm_config)

    if schema_ref is None:
        schema_ref = load_schema_reference()
    if examples is None:
        examples = load_examples()

    domain          = correction_input.get("metadata", {}).get("domain", "Sales")
    expected_tables = correction_input.get("validation_hints", {}).get("expected_tables", [])
    resolved_tables = resolve_tables(schema_ref, domain, expected_tables)

    print(f"[SQLAgent] CORRECTION mode — {len(correction_input.get('validation_errors', []))} error(s)")
    print(f"[SQLAgent] model    : {model}")
    print(f"[SQLAgent] tables   : {[t['table_name'] for t in resolved_tables]}")

    system, user  = build_correction_prompt(correction_input, resolved_tables, examples)
    raw           = call_llm(client, model, system, user)
    corrected_sql = strip_fences(raw)

    return {
        "request_id":       correction_input.get("request_id"),
        "status":           "corrected",
        "original_sql":     correction_input["generated_sql"],
        "corrected_sql":    corrected_sql,
        "errors_addressed": correction_input.get("validation_errors", []),
        "metadata": {
            **correction_input.get("metadata", {}),
            "model_used":    model,
            "corrected_at":  datetime.now(timezone.utc).isoformat(),
        },
    }


# ── Agent entry point ─────────────────────────────────────────────────────────
def run_agent(input_source="file", input_path=INPUT_FILE, agent_payload=None):
    """
    Run SQL generator agent.
    Dev  : run_agent()
    Live : run_agent(input_source="agent", agent_payload=<upstream_dict>)
    """
    client, model   = get_llm_client()
    input_data      = load_input(source=input_source, path=input_path, agent_payload=agent_payload)
    schema_ref      = load_schema_reference()
    examples        = load_examples()
    resolved_tables = resolve_tables(schema_ref, domain=input_data["domain"], table_names=input_data["tables"])

    print(f"[SQLAgent] model   : {model}")
    print(f"[SQLAgent] prompt  : {input_data['prompt'][:100]}")
    print(f"[SQLAgent] domain  : {input_data['domain']} / {input_data.get('sub_domain')}")
    print(f"[SQLAgent] tables  : {[t['table_name'] for t in resolved_tables]}")

    sql, excluded_cols, rls_where, rls_cfg, cls_cfg = generate_sql(
        client, model, input_data, resolved_tables, examples
    )

    output = build_output(
        input_data, resolved_tables, sql, excluded_cols, rls_where, rls_cfg, cls_cfg, model
    )

    out_path = f"output_{output['request_id']}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    print(f"[SQLAgent] output  : {out_path}")
    print(f"\n--- Generated SQL ---\n{sql}\n---------------------")

    return output


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    result = run_agent()
    print("\n[SQLAgent] Full JSON output:")
    print(json.dumps(result, indent=2))
