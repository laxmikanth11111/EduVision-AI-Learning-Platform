"""P9 (F6): add missing composite conversation index to match the ORM

Revision ID: 0030_tutor_conversation_index
Revises: 0029_tutor_sessions
Create Date: 2026-09-04 00:00:00.000000

The ``TutorConversation`` ORM model (``app/models/tutor_conversation.py``)
declares a composite index ``ix_tutor_conversations_lesson`` over
``(lesson_id, status)`` in ``__table_args__``. Migration ``0013_ai_tutor``
only created the single-column ``ix_tutor_conversations_lesson_id``, so a
fresh ``create_all`` (SQLite) and the migrated (PostgreSQL) schemas drifted:
the composite index the model expects never existed. This migration is the
additive, idempotent alignment — it creates only that missing index.

After this change, the ORM metadata and the physical schema agree on the
``tutor_conversations`` indexes, closing the F6 ORM/migration parity gap.
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import inspect

revision = "0030_tutor_conversation_index"
down_revision = "0029_tutor_sessions"
branch_labels = None
depends_on = None

INDEX_NAME = "ix_tutor_conversations_lesson"
TABLE = "tutor_conversations"


def _index_exists(table: str, index_name: str) -> bool:
    bind = op.get_bind()
    if bind is None or not inspect(bind).has_table(table):
        return False
    index_names = {i["name"] for i in inspect(bind).get_indexes(table)}
    return index_name in index_names


def upgrade() -> None:
    if not _index_exists(TABLE, INDEX_NAME):
        op.create_index(
            INDEX_NAME,
            TABLE,
            ["lesson_id", "status"],
            unique=False,
        )


def downgrade() -> None:
    if _index_exists(TABLE, INDEX_NAME):
        op.drop_index(INDEX_NAME, table_name=TABLE)
