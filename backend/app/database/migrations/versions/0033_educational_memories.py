"""P12: add missing educational_memories table.

Revision ID: 0033_educational_memories
Revises: 0032_quiz_attempts_adaptive
Create Date: 2026-09-05 00:00:00.000000

The ``EducationalMemoryRecord`` ORM model (app/models/educational_memory.py)
has been a working part of P10/P11 (mastery tracking, adaptive review, study
plans, learning goals) but no migration ever created its table — the row only
appeared under SQLite's ``metadata.create_all``. On a fresh PostgreSQL the
migration lineage silently lacked ``educational_memories``, so the adaptive
assessment engine's ``load_from_db`` (and every other memory-backed service)
failed with ``relation educational_memories does not exist``.

This additive migration creates the table to match the ORM exactly (native
``jsonb`` for ``memory_data``, the unique ``user_id`` constraint and the
single-column index the model declares). It is idempotent-friendly via a
table-existence guard and does not rewrite any historical migration.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

from app.database.base import convention

revision = "0033_educational_memories"
down_revision = "0032_quiz_attempts_adaptive"
branch_labels = None
depends_on = None

TABLE = "educational_memories"


def _table_exists() -> bool:
    bind = op.get_bind()
    if bind is None:
        return True
    return inspect(bind).has_table(TABLE)


def upgrade() -> None:
    if _table_exists():
        return

    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "public_id",
            sa.String(length=40),
            nullable=False,
            server_default=sa.text(
                "('emem_' || replace(gen_random_uuid()::text, '-', ''))"
            ),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("memory_data", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=convention["fk"].format(
                table_name=TABLE,
                column_0_name="user_id",
                referred_table_name="users",
            ),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=convention["pk"].format(table_name=TABLE)),
        sa.UniqueConstraint(
            "user_id",
            name=convention["uq"].format(table_name=TABLE, column_0_name="user_id"),
        ),
    )
    op.create_index("ix_educational_memories_public_id", TABLE, ["public_id"], unique=True)
    op.create_index("ix_educational_memories_user_id", TABLE, ["user_id"], unique=False)
    op.create_index("ix_educational_memories_id", TABLE, ["id"], unique=False)


def downgrade() -> None:
    if not _table_exists():
        return
    op.drop_table(TABLE)
