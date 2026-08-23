"""Make owner_id / user_id nullable (auth removed)

Revision ID: 0019_nullable_owner_user
Revises: 0018_topic_outlines
Create Date: 2026-08-17 00:00:00.000000

After removing the User model and auth system, ``owner_id`` on
``presentations`` and ``presentation_folders``, and ``user_id`` on
``visual_canvases`` are no longer required.  This migration flips
them to ``nullable=True``.
"""

from __future__ import annotations

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0019_nullable_owner_user"
down_revision = "0018_topic_outlines"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # presentations.owner_id
    op.alter_column(
        "presentations",
        "owner_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )
    # presentation_folders.owner_id
    op.alter_column(
        "presentation_folders",
        "owner_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )
    # visual_canvases.user_id
    op.alter_column(
        "visual_canvases",
        "user_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "visual_canvases",
        "user_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.alter_column(
        "presentation_folders",
        "owner_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.alter_column(
        "presentations",
        "owner_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
