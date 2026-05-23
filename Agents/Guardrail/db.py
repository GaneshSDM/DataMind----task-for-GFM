import os
import asyncio
import psycopg2
import psycopg2.pool

_pool: psycopg2.pool.ThreadedConnectionPool | None = None


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=10,
            host=os.environ["DB_HOST"],
            port=int(os.environ.get("DB_PORT", "6543")),
            dbname=os.environ.get("DB_NAME", "postgres"),
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
            sslmode=os.environ.get("DB_SSLMODE", "require"),
        )
    return _pool


def _fetch_sync(ids: list[str]) -> dict[str, dict]:
    pool = _get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id::text, check_value, embedding
                FROM tracopp.prompt_policies
                WHERE id = ANY(%s::uuid[])
                """,
                (ids,),
            )
            rows = cur.fetchall()
        return {
            row[0]: {"check_value": row[1], "embedding": row[2]}
            for row in rows
        }
    finally:
        pool.putconn(conn)


async def fetch_policies(ids: list[str]) -> dict[str, dict]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _fetch_sync, ids)
