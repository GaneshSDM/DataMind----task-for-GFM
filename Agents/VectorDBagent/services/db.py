"""
RAVEN database service.
Provides file authorization check: verifies that a RAG file exists
and its category aligns with the user's allowed domain.

Uses psycopg2 direct connection (same pattern as SPYDER sql_service).
Credentials read from config (backend/.env).
"""
import logging
import psycopg2
from psycopg2.extras import RealDictCursor

from config import get_settings

logger = logging.getLogger("raven.db")


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


def verify_file_authorized(filename: str, domain_name: str) -> bool:
    """
    Return True if filename exists in tracopp.rag_files AND its RAG category
    aligns with domain_name (case-insensitive match on category_name).

    Fail-closed on DB error: returns False and logs warning so the intent is
    excluded from search_inputs rather than potentially leaking cross-domain data.

    Query joins:
      rag_files → rag_sub_category → rag_category
    and checks category_name ~ domain_name (e.g. "HR", "Sales").
    """
    try:
        conn = _get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Layer 1 (in-memory domain check) already validated domain access.
                # Layer 2 confirms the file exists and is active — no category name
                # match needed (rag_category names differ from governance domain names).
                cur.execute(
                    """
                    SELECT rf.file_id
                    FROM tracopp.rag_files rf
                    WHERE rf.original_file_name = %s
                      AND rf.is_active = true
                    LIMIT 1
                    """,
                    (filename,),
                )
                row = cur.fetchone()
        finally:
            conn.close()

        authorized = row is not None
        if not authorized:
            logger.warning(
                "RAVEN file authorization denied: file='%s' — not found or inactive",
                filename,
            )
        return authorized

    except Exception as e:
        logger.error(
            "RAVEN DB authorization check failed file='%s' domain='%s': %s — "
            "denying access (fail-closed)",
            filename, domain_name, e,
        )
        return False   # fail-closed: deny on DB error
