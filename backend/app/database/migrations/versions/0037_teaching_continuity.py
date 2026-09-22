"""Teaching continuity: mode-aware session completion + annotation layers.

Revision ID: 0037_teaching_continuity
Revises: 0036_c4_topic_animation_assets
Create Date: 2026-09-22 12:00:00.000000

Teaching-continuity milestone:
1. ``learning_sessions.player_mode`` — the slide-deck representation a saved
   position belongs to (``'source'`` counts against the uploaded deck,
   ``'learning'`` against the AI concept/visual pair deck). The position is
   relative to this mode, so resuming restores exactly the slide (and view) the
   learner was on, and source-mode completion can reach 100% instead of capping
   at ~50%. Existing rows are backfilled to ``learning`` (their slide indices
   were learning-relative), so no historical position is reinterpreted.
2. ``lesson_annotations`` — per-slide annotation layers keyed by
   ``(user_id, lesson_id, player_mode, slide_index)``. Each row stores one
   slide's overlay marks (strokes/shapes/text) as validated JSON. These live in
   a normalized table rather than the legacy ``bookmarks``/``student_notes``
   tables (migration 0009), which store learner notes and are not layered.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

from app.database.base import convention

revision = "0037_teaching_continuity"
down_revision = "0036_c4_topic_animation_assets"
branch_labels = None
depends_on = None

SESSIONS_TABLE = "learning_sessions"
ANNOTATIONS_TABLE = "lesson_annotations"


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    if bind is None:
        return True
    return column in {c["name"] for c in inspect(bind).get_columns(table)}


def _table_exists(table: str) -> bool:
    bind = op.get_bind()
    if bind is None:
        return True
    return inspect(bind).has_table(table)


def upgrade() -> None:
    # 1. Mode-aware sessions.
    if _table_exists(SESSIONS_TABLE) and not _column_exists(SESSIONS_TABLE, "player_mode"):
        op.add_column(
            SESSIONS_TABLE,
            sa.Column(
                "player_mode",
                sa.String(length=16),
                nullable=False,
                server_default="learning",
            ),
        )
        op.create_check_constraint(
            "ck_learning_sessions_player_mode",
            SESSIONS_TABLE,
            "player_mode IN ('source', 'learning')",
        )

    # 2. Annotation layers.
    if _table_exists(ANNOTATIONS_TABLE):
        return

    op.create_table(
        ANNOTATIONS_TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "public_id",
            sa.String(length=40),
            nullable=False,
            server_default=sa.text(
                "('pann_' || replace(gen_random_uuid()::text, '-', ''))"
            ),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lesson_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("player_mode", sa.String(length=16), nullable=False),
        sa.Column("slide_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "items",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
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
            ["lesson_id"],
            ["generated_lessons.id"],
            name=convention["fk"]
            % {
                "table_name": ANNOTATIONS_TABLE,
                "column_0_name": "lesson_id",
                "referred_table_name": "generated_lessons",
            },
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=convention["pk"] % {"table_name": ANNOTATIONS_TABLE}),
        sa.UniqueConstraint(
            "user_id",
            "lesson_id",
            "player_mode",
            "slide_index",
            name="uq_lesson_annotations_layer",
        ),
        sa.CheckConstraint(
            "player_mode IN ('source', 'learning', 'visual', 'animation')",
            name="ck_lesson_annotations_player_mode",
        ),
        sa.CheckConstraint(
            "slide_index >= 0",
            name="ck_lesson_annotations_slide_index",
        ),
    )

    op.create_index(
        "ix_lesson_annotations_public_id",
        ANNOTATIONS_TABLE,
        ["public_id"],
        unique=True,
    )
    op.create_index(
        "ix_lesson_annotations_user_id",
        ANNOTATIONS_TABLE,
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_lesson_annotations_lesson_id",
        ANNOTATIONS_TABLE,
        ["lesson_id"],
        unique=False,
    )
    op.create_index(
        "ix_lesson_annotations_player_mode",
        ANNOTATIONS_TABLE,
        ["player_mode"],
        unique=False,
    )
    op.create_index(
        "ix_lesson_annotations_layer_scan",
        ANNOTATIONS_TABLE,
        ["user_id", "lesson_id", "player_mode"],
        unique=False,
    )


def downgrade() -> None:
    if _table_exists(ANNOTATIONS_TABLE):
        op.drop_index("ix_lesson_annotations_layer_scan", table_name=ANNOTATIONS_TABLE)
        op.drop_index("ix_lesson_annotations_player_mode", table_name=ANNOTATIONS_TABLE)
        op.drop_index("ix_lesson_annotations_lesson_id", table_name=ANNOTATIONS_TABLE)
        op.drop_index("ix_lesson_annotations_user_id", table_name=ANNOTATIONS_TABLE)
        op.drop_index("ix_lesson_annotations_public_id", table_name=ANNOTATIONS_TABLE)
        op.drop_table(ANNOTATIONS_TABLE)

    if _table_exists(SESSIONS_TABLE) and _column_exists(SESSIONS_TABLE, "player_mode"):
        op.drop_constraint(
            "ck_learning_sessions_player_mode",
            SESSIONS_TABLE,
            type_="check",
        )
        op.drop_column(SESSIONS_TABLE, "player_mode")
