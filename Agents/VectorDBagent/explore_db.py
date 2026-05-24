import psycopg2

# Supabase pooler session mode - port 5432
pooler = "aws-0-ap-southeast-1.pooler.supabase.com"
password = "Decision@2026Pondi"

configs = [
    # Session mode pooler
    {"host": pooler, "port": 5432, "user": "postgres", "desc": "pooler:5432/postgres"},
    {"host": pooler, "port": 5432, "user": "postgres.vhnksqufndudqpoxwmkd", "desc": "pooler:5432/postgres.ref"},
    # Transaction mode pooler (different user format)
    {"host": pooler, "port": 6543, "user": "postgres.vhnksqufndudqpoxwmkd", "desc": "pooler:6543/postgres.ref"},
    {"host": pooler, "port": 6543, "user": "postgres", "desc": "pooler:6543/postgres"},
]

for cfg in configs:
    print(f"\n--- Trying {cfg['desc']} ---")
    try:
        conn = psycopg2.connect(
            host=cfg["host"], port=cfg["port"], user=cfg["user"],
            password=password, dbname="postgres", connect_timeout=8
        )
        print("CONNECTED!")

        cur = conn.cursor()
        cur.execute("SELECT table_name, column_name, data_type, is_nullable FROM information_schema.columns WHERE table_schema = 'tracopp' ORDER BY table_name, ordinal_position")
        rows = cur.fetchall()
        cur_table = None
        for t, c, d, n in rows:
            if t != cur_table:
                if cur_table: print()
                cur_table = t
                print(f"\n[{t}]")
            print(f"  {c} | {d} | null={n}")

        for tbl in ['rag_files', 'rag_category', 'rag_sub_category', 'rag_document_chunks']:
            cur.execute(f"SELECT count(*) FROM tracopp.{tbl}")
            print(f"\n{tbl}: {cur.fetchone()[0]} rows")

        for tbl in ['rag_files', 'rag_category', 'rag_sub_category', 'rag_document_chunks']:
            cur.execute(f"SELECT * FROM tracopp.{tbl} ORDER BY 1 ASC LIMIT 1")
            cols = [d[0] for d in cur.description]
            row = cur.fetchone()
            print(f"\n{tbl} cols: {cols}")
            if row:
                for c, v in zip(cols, row):
                    sv = str(v)
                    if len(sv) > 200: sv = sv[:200] + "..."
                    print(f"  {c}: {sv}")

        cur.close(); conn.close()
        print("\n✓ DONE with", cfg['desc'])
        break
    except Exception as e:
        msg = str(e)
        if len(msg) > 200: msg = msg[:200]
        print(f"FAILED: {msg}")
