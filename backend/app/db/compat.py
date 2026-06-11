"""
PostgreSQL → SQLite type compatibility layer.

When running with sqlite:///, SQLAlchemy's PostgreSQL dialect types
(JSONB, UUID) won't work. This module maps them to their SQLite equivalents.

Usage: instead of `from sqlalchemy.dialects.postgresql import UUID, JSONB`,
       use `from app.db.compat import UUID, JSONB`.
"""

import sqlalchemy.types as types
from app.core.config import settings

_is_sqlite = settings.DATABASE_URL.startswith("sqlite")

if _is_sqlite:
    from sqlalchemy import String, JSON

    class UUID(types.TypeDecorator):
        """SQLite-compatible UUID stored as String(36).
        Accepts ``as_uuid`` kwarg for compatibility with PostgreSQL caller code.
        """
        impl = String(36)
        cache_ok = True

        def __init__(self, as_uuid: bool = True, *args, **kwargs):
            # Ignore as_uuid — we always store as string
            super().__init__(*args, **kwargs)

        def process_bind_param(self, value, dialect):
            return str(value) if value else None

        def process_result_value(self, value, dialect):
            return value

    JSONB = JSON

    class Vector:
        """No-op Vector type for SQLite (pgvector not supported)."""
        def __init__(self, *args, **kwargs): pass
else:
    from sqlalchemy.dialects.postgresql import UUID, JSONB  # noqa: F401
    try:
        from pgvector.sqlalchemy import Vector  # noqa: F401
    except ImportError:
        Vector = None  # type: ignore