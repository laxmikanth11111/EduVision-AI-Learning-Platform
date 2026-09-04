"""P10: add concept_id + last_reviewed_at to review_schedules

Revision ID: 0031_review_schedule_concept
Revises: 0030_tutor_conversation_index
Create Date: 2026-09-04 00:00:00.000000

The ``review_schedules`` table was created as a schema-only stub by migration
``0011_personalized_learning`` (no ORM model). P10 implements the spaced
repetition engine on top of it and introduces the ``ReviewSchedule`` ORM model.
This additive migration adds the two columns the engine keys on:

  - ``concept_id``   UUID FK -> ``concepts.id`` (ON DELETE SET NULL), nullable
                     to preserve any legacy rows; new rows always set it.
  - ``last_reviewed_at``  timezone-aware datetime, nullable.

and the two indexes the ORM declares:

  - ``ix_review_schedules_concept_id`` (concept_id)
  - ``ix_review_schedules_user_due`` (user_id, due_at)  -> efficient due-queue

Everything is additive and idempotent (guarded by existence checks) and never
rewrites existing data. After this change the ORM metadata and the migrated
PostgreSQL schema agree on the ``review_schedules`` columns/indexes.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

from app.database.base import convention

revision = "0031_review_schedule_concept"
down_revision = "0030_tutor_conversation_index"
branch_labels = None
depends_on = None

TABLE = "review_schedules"


def _table_columns() -> set[str]:
    bind = op.get_bind()
    if bind is None or not inspect(bind).has_table(TABLE):
        return set()
    return {c["name"] for c in inspect(bind).get_columns(TABLE)}


def _index_exists(table: str, index_name: str) -> bool:
    bind = op.get_bind()
    if bind is None or not inspect(bind).has_table(table):
        return False
    names = {i["name"] for i in inspect(bind).get_indexes(table)}
    return index_name in names


def upgrade() -> None:
    columns = _table_columns()

    if "concept_id" not in columns:
        op.add_column(
            TABLE,
            sa.Column(
                "concept_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey(
                    "concepts.id",
                    name=convention["fk"].format(
                        table_name="review_schedules",
                        column_0_name="concept_id",
                        referred_table_name="concepts",
                    ),
                    ondelete="SET NULL",
                ),
                nullable=True,
            ),
        )
    if "last_reviewed_at" not in columns:
        op.add_column(
            TABLE,
            sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        )

    if not _index_exists(TABLE, "ix_review_schedules_concept_id"):
        op.create_index(
            "ix_review_schedules_concept_id", TABLE, ["concept_id"], unique=False
        )
    if not _index_exists(TABLE, "ix_review_schedules_user_due"):
        op.create_index(
            "ix_review_schedules_user_due", TABLE, ["user_id", "due_at"], unique=False
        )


def downgrade() -> None:
    if _index_exists(TABLE, "ix_review_schedules_user_due"):
        op.drop_index("ix_review_schedules_user_due", table_name=TABLE)
    if _index_exists(TABLE, "ix_review_schedules_concept_id"):
        op.drop_index("ix_review_schedules_concept_id", table_name=TABLE)

    columns = _table_columns()
    if "last_reviewed_at" in columns:
        op.drop_column(TABLE, "last_reviewed_at")
    if "concept_id" in columns:
        op.drop_column(TABLE, "concept_id")
