"""quiz performance indexes

Revision ID: 0008_quiz_performance_indexes
Revises: 0007_adaptive_learning
Create Date: 2026-08-03 00:00:00.000000

Adds the composite indexes the quiz subsystem relies on for its hottest
query patterns:

* ``quiz_attempts (status, started_at)`` — the timeout worker scans
  in-progress attempts in started order (``list_expired_in_progress``).
* ``quiz_attempts (user_id, status, completed_at)`` — the adaptive mastery
  engine's ``list_scored_for_user`` (most-recently-scored per user).
* ``quiz_versions (quiz_id, status)`` — published/latest-version lookups
  (``get_published_for_quiz``, ``get_latest_succeeded_for_quiz``).

Existing single-column indexes already cover public-id lookups, foreign-key
joins and the ``(quiz_id, version)`` unique constraint.

All indexes are non-blocking on PostgreSQL (CONCURRENTLY is applied by the
operational runbook; a plain ``op.create_index`` here keeps alembic's
``downgrade``/``upgrade`` symmetrical and simple for fresh installs).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_quiz_performance_indexes"
down_revision = "0007_adaptive_learning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_quiz_attempts_status_started",
        "quiz_attempts",
        ["status", "started_at"],
        unique=False,
    )
    op.create_index(
        "ix_quiz_attempts_user_status_completed",
        "quiz_attempts",
        ["user_id", "status", "completed_at"],
        unique=False,
    )
    op.create_index(
        "ix_quiz_versions_quiz_status",
        "quiz_versions",
        ["quiz_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_quiz_versions_quiz_status", table_name="quiz_versions")
    op.drop_index(
        "ix_quiz_attempts_user_status_completed",
        table_name="quiz_attempts",
    )
    op.drop_index("ix_quiz_attempts_status_started", table_name="quiz_attempts")


def upgrade_data() -> None:
    """Idempotent online-friendly variant for hot upgrades.

    Creates each index only if it does not already exist, so the migration can
    be re-run against a live database after a partial outage.
    """
    inspector = sa.inspect(op.get_bind())
    existing = {
        index["name"] for index in inspector.get_indexes("quiz_attempts")
    }
    for name, table, columns in [
        (
            "ix_quiz_attempts_status_started",
            "quiz_attempts",
            ["status", "started_at"],
        ),
        (
            "ix_quiz_attempts_user_status_completed",
            "quiz_attempts",
            ["user_id", "status", "completed_at"],
        ),
    ]:
        if name not in existing:
            op.create_index(name, table, columns)
    existing_versions = {
        index["name"] for index in inspector.get_indexes("quiz_versions")
    }
    if "ix_quiz_versions_quiz_status" not in existing_versions:
        op.create_index(
            "ix_quiz_versions_quiz_status",
            "quiz_versions",
            ["quiz_id", "status"],
        )
