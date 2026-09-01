"""WS5/WS8: enforce lesson idempotency for NULL-user rows (Phase 2)

Revision ID: 0027_ws5_lesson_user_owner
Revises: 0026_ws2_pg_parity
Create Date: 2026-09-01 00:00:00.000000

``create_lesson`` now stamps ``generated_lessons.user_id`` from the owning
presentation instead of writing ``NULL``, so the existing
``uq_generated_lessons_user_idempotency`` composite constraint finally guards
replays for owned presentations.

Rows created before that change - and any owner-less presentation - keep
``user_id`` NULL, where a composite UNIQUE never fires because NULLs are
always distinct. This partial unique index closes that gap:

    CREATE UNIQUE INDEX uq_generated_lessons_idempotency_null
    ON generated_lessons (idempotency_key) WHERE user_id IS NULL;

It is created natively for PostgreSQL and SQLite (both support partial
indexes) and skipped on other dialects, where the service-level idempotency
lookup still applies.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0027_ws5_lesson_user_owner"
down_revision = "0026_ws2_pg_parity"
branch_labels = None
depends_on = None

INDEX_NAME = "uq_generated_lessons_idempotency_null"


def _dialect() -> str:
    bind = op.get_bind()
    return bind.dialect.name if bind is not None else ""


def _index_exists(table: str, index_name: str) -> bool:
    index_names = {i["name"] for i in inspect(op.get_bind()).get_indexes(table)}
    return index_name in index_names


def upgrade() -> None:
    dialect = _dialect()
    if dialect not in ("postgresql", "sqlite"):
        return
    if not _table_exists("generated_lessons") or _index_exists(
        "generated_lessons", INDEX_NAME
    ):
        return
    where = sa.text("user_id IS NULL")
    if dialect == "postgresql":
        op.create_index(
            INDEX_NAME,
            "generated_lessons",
            ["idempotency_key"],
            unique=True,
            postgresql_where=where,
        )
    else:
        op.create_index(
            INDEX_NAME,
            "generated_lessons",
            ["idempotency_key"],
            unique=True,
            sqlite_where=where,
        )


def _table_exists(name: str) -> bool:
    return inspect(op.get_bind()).has_table(name)


def downgrade() -> None:
    if _table_exists("generated_lessons") and _index_exists(
        "generated_lessons", INDEX_NAME
    ):
        op.drop_index(INDEX_NAME, table_name="generated_lessons")
