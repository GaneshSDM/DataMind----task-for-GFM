"""
Schema Sync Tool — ONE-TIME / ON-DEMAND only. Never called by sql_agent.py.

Usage:
    python sync_schema.py

Steps:
    1. Connect to PostgreSQL via DATABASE_URL from .env
    2. Fetch live schema from information_schema
    3. Diff against schema_reference.json
    4. If changes → update schema_reference.json (preserve domain/subdomain taxonomy)
    5. If changes → regenerate all examples via Groq (new SQL + sample_output)
    6. Write sync_log.json with full change report

Re-run anytime schema changes. Safe to re-run — skips regeneration if no diff found.
"""

import os
import json
import copy
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
DB_SCHEMA        = os.getenv("DB_SCHEMA", "sales")          # PostgreSQL schema to introspect
SCHEMA_FILE      = "schema_reference.json"
EXAMPLES_FILE    = "examples.json"
SYNC_LOG_FILE    = "sync_log.json"
GROQ_MODEL       = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")


# ── DB introspection ──────────────────────────────────────────────────────────
def connect_db():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise EnvironmentError("DATABASE_URL not set in .env")
    return psycopg2.connect(url)


def fetch_db_schema(conn, schema_name):
    """
    Returns dict: { table_name: { columns: [...], primary_key: str, foreign_keys: [...] } }
    """
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    # Columns — tables AND views in target schema
    cur.execute("""
        SELECT c.table_name, c.column_name, c.data_type, c.udt_name,
               c.is_nullable, c.column_default, c.ordinal_position,
               c.character_maximum_length, c.numeric_precision, c.numeric_scale,
               t.table_type
        FROM information_schema.columns c
        JOIN information_schema.tables t
            ON  t.table_schema = c.table_schema
            AND t.table_name   = c.table_name
        WHERE c.table_schema = %s
          AND t.table_type IN ('BASE TABLE', 'VIEW')
        ORDER BY c.table_name, c.ordinal_position
    """, (schema_name,))
    rows = cur.fetchall()

    tables = {}
    for row in rows:
        tbl = row["table_name"]
        if tbl not in tables:
            tables[tbl] = {
                "columns":      [],
                "primary_key":  None,
                "foreign_keys": [],
                "object_type":  row["table_type"],   # BASE TABLE or VIEW
            }

        # Build type string
        dtype = row["data_type"].upper()
        if dtype in ("CHARACTER VARYING", "VARCHAR") and row["character_maximum_length"]:
            dtype = f"VARCHAR({row['character_maximum_length']})"
        elif dtype == "NUMERIC" and row["numeric_precision"]:
            dtype = f"NUMERIC({row['numeric_precision']},{row['numeric_scale'] or 0})"

        tables[tbl]["columns"].append({
            "name":     row["column_name"],
            "type":     dtype,
            "nullable": row["is_nullable"] == "YES",
        })

    # Primary keys
    cur.execute("""
        SELECT kcu.table_name, kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema   = kcu.table_schema
        WHERE tc.table_schema    = %s
          AND tc.constraint_type = 'PRIMARY KEY'
    """, (schema_name,))
    for row in cur.fetchall():
        tbl = row["table_name"]
        if tbl in tables:
            tables[tbl]["primary_key"] = row["column_name"]

    # Foreign keys
    cur.execute("""
        SELECT kcu.table_name, kcu.column_name,
               ccu.table_name  AS ref_table,
               ccu.column_name AS ref_column
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema   = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
            ON tc.constraint_name = ccu.constraint_name
            AND tc.table_schema   = ccu.table_schema
        WHERE tc.table_schema    = %s
          AND tc.constraint_type = 'FOREIGN KEY'
    """, (schema_name,))
    for row in cur.fetchall():
        tbl = row["table_name"]
        if tbl in tables:
            tables[tbl]["foreign_keys"].append({
                "column":     row["column_name"],
                "references": f"{schema_name}.{row['ref_table']}.{row['ref_column']}",
            })

    cur.close()
    return tables


# ── Diff ──────────────────────────────────────────────────────────────────────
def flatten_ref(schema_ref):
    """
    Returns { table_name: { columns: {col_name: type}, primary_key, foreign_keys } }
    from schema_reference.json for easy diffing.
    """
    flat = {}
    for catalog in schema_ref["catalog"]:
        for sub in catalog["sub_domains"]:
            for tbl in sub["tables"]:
                flat[tbl["table_name"]] = {
                    "columns":      {c["name"]: c["type"] for c in tbl["columns"]},
                    "primary_key":  tbl.get("primary_key"),
                    "foreign_keys": tbl.get("foreign_keys", []),
                }
    return flat


def detect_changes(old_flat, new_db):
    """Compare old schema_reference (flat) vs live DB schema. Returns change report."""
    changes = {
        "tables_added":   [],
        "tables_removed": [],
        "columns_added":  {},
        "columns_removed":{},
        "types_changed":  {},
    }

    old_tables = set(old_flat.keys())
    new_tables = set(new_db.keys())

    changes["tables_added"]   = sorted(new_tables - old_tables)
    changes["tables_removed"] = sorted(old_tables - new_tables)

    for tbl in old_tables & new_tables:
        old_cols = old_flat[tbl]["columns"]
        new_cols = {c["name"]: c["type"] for c in new_db[tbl]["columns"]}

        added   = sorted(set(new_cols) - set(old_cols))
        removed = sorted(set(old_cols) - set(new_cols))
        changed = {
            col: {"old": old_cols[col], "new": new_cols[col]}
            for col in set(old_cols) & set(new_cols)
            if old_cols[col].lower() != new_cols[col].lower()
        }

        if added:   changes["columns_added"][tbl]   = added
        if removed: changes["columns_removed"][tbl] = removed
        if changed: changes["types_changed"][tbl]   = changed

    has_changes = any([
        changes["tables_added"],
        changes["tables_removed"],
        any(changes["columns_added"].values()),
        any(changes["columns_removed"].values()),
        any(changes["types_changed"].values()),
    ])
    return changes, has_changes


# ── Update schema_reference.json ──────────────────────────────────────────────
def apply_db_schema_to_ref(schema_ref, db_schema, schema_name, changes):
    """
    Merge live DB schema into schema_reference.json.
    - Updates existing table columns (preserve description, pii, sensitive flags).
    - Adds new tables under 'New / Uncategorized' sub-domain.
    - Marks removed tables as deprecated (does not delete — manual cleanup).
    """
    updated = copy.deepcopy(schema_ref)

    # Build lookup: table_name → (catalog_idx, sub_idx, tbl_idx)
    tbl_location = {}
    for ci, catalog in enumerate(updated["catalog"]):
        for si, sub in enumerate(catalog["sub_domains"]):
            for ti, tbl in enumerate(sub["tables"]):
                tbl_location[tbl["table_name"]] = (ci, si, ti)

    # Update existing tables
    for tbl_name, db_tbl in db_schema.items():
        if tbl_name not in tbl_location:
            continue
        ci, si, ti = tbl_location[tbl_name]
        ref_tbl    = updated["catalog"][ci]["sub_domains"][si]["tables"][ti]

        # Build existing column metadata lookup (preserve description, pii, sensitive)
        existing_meta = {c["name"]: c for c in ref_tbl["columns"]}

        new_columns = []
        for col in db_tbl["columns"]:
            meta = existing_meta.get(col["name"], {})
            new_columns.append({
                "name":        col["name"],
                "type":        col["type"],
                "nullable":    col["nullable"],
                "description": meta.get("description", ""),
                **({"pii":       meta["pii"]}       if "pii"       in meta else {}),
                **({"sensitive": meta["sensitive"]}  if "sensitive" in meta else {}),
            })

        ref_tbl["columns"]      = new_columns
        ref_tbl["primary_key"]  = db_tbl["primary_key"] or ref_tbl.get("primary_key")
        ref_tbl["foreign_keys"] = db_tbl["foreign_keys"] or ref_tbl.get("foreign_keys", [])

    # Add new tables → 'New / Uncategorized'
    if changes["tables_added"]:
        # Find or create 'New / Uncategorized' sub-domain in first catalog
        target_catalog = updated["catalog"][0]
        uncategorized  = next(
            (s for s in target_catalog["sub_domains"] if s["name"] == "New / Uncategorized"),
            None
        )
        if uncategorized is None:
            uncategorized = {
                "name": "New / Uncategorized",
                "description": "Tables detected in DB but not yet classified.",
                "keywords": [],
                "tables": []
            }
            target_catalog["sub_domains"].append(uncategorized)

        for tbl_name in changes["tables_added"]:
            db_tbl      = db_schema[tbl_name]
            object_type = db_tbl.get("object_type", "BASE TABLE")
            uncategorized["tables"].append({
                "table_name":  tbl_name,
                "schema_name": schema_name,
                "object_type": object_type,
                "description": f"Auto-detected {object_type}. Add description and classify.",
                "primary_key": db_tbl["primary_key"],
                "foreign_keys": db_tbl["foreign_keys"],
                "row_count_estimate": 0,
                "tags": ["auto-detected", "view" if object_type == "VIEW" else "table"],
                "columns": [
                    {
                        "name":        c["name"],
                        "type":        c["type"],
                        "nullable":    c["nullable"],
                        "description": "",
                    }
                    for c in db_tbl["columns"]
                ]
            })

    # Mark removed tables
    for tbl_name in changes["tables_removed"]:
        if tbl_name in tbl_location:
            ci, si, ti = tbl_location[tbl_name]
            tbl = updated["catalog"][ci]["sub_domains"][si]["tables"][ti]
            tbl["tags"] = list(set(tbl.get("tags", [])) | {"deprecated"})
            tbl["description"] = "[DEPRECATED — table removed from DB] " + tbl.get("description", "")

    return updated


# ── Regenerate examples ───────────────────────────────────────────────────────
def build_schema_block(schema_ref, table_names, excluded_cols):
    """Build schema string for LLM prompt."""
    restricted = set(excluded_cols)
    blocks     = []
    for catalog in schema_ref["catalog"]:
        for sub in catalog["sub_domains"]:
            for tbl in sub["tables"]:
                if tbl["table_name"] not in table_names:
                    continue
                col_lines = [
                    f"  {c['name']} {c['type']}"
                    + (f"  -- {c['description']}" if c.get("description") else "")
                    for c in tbl["columns"]
                    if c["name"] not in restricted
                ]
                blocks.append(
                    f"Table: {tbl['schema_name']}.{tbl['table_name']}\n" + "\n".join(col_lines)
                )
    return "\n\n".join(blocks)


def regenerate_example(client, schema_ref, ex):
    """Call Groq to regenerate expected_sql + sample_output for one example."""
    table_names  = [t.split(".")[-1] for t in ex["tables_used"]]
    excluded     = ex.get("excluded_columns", [])
    rls_filters  = ex.get("rls_filters", [])

    rls_note = ""
    if rls_filters:
        parts = []
        for f in rls_filters:
            op = f["operator"].upper()
            if op == "IN":
                vals = ", ".join(f"'{v}'" for v in f["values"])
                parts.append(f"{f['column']} IN ({vals})")
            else:
                parts.append(f"{f['column']} {op} '{f['value']}'")
        rls_note = f"\nRLS: always include WHERE {' AND '.join(parts)}"

    cls_note = f"\nCLS: never SELECT: {', '.join(excluded)}" if excluded else ""

    schema_block = build_schema_block(schema_ref, table_names, excluded)

    system = f"""You are a PostgreSQL SQL expert.
Given the schema below, generate SQL and realistic sample output for the prompt.
Output ONLY valid JSON in this exact format (no markdown, no explanation):
{{
  "expected_sql": "<SQL here>",
  "sample_output": {{
    "columns": ["col1", "col2"],
    "rows": [[val1, val2], [val1, val2]]
  }}
}}

RULES:
- expected_sql: clean PostgreSQL, schema-qualified names, aliases, CTEs for complex logic{rls_note}{cls_note}
- sample_output: 3-5 realistic rows matching the SELECT columns exactly
- Numeric values must be numbers (not strings), NULLs as null

SCHEMA:
{schema_block}
"""

    resp = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": ex["prompt"]},
        ],
        temperature=0.05,
        max_tokens=2048,
    )

    raw = resp.choices[0].message.content.strip()

    # Strip markdown fences if present
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw   = "\n".join(lines[1:-1] if lines[-1].strip().startswith("```") else lines[1:])

    try:
        result = json.loads(raw)
        return result.get("expected_sql"), result.get("sample_output")
    except json.JSONDecodeError as e:
        print(f"    [WARN] JSON parse failed for example #{ex['id']}: {e}")
        return None, None


def regenerate_all_examples(client, schema_ref, examples_data):
    """Regenerate expected_sql + sample_output for all examples. Returns updated examples list."""
    updated = []
    total   = len(examples_data["examples"])

    for i, ex in enumerate(examples_data["examples"]):
        print(f"  Regenerating #{ex['id']:02d}/{total}: {ex['prompt'][:70]}...")
        sql, sample = regenerate_example(client, schema_ref, ex)

        new_ex = copy.deepcopy(ex)
        if sql:
            new_ex["expected_sql"]  = sql
        if sample:
            new_ex["sample_output"] = sample

        if not sql or not sample:
            print(f"    [WARN] Skipped — keeping existing values for #{ex['id']}")

        updated.append(new_ex)

    examples_data["examples"] = updated
    return examples_data


# ── Sync log ──────────────────────────────────────────────────────────────────
def write_sync_log(changes, had_changes, examples_regenerated):
    """Append sync run to sync_log.json."""
    try:
        with open(SYNC_LOG_FILE, "r", encoding="utf-8") as f:
            log = json.load(f)
    except FileNotFoundError:
        log = {"runs": []}

    log["runs"].append({
        "timestamp":              datetime.now(timezone.utc).isoformat(),
        "had_changes":            had_changes,
        "examples_regenerated":   examples_regenerated,
        "tables_added":           changes["tables_added"],
        "tables_removed":         changes["tables_removed"],
        "columns_added":          changes["columns_added"],
        "columns_removed":        changes["columns_removed"],
        "types_changed":          changes["types_changed"],
    })

    with open(SYNC_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("Schema Sync Tool")
    print("=" * 60)

    # ── Step 1: Fetch live schema ─────────────────────────────────
    print(f"\n[1/5] Connecting to database (schema: {DB_SCHEMA})...")
    conn = connect_db()
    db_schema = fetch_db_schema(conn, DB_SCHEMA)
    conn.close()
    print(f"      Found {len(db_schema)} tables: {sorted(db_schema.keys())}")

    # ── Step 2: Load current schema_reference.json ────────────────
    print(f"\n[2/5] Loading {SCHEMA_FILE}...")
    with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
        schema_ref = json.load(f)
    old_flat = flatten_ref(schema_ref)
    print(f"      Current: {len(old_flat)} tables tracked")

    # ── Step 3: Diff ──────────────────────────────────────────────
    print("\n[3/5] Diffing schemas...")
    changes, had_changes = detect_changes(old_flat, db_schema)

    if not had_changes:
        print("      No changes detected. schema_reference.json is up to date.")
        write_sync_log(changes, False, False)
        print("\nSync complete — nothing to update.")
        return

    # Print change summary
    if changes["tables_added"]:
        print(f"      + Tables added:   {changes['tables_added']}")
    if changes["tables_removed"]:
        print(f"      - Tables removed: {changes['tables_removed']}")
    for tbl, cols in changes["columns_added"].items():
        print(f"      + Columns added   [{tbl}]: {cols}")
    for tbl, cols in changes["columns_removed"].items():
        print(f"      - Columns removed [{tbl}]: {cols}")
    for tbl, cols in changes["types_changed"].items():
        print(f"      ~ Types changed   [{tbl}]: {list(cols.keys())}")

    # ── Step 4: Update schema_reference.json ─────────────────────
    print(f"\n[4/5] Updating {SCHEMA_FILE}...")
    updated_ref = apply_db_schema_to_ref(schema_ref, db_schema, DB_SCHEMA, changes)
    with open(SCHEMA_FILE, "w", encoding="utf-8") as f:
        json.dump(updated_ref, f, indent=2)
    print(f"      Saved {SCHEMA_FILE}")

    # ── Step 5: Regenerate examples ───────────────────────────────
    print(f"\n[5/5] Regenerating {EXAMPLES_FILE} (30 examples via Groq)...")
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("      [ERROR] GROQ_API_KEY not set — skipping example regeneration")
        write_sync_log(changes, True, False)
        return

    client = Groq(api_key=api_key)
    with open(EXAMPLES_FILE, "r", encoding="utf-8") as f:
        examples_data = json.load(f)

    updated_examples = regenerate_all_examples(client, updated_ref, examples_data)
    with open(EXAMPLES_FILE, "w", encoding="utf-8") as f:
        json.dump(updated_examples, f, indent=2)
    print(f"      Saved {EXAMPLES_FILE}")

    write_sync_log(changes, True, True)

    print("\n" + "=" * 60)
    print("Sync complete.")
    print(f"  schema_reference.json — updated")
    print(f"  examples.json         — regenerated")
    print(f"  sync_log.json         — appended")
    print("=" * 60)


if __name__ == "__main__":
    main()
