"""
bootstrap_schema.py
-------------------
Generate schema_reference.json from live DB.

Reads from tracopp schema:
  - Domains + their db_schema (PG schema backing each domain)
  - Subdomains
  - Active RAG files
  - Tables/views in each domain's db_schema

Multi-domain: each domain row has a db_schema column pointing to its PG schema.
The script introspects all objects (views + base tables) in each domain's schema
and tags each table with domain_id + domain_name for downstream filtering.

Fallback: if no domains have db_schema set, falls back to TARGET_SCHEMA env var
(backward compatibility with single-schema setup).

Output: schema_reference.json (read by ARIA at startup, shared with SAGE)

Usage:
    python bootstrap_schema.py
"""

import os
import json
import sys
import psycopg2
from datetime import datetime, timezone
from dotenv import load_dotenv

_BACKEND_ENV = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../backend/.env")
)
load_dotenv(dotenv_path=_BACKEND_ENV)

DATABASE_URL  = os.getenv("DATABASE_URL", "")
TARGET_SCHEMA = os.getenv("TARGET_SCHEMA", "sales")   # fallback only
OUTPUT_FILE   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema_reference.json")


def _introspect_schema(cur, schema_name: str, domain_name: str, domain_id: int) -> list:
    """
    Return list of table dicts for all objects in `schema_name`.
    Each entry tagged with domain_name + domain_id.
    Includes both VIEWs and BASE TABLEs — DBA controls what lives in each schema.
    """
    cur.execute("""
        SELECT
            c.table_name,
            c.column_name,
            c.data_type,
            c.is_nullable,
            COALESCE(t.table_type, 'BASE TABLE') AS table_type
        FROM information_schema.columns c
        LEFT JOIN information_schema.tables t
            ON  t.table_schema = c.table_schema
            AND t.table_name   = c.table_name
        WHERE c.table_schema = %s
        ORDER BY c.table_name, c.ordinal_position
    """, (schema_name,))

    tables_dict: dict[str, dict] = {}
    for row in cur.fetchall():
        tname, cname, dtype, nullable, ttype = row
        if tname not in tables_dict:
            tables_dict[tname] = {
                "table_name":  tname,
                "schema":      schema_name,
                "domain":      domain_name,
                "domain_id":   domain_id,
                "object_type": ttype,
                "columns":     [],
            }
        tables_dict[tname]["columns"].append({
            "name":     cname,
            "type":     dtype,
            "nullable": nullable == "YES",
        })

    return list(tables_dict.values())


def _introspect_fallback(cur, schema_name: str) -> list:
    """Legacy single-schema introspection (no domain tagging)."""
    cur.execute("""
        SELECT table_name, column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = %s
        ORDER BY table_name, ordinal_position
    """, (schema_name,))

    tables_dict: dict[str, list] = {}
    for row in cur.fetchall():
        tname, cname, dtype, nullable = row
        if tname not in tables_dict:
            tables_dict[tname] = []
        tables_dict[tname].append({"name": cname, "type": dtype, "nullable": nullable == "YES"})

    return [
        {"table_name": tname, "schema": schema_name, "columns": cols}
        for tname, cols in sorted(tables_dict.items())
    ]


def run():
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL not set in .env")
        sys.exit(1)

    print("Connecting to database…")
    try:
        conn = psycopg2.connect(DATABASE_URL)
    except Exception as e:
        print(f"ERROR: Connection failed — {e}")
        sys.exit(1)

    cur = conn.cursor()

    # ── 1. Domains (with db_schema) ────────────────────────────
    print("Reading domains…")
    try:
        cur.execute("""
            SELECT domain_id, domain_name, db_schema
            FROM tracopp.domain
            WHERE is_active = true
            ORDER BY domain_name
        """)
        domains = [{"id": r[0], "name": r[1], "db_schema": r[2]} for r in cur.fetchall()]
    except Exception as e:
        # db_schema column may not exist yet — fall back to name-only
        print(f"  WARNING: Could not read db_schema column ({e}) — column may need migration")
        conn.rollback()
        cur.execute("""
            SELECT domain_id, domain_name
            FROM tracopp.domain
            WHERE is_active = true
            ORDER BY domain_name
        """)
        domains = [{"id": r[0], "name": r[1], "db_schema": None} for r in cur.fetchall()]

    print(f"  {len(domains)} domains")

    # ── 2. Subdomains ──────────────────────────────────────────
    print("Reading subdomains…")
    cur.execute("""
        SELECT sub_domain_id, sub_domain_name, domain_id
        FROM tracopp.sub_domain
        WHERE is_active = true
        ORDER BY sub_domain_name
    """)
    subdomains = [{"id": r[0], "name": r[1], "domain_id": r[2]} for r in cur.fetchall()]
    print(f"  {len(subdomains)} subdomains")

    # ── 3. RAG files ───────────────────────────────────────────
    print("Reading RAG files…")
    cur.execute("""
        SELECT
            rf.file_id, rf.original_file_name, rf.description,
            rf.page_count, rf.file_type,
            d.domain_name, sd.sub_domain_name,
            rc.category_name, rsc.sub_category_name
        FROM tracopp.rag_files rf
        JOIN tracopp.domain d          ON d.domain_id       = rf.domain_id
        JOIN tracopp.sub_domain sd     ON sd.sub_domain_id  = rf.sub_domain_id
        JOIN tracopp.rag_category rc   ON rc.category_id    = rf.category_id
        LEFT JOIN tracopp.rag_sub_category rsc ON rsc.sub_category_id = rf.sub_category_id
        WHERE rf.is_active = true
          AND rf.status = 'active'
        ORDER BY d.domain_name, sd.sub_domain_name, rf.original_file_name
    """)
    rag_files = [
        {
            "file_id":      str(r[0]),
            "filename":     r[1],
            "description":  r[2] or "",
            "page_count":   r[3],
            "file_type":    r[4],
            "domain":       r[5],
            "subdomain":    r[6],
            "category":     r[7],
            "sub_category": r[8] or "",
        }
        for r in cur.fetchall()
    ]
    print(f"  {len(rag_files)} active RAG files")

    # ── 4. Tables/views per domain ─────────────────────────────
    print("Introspecting domain schemas…")
    all_tables: list[dict] = []
    domains_with_schema = [d for d in domains if d.get("db_schema")]

    if domains_with_schema:
        for domain in domains_with_schema:
            schema_name = domain["db_schema"]
            rows = _introspect_schema(cur, schema_name, domain["name"], domain["id"])
            print(f"  '{domain['name']}' → schema '{schema_name}': {len(rows)} object(s)")
            all_tables.extend(rows)
        print(f"  {len(all_tables)} total objects across {len(domains_with_schema)} domain(s)")
    else:
        # Fallback: single TARGET_SCHEMA (legacy / initial setup)
        print(f"  No domains have db_schema set — falling back to TARGET_SCHEMA='{TARGET_SCHEMA}'")
        all_tables = _introspect_fallback(cur, TARGET_SCHEMA)
        print(f"  {len(all_tables)} tables in fallback schema '{TARGET_SCHEMA}'")

    cur.close()
    conn.close()

    # ── Write output ───────────────────────────────────────────
    payload = {
        "generated_at":  datetime.now(timezone.utc).isoformat(),
        "target_schema": TARGET_SCHEMA,         # kept for SAGE backward compat
        "domains":       domains,
        "subdomains":    subdomains,
        "tables":        all_tables,
        "rag_files":     rag_files,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)

    print(f"\nschema_reference.json → {OUTPUT_FILE}")
    print(f"  Domains   : {len(domains)} ({len(domains_with_schema)} with db_schema)")
    print(f"  Subdomains: {len(subdomains)}")
    print(f"  Tables    : {len(all_tables)}")
    print(f"  RAG files : {len(rag_files)}")
    if domains_with_schema:
        print("\nARIA will auto-reload. Run: POST http://localhost:8002/schema/reload to force.")
    else:
        print("\nSet db_schema on domain rows to enable per-domain schema introspection.")


if __name__ == "__main__":
    run()
