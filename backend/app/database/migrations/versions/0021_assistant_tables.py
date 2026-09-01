"""AI learning assistant tables (Phase 4D.6)

Revision ID: 0021_assistant_tables
Revises: 0020_create_users
Create Date: 2026-08-19 00:00:00.000000

No-op revision.

The four assistant tables (assistant_sessions, assistant_conversations,
assistant_messages, assistant_context_snapshots) are ALREADY created by
``0011_personalized_learning``, which also declares the ``user_id`` foreign
keys that match the ORM models. Re-creating them here breaks both fresh
installs (relation already exists) and upgrades from deployments that ran
``0011``. This revision is retained in the lineage so that
``0020_create_users -> 0021_assistant_tables`` remains replayable.
"""

from __future__ import annotations

from alembic import op

revision = "0021_assistant_tables"
down_revision = "0020_create_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """No-op: the assistant tables already exist (see 0011_personalized_learning)."""


def downgrade() -> None:
    op.drop_table("assistant_context_snapshots")
    op.drop_table("assistant_messages")
    op.drop_table("assistant_conversations")
    op.drop_table("assistant_sessions")
