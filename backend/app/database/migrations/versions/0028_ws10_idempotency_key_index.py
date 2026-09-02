"""WS10: index generated_lessons.idempotency_key for key-only dedupe lookups

Revision ID: 0028_ws10_idempotency_key_index
Revises: 0027_ws5_lesson_user_owner
Create Date: 2026-09-02 00:00:00.000000

``find_by_idempotency_key`` resolves replays by ``idempotency_key`` alone
(the caller additionally verifies the owning presentation id). The existing
composite UNIQUE indexes cannot serve that lookup:

* ``uq_generated_lessons_user_idempotency`` is on ``(user_id, idempotency_key)``
  - a key-only predicate can only use it with a full scan when ``user_id`` is
  NULL, since the column is not leading.
* ``uq_generated_lessons_idempotency_null`` is a partial index restricted to
  ``user_id IS NULL`` rows only.

A plain (non-unique) index on ``idempotency_key`` makes the dedupe query a
point lookup for every row and, thanks to the existing constraints, cannot
introduce duplicate-key risk on its own.
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import inspect

revision = "0028_ws10_idempotency_key_index"
down_revision = "0027_ws5_lesson_user_owner"
branch_labels = None
depends_on = None

INDEX_NAME = "ix_generated_lessons_idempotency_key"


def _index_exists(table: str, index_name: str) -> bool:
    index_names = {i["name"] for i in inspect(op.get_bind()).get_indexes(table)}
    return index_name in index_names


def upgrade() -> None:
    bind = op.get_bind()
    if bind is None or not inspect(bind).has_table("generated_lessons"):
        return
    if _index_exists("generated_lessons", INDEX_NAME):
        return
    op.create_index(
        INDEX_NAME,
        "generated_lessons",
        ["idempotency_key"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind is None or not inspect(bind).has_table("generated_lessons"):
        return
    if _index_exists("generated_lessons", INDEX_NAME):
        op.drop_index(INDEX_NAME, table_name="generated_lessons")
