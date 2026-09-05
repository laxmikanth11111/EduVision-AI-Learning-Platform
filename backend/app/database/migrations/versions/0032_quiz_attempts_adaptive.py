"""P12: add adaptive delivery flag + missing quiz_attempts.status index.

Revision ID: 0032_quiz_attempts_adaptive
Revises: 0031_review_schedule_concept
Create Date: 2026-09-05 00:00:00.000000

Two production-schema corrections, both additive and idempotent:

1. ``quiz_attempts.adaptive`` — the P12 adaptive assessment feature persists
   whether an attempt was requested in adaptive mode so delivery continues
   genuinely adaptively across resume. The adaptive flag is server-side only,
   so existing rows default to ``false`` (fixed order).

2. ``ix_quiz_attempts_status`` — the ``QuizAttempt`` ORM model declares this
   single-column index in ``__table_args__`` (``app/models/quiz_attempt.py``),
   but migration ``0005_quiz_subsystem`` only ever created
   ``ix_quiz_attempts_version_status`` and ``ix_quiz_attempts_quiz_user``.
   The schema is otherwise correct; this alignment closes the ORM/parity gap
   the same way 0030/0031 folded in missing ORM-declared indexes.

No historical migration is rewritten; Alembic head stays single.
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import Boolean, Column, inspect, text

revision = "0032_quiz_attempts_adaptive"
down_revision = "0031_review_schedule_concept"
branch_labels = None
depends_on = None

TABLE = "quiz_attempts"
COLUMN = "adaptive"
INDEX = "ix_quiz_attempts_status"


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    if bind is None or not inspect(bind).has_table(table):
        return False
    return column in {c["name"] for c in inspect(bind).get_columns(table)}


def _has_index(table: str, index_name: str) -> bool:
    bind = op.get_bind()
    if bind is None or not inspect(bind).has_table(table):
        return False
    return index_name in {i["name"] for i in inspect(bind).get_indexes(table)}


def upgrade() -> None:
    if not _has_column(TABLE, COLUMN):
        op.add_column(
            TABLE,
            column=Column(
                COLUMN,
                Boolean(),
                nullable=False,
                server_default=text("false"),
            ),
        )

    if not _has_index(TABLE, INDEX):
        op.create_index(INDEX, TABLE, ["status"], unique=False)


def downgrade() -> None:
    if _has_index(TABLE, INDEX):
        op.drop_index(INDEX, table_name=TABLE)

    if _has_column(TABLE, COLUMN):
        op.drop_column(TABLE, COLUMN)