"""Google OAuth Support & Nullable Password Hash

Revision ID: 0017_google_oauth
Revises: 0016_visual_knowledge_graph
Create Date: 2026-08-11 00:00:00.000000

Adds google_id column to users table and alters password_hash to be nullable.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017_google_oauth"
down_revision = "0016_visual_knowledge_graph"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("google_id", sa.String(255), nullable=True))
    op.create_index("ix_users_google_id", "users", ["google_id"], unique=True)
    op.alter_column("users", "password_hash", existing_type=sa.String(255), nullable=True)


def downgrade() -> None:
    op.drop_index("ix_users_google_id", table_name="users")
    op.drop_column("users", "google_id")
    op.alter_column("users", "password_hash", existing_type=sa.String(255), nullable=False)
