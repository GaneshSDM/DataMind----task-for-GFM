"""
Structured data service.
Executes validated SELECT queries against PostgreSQL.
"""
import decimal
import datetime
import psycopg2
from psycopg2.extras import RealDictCursor

from config import get_settings


def _get_connection():
    s = get_settings()
    return psycopg2.connect(
        host=s.db_host,
        port=s.db_port,
        dbname=s.db_name,
        user=s.db_user,
        password=s.db_password,
        sslmode=s.db_sslmode,
        connect_timeout=10,
    )


def _serialise_row(row: dict) -> dict:
    """Convert non-JSON-serialisable types from psycopg2."""
    out = {}
    for k, v in row.items():
        if isinstance(v, decimal.Decimal):
            out[k] = float(v)
        elif isinstance(v, (datetime.datetime, datetime.date, datetime.time)):
            out[k] = v.isoformat()
        elif isinstance(v, memoryview):
            out[k] = v.tobytes().hex()
        else:
            out[k] = v
    return out


def execute_sql_scripts(sql_scripts: list) -> list:
    """
    Run each SQL script and return a list of result dicts.
    Errors are captured per-query; they do NOT abort the batch.
    """
    results = []

    try:
        conn = _get_connection()
    except Exception as e:
        # Return error for every script if we can't even connect
        for script in sql_scripts:
            results.append({
                "query_id": script.get("query_id", "UNKNOWN"),
                "label": script.get("label", script.get("query_id", "UNKNOWN")),
                "source_table": script.get("source_table", ""),
                "rows": [],
                "row_count": 0,
                "columns": [],
                "status": "error",
                "error": f"Database connection failed: {e}",
            })
        return results

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            for script in sql_scripts:
                qid = script.get("query_id", "UNKNOWN")
                label = script.get("label", qid)
                source = script.get("source_table", "")
                sql = script.get("sql", "").strip()

                try:
                    cur.execute(sql)
                    raw_rows = cur.fetchall()
                    rows = [_serialise_row(dict(r)) for r in raw_rows]
                    columns = list(rows[0].keys()) if rows else []
                    results.append({
                        "query_id": qid,
                        "label": label,
                        "source_table": source,
                        "rows": rows,
                        "row_count": len(rows),
                        "columns": columns,
                        "status": "success",
                    })
                except Exception as e:
                    conn.rollback()  # reset tx after error
                    results.append({
                        "query_id": qid,
                        "label": label,
                        "source_table": source,
                        "rows": [],
                        "row_count": 0,
                        "columns": [],
                        "status": "error",
                        "error": str(e),
                    })
    finally:
        conn.close()

    return results


def test_connection() -> dict:
    """Health-check: verify DB is reachable and pgvector is installed."""
    try:
        conn = _get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT version();")
            pg_ver = cur.fetchone()[0]

            # Check pgvector extension
            cur.execute(
                "SELECT installed_version FROM pg_available_extensions WHERE name = 'vector';"
            )
            row = cur.fetchone()
            pgvector_ver = row[0] if row and row[0] else "not installed"

        conn.close()
        return {
            "status": "ok",
            "postgres_version": pg_ver,
            "pgvector_version": pgvector_ver,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
