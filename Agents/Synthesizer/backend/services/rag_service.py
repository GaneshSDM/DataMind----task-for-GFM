"""
Unstructured data service.
Runs PgVector cosine-similarity search for each embedding input.
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
    out = {}
    for k, v in row.items():
        if isinstance(v, decimal.Decimal):
            out[k] = float(v)
        elif isinstance(v, (datetime.datetime, datetime.date)):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


def _embedding_to_pg_literal(embedding: list) -> str:
    """
    Convert a Python list of numbers to a PgVector literal: '[0.01,-0.04,0.07]'
    Validates that all values are numeric to prevent injection.
    """
    validated = [float(v) for v in embedding]   # raises ValueError on bad input
    return "[" + ",".join(str(v) for v in validated) + "]"


def run_similarity_search(search_inputs: list) -> list:
    """
    Run one PgVector similarity search per input item.
    Errors are captured per-item and do NOT abort the batch.
    """
    results = []

    try:
        conn = _get_connection()
    except Exception as e:
        for item in search_inputs:
            results.append({
                "embedding_id": item.get("embedding_id", "UNKNOWN"),
                "label": item.get("label", item.get("embedding_id", "UNKNOWN")),
                "content": item.get("content", ""),
                "document_filter": item.get("document_filter"),
                "chunks": [],
                "chunk_count": 0,
                "status": "error",
                "error": f"Database connection failed: {e}",
            })
        return results

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            for item in search_inputs:
                eid = item.get("embedding_id", "UNKNOWN")
                label = item.get("label", eid)
                content = item.get("content", "")
                embedding = item.get("embedding", [])
                rag_table = item.get("rag_table", "")
                doc_filter = item.get("document_filter")
                top_k = int(item.get("top_k", 5))

                try:
                    emb_literal = _embedding_to_pg_literal(embedding)

                    # rag_document_chunks does NOT have document_name — it has file_id.
                    # We JOIN tracopp.rag_files to filter by original_file_name.
                    # The chunks table is addressed as the schema-qualified rag_table from JSON.
                    # The rag_files table lives in the same schema (tracopp).
                    rag_schema = rag_table.split(".")[0] if "." in rag_table else "tracopp"
                    files_table = f"{rag_schema}.rag_files"

                    if doc_filter:
                        sql = f"""
                            SELECT
                                c.chunk_id,
                                f.original_file_name  AS document_name,
                                c.page_number,
                                c.chunk_text,
                                1 - (c.embedding <=> '{emb_literal}'::vector) AS similarity_score
                            FROM {rag_table} c
                            JOIN {files_table} f ON c.file_id = f.file_id
                            WHERE f.original_file_name = %s
                            ORDER BY c.embedding <=> '{emb_literal}'::vector
                            LIMIT %s
                        """
                        cur.execute(sql, (doc_filter, top_k))
                    else:
                        sql = f"""
                            SELECT
                                c.chunk_id,
                                f.original_file_name  AS document_name,
                                c.page_number,
                                c.chunk_text,
                                1 - (c.embedding <=> '{emb_literal}'::vector) AS similarity_score
                            FROM {rag_table} c
                            JOIN {files_table} f ON c.file_id = f.file_id
                            ORDER BY c.embedding <=> '{emb_literal}'::vector
                            LIMIT %s
                        """
                        cur.execute(sql, (top_k,))

                    raw_chunks = cur.fetchall()
                    all_chunks = [_serialise_row(dict(c)) for c in raw_chunks]

                    # Quality gate — filter chunks below similarity threshold
                    from config import get_settings as _get_settings
                    _min_sim = _get_settings().rag_min_similarity
                    chunks = [
                        c for c in all_chunks
                        if float(c.get("similarity_score") or 0) >= _min_sim
                    ]

                    if len(chunks) < len(all_chunks):
                        import logging as _logging
                        _logging.getLogger("spyder.rag").debug(
                            "RAG quality gate: kept %d/%d chunks (min_similarity=%.2f) "
                            "for embedding_id=%s",
                            len(chunks), len(all_chunks), _min_sim, eid,
                        )

                    results.append({
                        "embedding_id": eid,
                        "label": label,
                        "content": content,
                        "document_filter": doc_filter,
                        "chunks": chunks,
                        "chunk_count": len(chunks),
                        "status": "success",
                    })

                except Exception as e:
                    conn.rollback()
                    results.append({
                        "embedding_id": eid,
                        "label": label,
                        "content": content,
                        "document_filter": doc_filter,
                        "chunks": [],
                        "chunk_count": 0,
                        "status": "error",
                        "error": str(e),
                    })
    finally:
        conn.close()

    return results
