"""P16: add learner-owned video_projects table.

Revision ID: 0034_video_projects
Revises: 0033_educational_memories
Create Date: 2026-09-06 00:00:00.000000

P16 introduces an asynchronous, persistent video rendering runtime. The
previous video project lifecycle lived only in an in-process ``BoundedCache``
(with a fabricated-project fallback on cache miss), so renders were blocking
inside request handlers, never durable, and owned only by fiat of that cache.

This additive migration creates the ``video_projects`` table exactly matching
the ``VideoProjectRecord`` ORM model (``app/models/video_project.py``): a
learner-owned row (``user_id`` FK CASCADE) carrying the stable engine
``video_id``, the coarse render lifecycle ``status``, ``progress_percentage``,
the terminal ``playable_url``/``error``, and the deterministic blueprint JSON.
It is idempotent-friendly via a table-existence guard and does not rewrite any
historical migration.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

from app.database.base import convention

revision = "0034_video_projects"
down_revision = "0033_educational_memories"
branch_labels = None
depends_on = None

TABLE = "video_projects"


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
            server_default=sa.text(
                "('vproj_' || replace(gen_random_uuid()::text, '-', ''))"
            ),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("video_id", sa.String(length=64), nullable=False),
        sa.Column("topic", sa.String(length=300), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("progress_percentage", sa.Float(), nullable=False),
        sa.Column("playable_url", sa.String(length=500), nullable=True),
        sa.Column("error", sa.String(length=1000), nullable=True),
        sa.Column("project_data", postgresql.JSONB(), nullable=True),
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
            "status IN ('queued', 'rendering', 'ready', 'failed')",
            name="ck_video_projects_status",
        ),
        sa.CheckConstraint(
            "progress_percentage >= 0.0 AND progress_percentage <= 100.0",
            name="ck_video_projects_progress_range",
        ),
    )
    op.create_index("ix_video_projects_public_id", TABLE, ["public_id"], unique=True)
    op.create_index("ix_video_projects_user_id", TABLE, ["user_id"], unique=False)
    op.create_index("ix_video_projects_id", TABLE, ["id"], unique=False)
    op.create_index("ix_video_projects_user_status", TABLE, ["user_id", "status"], unique=False)


def downgrade() -> None:
    if not _table_exists():
        return
    op.drop_index("ix_video_projects_user_status", table_name=TABLE)
    op.drop_index("ix_video_projects_user_id", table_name=TABLE)
    op.drop_index("ix_video_projects_public_id", table_name=TABLE)
    op.drop_index("ix_video_projects_id", table_name=TABLE)
    op.drop_table(TABLE)
