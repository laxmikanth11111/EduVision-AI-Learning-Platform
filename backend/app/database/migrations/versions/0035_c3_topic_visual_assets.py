"""C3: add topic_visual_assets table for topic-level visual intelligence.

Revision ID: 0035_c3_topic_visual_assets
Revises: 0034_video_projects
Create Date: 2026-09-06 12:00:00.000000

Checkpoint C3 introduces a Topic-Level Visual Intelligence Engine that generates,
validates, and persists educational visuals associated with specific topics and
subtopics. This migration creates the ``topic_visual_assets`` table matching the
``TopicVisualAsset`` ORM model (``app/models/topic_visual_asset.py``).

Key design decisions:
- Each visual asset carries its full specification as JSONB for re-rendering.
- A deterministic ``fingerprint`` column enables idempotent deduplication.
- ``status`` tracks the lifecycle: planned -> generating -> validating -> ready.
- ``version`` supports superseding old visuals when topics are regenerated.
- ``provenance`` distinguishes source-derived vs AI-explained content.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

from app.database.base import convention

revision = "0035_c3_topic_visual_assets"
down_revision = "0034_video_projects"
branch_labels = None
depends_on = None

TABLE = "topic_visual_assets"


def _table_exists() -> bool:
    bind = op.get_bind()
    if bind is None:
        return True
    return inspect(bind).has_table(TABLE)


def upgrade() -> None:
    if _table_exists():
        return

    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "public_id",
            sa.String(length=40),
            nullable=False,
            server_default=sa.text("('c3v_' || replace(gen_random_uuid()::text, '-', ''))"),
        ),
        sa.Column("presentation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("topic_id", sa.String(length=200), nullable=False),
        sa.Column("topic_title", sa.String(length=500), nullable=False),
        sa.Column("subtopic_id", sa.String(length=200), nullable=True),
        sa.Column("subtopic_title", sa.String(length=500), nullable=True),
        sa.Column("visual_type", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="planned",
        ),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "asset_format",
            sa.String(length=16),
            nullable=False,
            server_default="svg",
        ),
        sa.Column("asset_url", sa.String(length=512), nullable=True),
        sa.Column("asset_key", sa.String(length=512), nullable=True),
        sa.Column("asset_content", sa.Text(), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False, server_default=""),
        sa.Column("learning_objective", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "provenance",
            sa.String(length=32),
            nullable=False,
            server_default="ai_explained",
        ),
        sa.Column(
            "confidence",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0.8"),
        ),
        sa.Column(
            "specification",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "explanation",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "source_references",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "concept_ids",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "generation_metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "retry_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["presentation_id"],
            ["presentations.id"],
            name=convention["fk"]
            % {
                "table_name": TABLE,
                "column_0_name": "presentation_id",
                "referred_table_name": "presentations",
            },
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=convention["fk"]
            % {
                "table_name": TABLE,
                "column_0_name": "user_id",
                "referred_table_name": "users",
            },
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=convention["pk"] % {"table_name": TABLE}),
        sa.CheckConstraint(
            "status IN ('planned', 'specifying', 'generating', 'validating', 'ready', 'failed', 'superseded')",
            name="ck_topic_visual_assets_status",
        ),
        sa.CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_topic_visual_assets_confidence_range",
        ),
    )

    op.create_index(
        "ix_topic_visual_assets_public_id",
        TABLE,
        ["public_id"],
        unique=True,
    )
    op.create_index(
        "ix_topic_visual_assets_user_id",
        TABLE,
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_topic_visual_assets_pres_topic",
        TABLE,
        ["presentation_id", "topic_id"],
        unique=False,
    )
    op.create_index(
        "ix_topic_visual_assets_pres_subtopic",
        TABLE,
        ["presentation_id", "subtopic_id"],
        unique=False,
    )
    op.create_index(
        "ix_topic_visual_assets_fingerprint",
        TABLE,
        ["fingerprint"],
        unique=False,
    )
    op.create_index(
        "ix_topic_visual_assets_status_version",
        TABLE,
        ["status", "version"],
        unique=False,
    )
    op.create_index(
        "ix_topic_visual_assets_visual_type",
        TABLE,
        ["visual_type"],
        unique=False,
    )


def downgrade() -> None:
    if not _table_exists():
        return
    op.drop_index("ix_topic_visual_assets_visual_type", table_name=TABLE)
    op.drop_index("ix_topic_visual_assets_status_version", table_name=TABLE)
    op.drop_index("ix_topic_visual_assets_fingerprint", table_name=TABLE)
    op.drop_index("ix_topic_visual_assets_pres_subtopic", table_name=TABLE)
    op.drop_index("ix_topic_visual_assets_pres_topic", table_name=TABLE)
    op.drop_index("ix_topic_visual_assets_user_id", table_name=TABLE)
    op.drop_index("ix_topic_visual_assets_public_id", table_name=TABLE)
    op.drop_table(TABLE)
