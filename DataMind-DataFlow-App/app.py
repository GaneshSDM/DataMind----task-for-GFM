import os, csv, re, datetime
from decimal import Decimal
from pathlib import Path
from typing import List
from fastapi import FastAPI, UploadFile, File, Body, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / ".env")
DATABASE_URL = os.getenv("DATABASE_URL")
SCHEMA = os.getenv("TARGET_SCHEMA", "dataflow_demo")
UPLOADS = BASE / "uploads"; UPLOADS.mkdir(exist_ok=True)
SAMPLES = BASE / "sample_data"
PII = {"first_name","last_name","full_name","name","email","phone","mobile","ssn","dob","date_of_birth","address"}

app = FastAPI(title="DataMind DataFlow")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

def conn():
    if not DATABASE_URL:
        raise HTTPException(500, "DATABASE_URL not set in .env")
    c = psycopg2.connect(DATABASE_URL, connect_timeout=15); c.autocommit = True; return c

def project_ref():
    m = re.search(r"postgres\.([a-z0-9]+)", DATABASE_URL or ""); return m.group(1) if m else "?"

def is_int(v):   return bool(re.fullmatch(r"-?\d+", v or ""))
def is_float(v):
    try: float(v); return True
    except: return False
def is_date(v):  return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", v or ""))

def infer_one(name, vals):
    n = name.lower()
    if vals and "date" in n and all(is_date(x) for x in vals): return "DATE"
    if vals and all(is_int(x) for x in vals):   return "BIGINT"
    if vals and all(is_float(x) for x in vals): return "DOUBLE PRECISION"
    return "TEXT"

def read_csv_file(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        r = csv.reader(f); header = next(r); rows = [row for row in r if any(c.strip() for c in row)]
    return header, rows

def profile(header, rows):
    cols = []
    for i, name in enumerate(header):
        vals = [row[i] for row in rows if i < len(row) and row[i] != ""]
        cols.append({"column": name, "type": infer_one(name, vals), "pii": name.lower() in PII})
    return cols

def find_source(table):
    for d in (UPLOADS, SAMPLES):
        p = d / f"{table}.csv"
        if p.exists(): return p
    return None

def ddl_for(table, cols):
    body = ",\n  ".join(f'{c["column"]} {c["type"]}' for c in cols)
    return f"CREATE TABLE {SCHEMA}.{table} (\n  {body}\n);"

def conv(v, t):
    if v is None or v == "": return None
    if t == "BIGINT": return int(v)
    if t == "DOUBLE PRECISION": return float(v)
    return v

def jval(v):
    if isinstance(v, Decimal): return float(v)
    if isinstance(v, (datetime.date, datetime.datetime)): return v.isoformat()
    return v

def preview(cur, table, limit=6):
    cur.execute(f"SELECT * FROM {SCHEMA}.{table} LIMIT {limit}")
    names = [d[0] for d in cur.description]
    return [{n: jval(v) for n, v in zip(names, row)} for row in cur.fetchall()]

def ensure_schema(cur): cur.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
def table_exists(cur, t):
    cur.execute("select 1 from information_schema.tables where table_schema=%s and table_name=%s", (SCHEMA, t))
    return cur.fetchone() is not None

def load_table(table):
    src = find_source(table)
    if not src: raise HTTPException(404, f"No CSV found for '{table}'. Upload {table}.csv first.")
    header, rows = read_csv_file(src)
    cols = profile(header, rows); types = [c["type"] for c in cols]
    c = conn(); cur = c.cursor(); ensure_schema(cur)
    cur.execute(f"DROP TABLE IF EXISTS {SCHEMA}.{table} CASCADE")
    cur.execute(ddl_for(table, cols))
    collist = ", ".join(x["column"] for x in cols)
    vals = [tuple(conv(row[i] if i < len(row) else "", types[i]) for i in range(len(cols))) for row in rows]
    if vals: execute_values(cur, f"INSERT INTO {SCHEMA}.{table} ({collist}) VALUES %s", vals)
    cur.execute(f"SELECT count(*) FROM {SCHEMA}.{table}"); n = cur.fetchone()[0]
    nulls = sum(1 for row in rows for i in range(len(cols)) if i >= len(row) or row[i] == "")
    prev = preview(cur, table); c.close()
    return cols, ddl_for(table, cols), n, prev, nulls

def ensure_loaded(cur, tables, steps):
    for t in tables:
        if not table_exists(cur, t):
            load_table(t); steps.append({"agent": "Ingestion", "label": f"auto-load dependency: {t}"})

def build_dim_product(cur):
    sql = (f"CREATE TABLE {SCHEMA}.dim_product AS\n"
           "SELECT p.product_id, p.product_name, p.category_id, c.category_name, p.unit_cost, p.unit_price\n"
           f"FROM {SCHEMA}.products p JOIN {SCHEMA}.categories c ON p.category_id = c.category_id")
    cur.execute(f"DROP TABLE IF EXISTS {SCHEMA}.dim_product CASCADE"); cur.execute(sql); return sql + ";"

def build_dim_customer(cur):
    sql = (f"CREATE TABLE {SCHEMA}.dim_customer AS\n"
           "SELECT customer_id, first_name, last_name,\n"
           "       CASE gender_code WHEN 1 THEN 'Male' WHEN 2 THEN 'Female' END AS gender, city, country\n"
           f"FROM {SCHEMA}.customers")
    cur.execute(f"DROP TABLE IF EXISTS {SCHEMA}.dim_customer CASCADE"); cur.execute(sql); return sql + ";"

def build_fact(cur):
    sql = (f"CREATE TABLE {SCHEMA}.fact_sales AS\n"
           "SELECT t.txn_id, t.txn_date, dc.first_name||' '||dc.last_name AS customer, dc.gender,\n"
           "       dp.product_name AS product, dp.category_name AS category,\n"
           "       t.quantity, dp.unit_price, t.quantity*dp.unit_price AS revenue\n"
           f"FROM {SCHEMA}.transactions t\n"
           f"JOIN {SCHEMA}.dim_product  dp ON t.product_id  = dp.product_id\n"
           f"JOIN {SCHEMA}.dim_customer dc ON t.customer_id = dc.customer_id")
    cur.execute(f"DROP TABLE IF EXISTS {SCHEMA}.fact_sales CASCADE"); cur.execute(sql); return sql + ";"

@app.get("/api/health")
def health():
    try:
        c = conn(); cur = c.cursor(); cur.execute("select version()"); v = cur.fetchone()[0]; c.close()
        return {"connected": True, "project": project_ref(), "schema": SCHEMA, "server": v.split(" on ")[0]}
    except Exception as e:
        return {"connected": False, "project": project_ref(), "schema": SCHEMA, "error": str(e)[:200]}

@app.get("/api/sources")
def sources():
    seen = {}
    for d, origin in ((UPLOADS, "uploaded"), (SAMPLES, "sample")):
        if d.exists():
            for p in sorted(d.glob("*.csv")):
                if p.stem in seen: continue
                header, rows = read_csv_file(p)
                seen[p.stem] = {"table": p.stem, "origin": origin, "rows": len(rows), "columns": profile(header, rows)}
    return list(seen.values())

@app.post("/api/upload")
async def upload(files: List[UploadFile] = File(...)):
    out = []
    for f in files:
        if not f.filename.lower().endswith(".csv"): continue
        p = UPLOADS / Path(f.filename).name; p.write_bytes(await f.read())
        header, rows = read_csv_file(p)
        out.append({"table": p.stem, "rows": len(rows), "columns": profile(header, rows)})
    return {"uploaded": out}

@app.get("/api/catalog")
def catalog():
    c = conn(); cur = c.cursor()
    cur.execute("select table_name from information_schema.tables where table_schema=%s order by table_name", (SCHEMA,))
    tabs = [r[0] for r in cur.fetchall()]; out = []
    for t in tabs:
        cur.execute(f"SELECT count(*) FROM {SCHEMA}.{t}"); out.append({"table": t, "rows": cur.fetchone()[0]})
    c.close(); return {"schema": SCHEMA, "tables": out}

@app.post("/api/ingest")
def ingest(payload: dict = Body(...)):
    table = payload.get("table")
    cols, ddl, n, prev, nulls = load_table(table)
    steps = [{"agent": "Discovery", "label": f"introspect & profile {table}"},
             {"agent": "Ingestion", "label": f"create + load {SCHEMA}.{table}"},
             {"agent": "Quality", "label": "row-count & null checks"}]
    return {"table": table, "steps": steps, "ddl": ddl, "profile": cols,
            "rows": n, "nulls": nulls, "preview": prev}

@app.post("/api/transform")
def transform():
    steps = []; c = conn(); cur = c.cursor(); ensure_schema(cur)
    ensure_loaded(cur, ["products", "categories", "customers"], steps)
    s1 = build_dim_product(cur); steps.append({"agent": "Transformation", "label": "join products × categories → category_name"})
    s2 = build_dim_customer(cur); steps.append({"agent": "Transformation", "label": "map gender_code → Male/Female"})
    pv1 = preview(cur, "dim_product"); pv2 = preview(cur, "dim_customer")
    steps.append({"agent": "Quality", "label": "validate mapped domains"})
    c.close()
    return {"steps": steps, "sql": [s1, s2], "previews": {"dim_product": pv1, "dim_customer": pv2}}

@app.post("/api/aggregate")
def aggregate(payload: dict = Body(default={})):
    by = "customer" if (payload or {}).get("by") == "customer" else "category"
    steps = []; c = conn(); cur = c.cursor(); ensure_schema(cur)
    ensure_loaded(cur, ["products", "categories", "customers", "transactions"], steps)
    sqls = []
    if not table_exists(cur, "dim_product"): sqls.append(build_dim_product(cur))
    if not table_exists(cur, "dim_customer"): sqls.append(build_dim_customer(cur))
    if sqls: steps.append({"agent": "Transformation", "label": "build dimensions (dependency)"})
    sf = build_fact(cur); steps.append({"agent": "Transformation", "label": "join transactions × product × customer → fact_sales"})
    sqlA = (f"CREATE TABLE {SCHEMA}.agg_sales_by_{by} AS\n"
            f"SELECT {by}, SUM(quantity) AS units, SUM(revenue) AS revenue, COUNT(*) AS txns\n"
            f"FROM {SCHEMA}.fact_sales GROUP BY {by} ORDER BY revenue DESC")
    cur.execute(f"DROP TABLE IF EXISTS {SCHEMA}.agg_sales_by_{by} CASCADE"); cur.execute(sqlA)
    steps.append({"agent": "Transformation", "label": f"aggregate revenue by {by}"})
    rows = preview(cur, f"agg_sales_by_{by}", 50)
    cur.execute(f"SELECT COALESCE(SUM(revenue),0), COALESCE(SUM(quantity),0), COUNT(*) FROM {SCHEMA}.fact_sales")
    tot, units, txns = cur.fetchone()
    steps.append({"agent": "Publish", "label": "materialize table + register lineage"})
    c.close()
    return {"by": by, "steps": steps, "sql": sqls + [sf, sqlA + ";"],
            "rows": rows, "kpis": {"revenue": float(tot), "units": int(units), "txns": int(txns), "groups": len(rows)}}

@app.post("/api/reset")
def reset():
    c = conn(); cur = c.cursor(); cur.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"); cur.execute(f"CREATE SCHEMA {SCHEMA}"); c.close()
    return {"ok": True}

@app.get("/", response_class=HTMLResponse)
def index():
    return (BASE / "frontend" / "index.html").read_text(encoding="utf-8")
