"""Create users table for authentication.

Revision ID: 0020_create_users
Revises: 0019_nullable_owner_user
Create Date: 2026-08-17 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0020_create_users"
down_revision = "0019_nullable_owner_user"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "users" not in inspector.get_table_names():
        op.create_table(
            "users",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("email", sa.String(320), nullable=False),
            sa.Column("password_hash", sa.String(255), nullable=True),
            sa.Column("google_id", sa.String(255), nullable=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_users_email", "users", ["email"], unique=True)
        op.create_index("ix_users_google_id", "users", ["google_id"], unique=True)
    else:
        expected = {"id", "email", "password_hash", "google_id", "name", "created_at", "updated_at"}
        existing = {c["name"] for c in inspector.get_columns("users")}
        stale = existing - expected
        for col_name in sorted(stale):
            op.drop_column("users", col_name)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "users" in inspector.get_table_names():
        op.drop_index("ix_users_google_id", table_name="users")
        op.drop_index("ix_users_email", table_name="users")
        op.drop_table("users")
