"""Topic Outlines

Revision ID: 0018_topic_outlines
Revises: 0017_google_oauth
Create Date: 2026-08-16 00:00:00.000000

Adds the ``topic_outlines`` table storing the LLM-produced structured outline
(``{title, topics: [{title, slide_ranges}]}``) per presentation.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0018_topic_outlines"
down_revision = "0017_google_oauth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "topic_outlines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "public_id",
            sa.String(40),
            nullable=False,
        ),
        sa.Column(
            "presentation_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("topics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("provider", sa.String(100), nullable=True),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("request_id", sa.String(100), nullable=True),
        sa.Column("correlation_id", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["presentation_id"],
            ["presentations.id"],
            name="fk_topic_outlines_presentation_id_presentations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_topic_outlines"),
    )
    op.create_index(
        "ix_topic_outlines_id", "topic_outlines", ["id"], unique=False
    )
    op.create_index(
        "ix_topic_outlines_public_id",
        "topic_outlines",
        ["public_id"],
        unique=True,
    )
    op.create_index(
        "ix_topic_outlines_presentation_id",
        "topic_outlines",
        ["presentation_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_topic_outlines_presentation_id", table_name="topic_outlines")
    op.drop_index("ix_topic_outlines_public_id", table_name="topic_outlines")
    op.drop_index("ix_topic_outlines_id", table_name="topic_outlines")
    op.drop_table("topic_outlines")
