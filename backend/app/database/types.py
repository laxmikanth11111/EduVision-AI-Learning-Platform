"""Portable JSON type that works on both PostgreSQL (JSONB) and SQLite (JSON)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, TypeDecorator
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeEngine


class PortableJSONB(TypeDecorator[Any]):
    """JSONB on PostgreSQL, plain JSON on SQLite.

    This lets the same ORM model definitions work in both production
    (PostgreSQL) and the test suite (SQLite).
    """

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import JSONB

            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())

    def _compare_values(self, x: Any, y: Any) -> bool:
        return bool(x == y)
