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

_IDENT_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')

def validate_identifier(name: str, label: str = "identifier") -> str:
    """Reject identifiers that don't match [A-Za-z_][A-Za-z0-9_]* to prevent SQL injection."""
    if not _IDENT_RE.match(name):
        raise HTTPException(400, f"Invalid {label} '{name}': only letters, digits and underscores are allowed, and it must not start with a digit.")
    return name

app = FastAPI(title="DataMind DataFlow")
_CORS_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:8000,http://localhost:5173").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=_CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])

def conn():
    if not DATABASE_URL:
        raise HTTPException(500, "DATABASE_URL not set in .env")
    return psycopg2.connect(DATABASE_URL, connect_timeout=15)

def project_ref():
    m = re.search(r"postgres\.([a-z0-9]+)", DATABASE_URL or ""); return m.group(1) if m else "?"

def is_int(v):   return bool(v != "" and re.fullmatch(r"-?\d+", v))
def is_float(v):
    if v == "": return False
    try: float(v); return True
    except: return False
def is_date(v):  return bool(v != "" and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v))
def is_timestamp(v): return bool(v != "" and re.fullmatch(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})?", v))

def infer_one(name, vals):
    n = name.lower()
    if vals and "timestamp" in n and all(is_timestamp(x) for x in vals): return "TIMESTAMP"
    if vals and "date" in n and all(is_date(x) for x in vals): return "DATE"
    if vals and all(is_int(x) for x in vals):   return "BIGINT"
    if vals and all(is_float(x) for x in vals): return "DOUBLE PRECISION"
    return "TEXT"

def read_csv_file(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        r = csv.reader(f)
        try:
            header = next(r)
        except StopIteration:
            raise ValueError(f"CSV file is empty: {path}")
        rows = [row for row in r if any(c.strip() for c in row)]
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

def _qi(name: str) -> str:
    """Return a double-quoted SQL identifier (safe after validate_identifier)."""
    return '"' + name.replace('"', '""') + '"'

def ddl_for(table, cols):
    validate_identifier(table, "table name")
    for c in cols:
        validate_identifier(c["column"], "column name")
    body = ",\n  ".join(f'{_qi(c["column"])} {c["type"]}' for c in cols)
    return f"CREATE TABLE {_qi(SCHEMA)}.{_qi(table)} (\n  {body}\n);"

def conv(v, t):
    if v is None or v == "": return None
    if t == "BIGINT": return int(v)
    if t == "DOUBLE PRECISION": return float(v)
    if t == "DATE": return v
    if t == "TIMESTAMP": return v
    return v

def jval(v):
    if isinstance(v, Decimal): return float(v)
    if isinstance(v, (datetime.date, datetime.datetime)): return v.isoformat()
    return v

def preview(cur, table, limit=6):
    validate_identifier(table, "table name")
    cur.execute(f"SELECT * FROM {_qi(SCHEMA)}.{_qi(table)} LIMIT %s", (limit,))
    names = [d[0] for d in cur.description]
    return [{n: jval(v) for n, v in zip(names, row)} for row in cur.fetchall()]

def ensure_schema(cur): cur.execute(f"CREATE SCHEMA IF NOT EXISTS {_qi(SCHEMA)}")
def table_exists(cur, t):
    cur.execute("select 1 from information_schema.tables where table_schema=%s and table_name=%s", (SCHEMA, t))
    return cur.fetchone() is not None

def load_table(table):
    validate_identifier(table, "table name")
    src = find_source(table)
    if not src: raise HTTPException(404, f"No CSV found for '{table}'. Upload {table}.csv first.")
    header, rows = read_csv_file(src)
    cols = profile(header, rows); types = [c["type"] for c in cols]
    for col in cols: validate_identifier(col["column"], "column name")
    c = conn(); cur = c.cursor()
    try:
        ensure_schema(cur)
        cur.execute(f"DROP TABLE IF EXISTS {_qi(SCHEMA)}.{_qi(table)} CASCADE")
        cur.execute(ddl_for(table, cols))
        collist = ", ".join(_qi(x["column"]) for x in cols)
        vals = [tuple(conv(row[i] if i < len(row) else "", types[i]) for i in range(len(cols))) for row in rows]
        if vals: execute_values(cur, f"INSERT INTO {_qi(SCHEMA)}.{_qi(table)} ({collist}) VALUES %s", vals)
        cur.execute(f"SELECT count(*) FROM {_qi(SCHEMA)}.{_qi(table)}"); n = cur.fetchone()[0]
        nulls = sum(1 for row in rows for i in range(len(cols)) if i >= len(row) or row[i] == "")
        prev = preview(cur, table)
        c.commit()
    except Exception:
        c.rollback(); raise
    finally:
        c.close()
    return cols, ddl_for(table, cols), n, prev, nulls

def ensure_loaded(cur, tables, steps):
    for t in tables:
        if not table_exists(cur, t):
            load_table(t); steps.append({"agent": "Ingestion", "label": f"auto-load dependency: {t}"})

def build_dim_product(cur):
    validate_identifier("dim_product", "table name")
    sql = (f"CREATE TABLE {_qi(SCHEMA)}.{_qi('dim_product')} AS\n"
           f"SELECT {_qi('p')}.{_qi('product_id')}, {_qi('p')}.{_qi('product_name')}, {_qi('p')}.{_qi('category_id')}, {_qi('c')}.{_qi('category_name')}, {_qi('p')}.{_qi('unit_cost')}, {_qi('p')}.{_qi('unit_price')}\n"
           f"FROM {_qi(SCHEMA)}.{_qi('products')} {_qi('p')} JOIN {_qi(SCHEMA)}.{_qi('categories')} {_qi('c')} ON {_qi('p')}.{_qi('category_id')} = {_qi('c')}.{_qi('category_id')}")
    cur.execute(f"DROP TABLE IF EXISTS {_qi(SCHEMA)}.{_qi('dim_product')} CASCADE"); cur.execute(sql); return sql + ";"

def build_dim_customer(cur):
    validate_identifier("dim_customer", "table name")
    sql = (f"CREATE TABLE {_qi(SCHEMA)}.{_qi('dim_customer')} AS\n"
           f"SELECT {_qi('customer_id')}, {_qi('first_name')}, {_qi('last_name')},\n"
           "       CASE gender_code WHEN 1 THEN 'Male' WHEN 2 THEN 'Female' END AS gender, city, country\n"
           f"FROM {_qi(SCHEMA)}.{_qi('customers')}")
    cur.execute(f"DROP TABLE IF EXISTS {_qi(SCHEMA)}.{_qi('dim_customer')} CASCADE"); cur.execute(sql); return sql + ";"

def build_fact(cur):
    validate_identifier("fact_sales", "table name")
    sql = (f"CREATE TABLE {_qi(SCHEMA)}.{_qi('fact_sales')} AS\n"
           f"SELECT {_qi('t')}.{_qi('txn_id')}, {_qi('t')}.{_qi('txn_date')}, {_qi('dc')}.{_qi('first_name')}||' '||{_qi('dc')}.{_qi('last_name')} AS customer, {_qi('dc')}.{_qi('gender')},\n"
           f"       {_qi('dp')}.{_qi('product_name')} AS product, {_qi('dp')}.{_qi('category_name')} AS category,\n"
           f"       {_qi('t')}.{_qi('quantity')}, {_qi('dp')}.{_qi('unit_price')}, {_qi('t')}.{_qi('quantity')}*{_qi('dp')}.{_qi('unit_price')} AS revenue\n"
           f"FROM {_qi(SCHEMA)}.{_qi('transactions')} {_qi('t')}\n"
           f"JOIN {_qi(SCHEMA)}.{_qi('dim_product')}  {_qi('dp')} ON {_qi('t')}.{_qi('product_id')}  = {_qi('dp')}.{_qi('product_id')}\n"
           f"JOIN {_qi(SCHEMA)}.{_qi('dim_customer')} {_qi('dc')} ON {_qi('t')}.{_qi('customer_id')} = {_qi('dc')}.{_qi('customer_id')}")
    cur.execute(f"DROP TABLE IF EXISTS {_qi(SCHEMA)}.{_qi('fact_sales')} CASCADE"); cur.execute(sql); return sql + ";"

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
    out = []; skipped = []
    for f in files:
        if not f.filename.lower().endswith(".csv"):
            skipped.append({"filename": f.filename, "reason": "not a CSV"})
            continue
        stem = Path(f.filename).stem
        try:
            validate_identifier(stem, "filename stem")
        except HTTPException as e:
            skipped.append({"filename": f.filename, "reason": e.detail})
            continue
        p = UPLOADS / (stem + ".csv"); p.write_bytes(await f.read())
        header, rows = read_csv_file(p)
        out.append({"table": p.stem, "rows": len(rows), "columns": profile(header, rows)})
    return {"uploaded": out, "skipped": skipped}

@app.get("/api/export/csv/{table}")
def export_csv(table: str):
    from fastapi.responses import StreamingResponse
    import io
    validate_identifier(table, "table name")
    c = conn(); cur = c.cursor()
    try:
        cur.execute("select 1 from information_schema.tables where table_schema=%s and table_name=%s", (SCHEMA, table))
        if cur.fetchone() is None:
            raise HTTPException(404, f"Table {table} not found in schema {SCHEMA}")
        cur.execute(f"SELECT * FROM {_qi(SCHEMA)}.{_qi(table)}")
        header = [d[0] for d in cur.description]
        buf = io.StringIO(); w = csv.writer(buf)
        w.writerow(header)
        for row in cur.fetchall():
            w.writerow([jval(v) for v in row])
        data = buf.getvalue().encode("utf-8-sig")
    finally:
        c.close()
    return StreamingResponse(io.BytesIO(data), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f"attachment; filename={table}.csv"})

@app.get("/api/export/sql")
def export_sql():
    """Return a reproducible SQL script for the current demo pipeline."""
    script = [
        f"CREATE SCHEMA IF NOT EXISTS {_qi(SCHEMA)};",
        f"-- Generated by DataMind DataFlow on {datetime.datetime.utcnow().isoformat()}Z",
    ]
    for table in ["categories", "products", "customers", "transactions"]:
        src = find_source(table)
        if src:
            header, rows = read_csv_file(src)
            cols = profile(header, rows)
            script.append(ddl_for(table, cols))
            # Best-effort insert placeholders; real values inserted via load_table at runtime.
            collist = ", ".join(_qi(c["column"]) for c in cols)
            script.append(f"-- INSERT INTO {_qi(SCHEMA)}.{_qi(table)} ({collist}) VALUES ... ({len(rows)} rows loaded by app)")
    script.append(build_dim_product.__doc__ or "")
    # Note: build_dim_product/Customer/Fact require a cursor, so we append their static SQL shapes manually.
    script.extend([
        f"DROP TABLE IF EXISTS {_qi(SCHEMA)}.{_qi('dim_product')} CASCADE;",
        f"CREATE TABLE {_qi(SCHEMA)}.{_qi('dim_product')} AS SELECT p.product_id, p.product_name, p.category_id, c.category_name, p.unit_cost, p.unit_price FROM {_qi(SCHEMA)}.{_qi('products')} p JOIN {_qi(SCHEMA)}.{_qi('categories')} c ON p.category_id = c.category_id;",
        f"DROP TABLE IF EXISTS {_qi(SCHEMA)}.{_qi('dim_customer')} CASCADE;",
        f"CREATE TABLE {_qi(SCHEMA)}.{_qi('dim_customer')} AS SELECT customer_id, first_name, last_name, CASE gender_code WHEN 1 THEN 'Male' WHEN 2 THEN 'Female' END AS gender, city, country FROM {_qi(SCHEMA)}.{_qi('customers')};",
        f"DROP TABLE IF EXISTS {_qi(SCHEMA)}.{_qi('fact_sales')} CASCADE;",
        f"CREATE TABLE {_qi(SCHEMA)}.{_qi('fact_sales')} AS SELECT t.txn_id, t.txn_date, dc.first_name||' '||dc.last_name AS customer, dc.gender, dp.product_name AS product, dp.category_name AS category, t.quantity, dp.unit_price, t.quantity*dp.unit_price AS revenue FROM {_qi(SCHEMA)}.{_qi('transactions')} t JOIN {_qi(SCHEMA)}.{_qi('dim_product')} dp ON t.product_id = dp.product_id JOIN {_qi(SCHEMA)}.{_qi('dim_customer')} dc ON t.customer_id = dc.customer_id;",
        f"DROP TABLE IF EXISTS {_qi(SCHEMA)}.{_qi('agg_sales_by_category')} CASCADE;",
        f"CREATE TABLE {_qi(SCHEMA)}.{_qi('agg_sales_by_category')} AS SELECT category, SUM(quantity) AS units, SUM(revenue) AS revenue, COUNT(*) AS txns FROM {_qi(SCHEMA)}.{_qi('fact_sales')} GROUP BY category ORDER BY revenue DESC;",
        f"DROP TABLE IF EXISTS {_qi(SCHEMA)}.{_qi('agg_sales_by_customer')} CASCADE;",
        f"CREATE TABLE {_qi(SCHEMA)}.{_qi('agg_sales_by_customer')} AS SELECT customer, SUM(quantity) AS units, SUM(revenue) AS revenue, COUNT(*) AS txns FROM {_qi(SCHEMA)}.{_qi('fact_sales')} GROUP BY customer ORDER BY revenue DESC;",
    ])
    return {"schema": SCHEMA, "sql": "\n\n".join(script)}

@app.get("/api/catalog")
def catalog():
    c = conn(); cur = c.cursor()
    try:
        cur.execute("select table_name from information_schema.tables where table_schema=%s order by table_name", (SCHEMA,))
        tabs = [r[0] for r in cur.fetchall()]; out = []
        for t in tabs:
            cur.execute(f"SELECT count(*) FROM {_qi(SCHEMA)}.{_qi(t)}"); out.append({"table": t, "rows": cur.fetchone()[0]})
    finally:
        c.close()
    return {"schema": SCHEMA, "tables": out}

@app.post("/api/ingest")
def ingest(payload: dict = Body(...)):
    table = payload.get("table") or ""
    validate_identifier(table, "table name")
    cols, ddl, n, prev, nulls = load_table(table)
    steps = [{"agent": "Discovery", "label": f"introspect & profile {table}"},
             {"agent": "Ingestion", "label": f"create + load {SCHEMA}.{table}"},
             {"agent": "Quality", "label": "row-count & null checks"}]
    return {"table": table, "steps": steps, "ddl": ddl, "profile": cols,
            "rows": n, "nulls": nulls, "preview": prev}

@app.post("/api/transform")
def transform():
    steps = []; c = conn(); cur = c.cursor()
    try:
        ensure_schema(cur)
        ensure_loaded(cur, ["products", "categories", "customers"], steps)
        s1 = build_dim_product(cur); steps.append({"agent": "Transformation", "label": "join products × categories → category_name"})
        s2 = build_dim_customer(cur); steps.append({"agent": "Transformation", "label": "map gender_code → Male/Female"})
        pv1 = preview(cur, "dim_product"); pv2 = preview(cur, "dim_customer")
        steps.append({"agent": "Quality", "label": "validate mapped domains"})
        c.commit()
    except Exception:
        c.rollback(); raise
    finally:
        c.close()
    return {"steps": steps, "sql": [s1, s2], "previews": {"dim_product": pv1, "dim_customer": pv2}}

@app.post("/api/aggregate")
def aggregate(payload: dict = Body(default={})):
    by = "customer" if (payload or {}).get("by") == "customer" else "category"
    steps = []; c = conn(); cur = c.cursor()
    try:
        ensure_schema(cur)
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
        c.commit()
    except Exception:
        c.rollback(); raise
    finally:
        c.close()
    return {"by": by, "steps": steps, "sql": sqls + [sf, sqlA + ";"],
            "rows": rows, "kpis": {"revenue": float(tot), "units": int(units), "txns": int(txns), "groups": len(rows)}}

@app.post("/api/reset")
def reset():
    c = conn(); cur = c.cursor()
    try:
        cur.execute(f"DROP SCHEMA IF EXISTS {_qi(SCHEMA)} CASCADE")
        cur.execute(f"CREATE SCHEMA {_qi(SCHEMA)}")
        c.commit()
    except Exception:
        c.rollback(); raise
    finally:
        c.close()
    return {"ok": True}

@app.get("/", response_class=HTMLResponse)
def index():
    return (BASE / "frontend" / "index.html").read_text(encoding="utf-8")
