"""P8: add mastery-aware tutor columns to the existing 0013 tutor schema

Revision ID: 0029_tutor_sessions
Revises: 0028_ws10_idempotency_key_index
Create Date: 2026-09-03 00:00:00.000000

The Phase 4E tutor tables (``tutor_sessions`` and ``tutor_messages``) already
exist from migration ``0013_ai_tutor``. This P8 migration is strictly
additive: it adds the three mastery/grounding columns required by the
Mastery-Aware AI Tutor and one index to bound lookups. It does not create or
drop any tutor tables, preserving the orphaned-schema reuse decision.

* ``tutor_sessions.target_concept_id`` — optional weak target concept a P8
  session is anchored to (a ``concepts.public_id`` string).
* ``tutor_messages.source_kind``   — provenance of the answer: ``rag`` or
  ``deterministic`` (``TutorSourceKind``).
* ``tutor_messages.attribution``   — human-readable attribution naming the
  learner-owned source material the answer drew from.
* ``tutor_messages.confidence``    — confidence bucket (``high``/``medium``/
  ``low``, per ``TutorConfidenceLevel``).

Each statement is guarded so re-running is safe and so the migration is
idempotent against both fresh (SQLite ``create_all``) and pre-existing
(PostgreSQL via 0013) schemas.
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import inspect

revision = "0029_tutor_sessions"
down_revision = "0028_ws10_idempotency_key_index"
branch_labels = None
depends_on = None

TUTOR_MESSAGES_INDEX = "ix_tutor_messages_source_kind"


def _columns(table: str) -> set[str]:
    bind = op.get_bind()
    if bind is None or not inspect(bind).has_table(table):
        return set()
    return {c["name"] for c in inspect(bind).get_columns(table)}


def _index_exists(table: str, index_name: str) -> bool:
    bind = op.get_bind()
    if bind is None or not inspect(bind).has_table(table):
        return False
    index_names = {i["name"] for i in inspect(bind).get_indexes(table)}
    return index_name in index_names


def upgrade() -> None:
    session_cols = _columns("tutor_sessions")
    if "target_concept_id" not in session_cols:
        op.add_column(
            "tutor_sessions",
            op.Column("target_concept_id", op.String(length=40), nullable=True),
        )

    message_cols = _columns("tutor_messages")
    if "source_kind" not in message_cols:
        op.add_column(
            "tutor_messages",
            op.Column("source_kind", op.String(length=30), nullable=True),
        )
    if "attribution" not in message_cols:
        op.add_column(
            "tutor_messages",
            op.Column("attribution", op.String(length=1000), nullable=True),
        )
    if "confidence" not in message_cols:
        op.add_column(
            "tutor_messages",
            op.Column("confidence", op.String(length=20), nullable=True),
        )

    if not _index_exists("tutor_messages", TUTOR_MESSAGES_INDEX):
        op.create_index(
            TUTOR_MESSAGES_INDEX,
            "tutor_messages",
            ["source_kind"],
            unique=False,
        )


def downgrade() -> None:
    if _column_exists("tutor_messages", "confidence"):
        op.drop_column("tutor_messages", "confidence")
    if _column_exists("tutor_messages", "attribution"):
        op.drop_column("tutor_messages", "attribution")
    if _column_exists("tutor_messages", "source_kind"):
        op.drop_column("tutor_messages", "source_kind")
    if _index_exists("tutor_messages", TUTOR_MESSAGES_INDEX):
        op.drop_index(TUTOR_MESSAGES_INDEX, table_name="tutor_messages")
    if _column_exists("tutor_sessions", "target_concept_id"):
        op.drop_column("tutor_sessions", "target_concept_id")


def _column_exists(table: str, column: str) -> bool:
    return column in _columns(table)
