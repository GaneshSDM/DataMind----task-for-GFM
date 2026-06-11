"""
Schema helper — provides SCHEMA-aware ForeignKey that strips the schema
prefix when running on SQLite (which does not support schemas).

Usage in model files:
    from app.db.schema_helper import SCHEMA, fk, table_args
    ...
    __table_args__ = table_args("tracopp")
    user_id = Column(Integer, ForeignKey(fk("users.user_id")), nullable=False)
"""

from sqlalchemy import ForeignKey as SA_ForeignKey
from app.core.config import settings

_is_sqlite = settings.DATABASE_URL.startswith("sqlite")
SCHEMA = "" if _is_sqlite else "tracopp"


def fk(target: str, **kwargs) -> SA_ForeignKey:
    """
    Create a ForeignKey, stripping the schema prefix for SQLite.

    The target should always be "table.column" (no schema prefix).
    When running on PostgreSQL, the schema is prepended automatically.
    When running on SQLite, it's used as-is.

    Usage:  fk("users.user_id")
    """
    if _is_sqlite:
        # Use target as-is (no schema prefix for SQLite)
        return SA_ForeignKey(target, **kwargs)
    # Prepend SCHEMA for PostgreSQL
    return SA_ForeignKey(f"{SCHEMA}.{target}", **kwargs)


def table_args(schema_name: str = "tracopp") -> dict:
    """Return __table_args__ dict suitable for the current engine."""
    if _is_sqlite:
        return {}
    return {"schema": schema_name}