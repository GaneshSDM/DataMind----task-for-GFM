"""
bootstrap_schema.py
-------------------
Run once (or after schema change) to generate schema_reference.json.

Reads from app DB (tracopp schema):
  - Domains + subdomains
  - Active RAG files with domain/subdomain names
  - Tables + columns from TARGET_SCHEMA (default: sales)

Output: schema_reference.json (loaded by ARIA at startup)

Usage:
    python bootstrap_schema.py
"""

import os
import json
import sys
import psycopg2
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL  = os.getenv("DATABASE_URL", "")
TARGET_SCHEMA = os.getenv("TARGET_SCHEMA", "sales")
OUTPUT_FILE   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema_reference.json")


def run():
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL not set in .env")
        sys.exit(1)

    print(f"Connecting to database…")
    try:
        conn = psycopg2.connect(DATABASE_URL)
    except Exception as e:
        print(f"ERROR: Connection failed — {e}")
        sys.exit(1)

    cur = conn.cursor()

    # ── 1. Domains ─────────────────────────────────────────────
    print("Reading domains…")
    cur.execute("""
        SELECT domain_id, domain_name
        FROM tracopp.domain
        WHERE is_active = true
        ORDER BY domain_name
    """)
    domains = [{"id": r[0], "name": r[1]} for r in cur.fetchall()]
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

    # ── 3. RAG files (active + embedded only) ─────────────────
    print("Reading RAG files…")
    cur.execute("""
        SELECT
            rf.file_id,
            rf.original_file_name,
            rf.description,
            rf.page_count,
            rf.file_type,
            d.domain_name,
            sd.sub_domain_name,
            rc.category_name,
            rsc.sub_category_name
        FROM tracopp.rag_files rf
        JOIN tracopp.domain d         ON d.domain_id       = rf.domain_id
        JOIN tracopp.sub_domain sd    ON sd.sub_domain_id  = rf.sub_domain_id
        JOIN tracopp.rag_category rc  ON rc.category_id    = rf.category_id
        LEFT JOIN tracopp.rag_sub_category rsc ON rsc.sub_category_id = rf.sub_category_id
        WHERE rf.is_active = true
          AND rf.status = 'active'
        ORDER BY d.domain_name, sd.sub_domain_name, rf.original_file_name
    """)
    rag_files = []
    for r in cur.fetchall():
        rag_files.append({
            "file_id":   str(r[0]),
            "filename":  r[1],
            "description": r[2] or "",
            "page_count": r[3],
            "file_type": r[4],
            "domain":    r[5],
            "subdomain": r[6],
            "category":  r[7],
            "sub_category": r[8] or "",
        })
    print(f"  {len(rag_files)} active RAG files")

    # ── 4. Tables + columns from TARGET_SCHEMA ─────────────────
    print(f"Introspecting schema '{TARGET_SCHEMA}'…")
    cur.execute("""
        SELECT table_name, column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = %s
        ORDER BY table_name, ordinal_position
    """, (TARGET_SCHEMA,))

    tables_dict: dict[str, list] = {}
    for row in cur.fetchall():
        tname, cname, dtype, nullable = row
        if tname not in tables_dict:
            tables_dict[tname] = []
        tables_dict[tname].append({
            "name":     cname,
            "type":     dtype,
            "nullable": nullable == "YES",
        })

    tables = [
        {"table_name": tname, "schema": TARGET_SCHEMA, "columns": cols}
        for tname, cols in sorted(tables_dict.items())
    ]
    print(f"  {len(tables)} tables in schema '{TARGET_SCHEMA}'")

    cur.close()
    conn.close()

    # ── Write output ───────────────────────────────────────────
    payload = {
        "generated_at":  datetime.now(timezone.utc).isoformat(),
        "target_schema": TARGET_SCHEMA,
        "domains":       domains,
        "subdomains":    subdomains,
        "tables":        tables,
        "rag_files":     rag_files,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)

    print(f"\nschema_reference.json written → {OUTPUT_FILE}")
    print(f"  Domains   : {len(domains)}")
    print(f"  Subdomains: {len(subdomains)}")
    print(f"  Tables    : {len(tables)}")
    print(f"  RAG files : {len(rag_files)}")
    print("\nRestart aria.py to pick up new schema.")


if __name__ == "__main__":
    run()
