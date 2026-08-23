"""learning sessions

Revision ID: 0009_learning_sessions
Revises: 0008_quiz_performance_indexes
Create Date: 2026-08-03 00:00:00.000000

Adds the Interactive Learning foundation tables (Phase 4D.1 + 4D.2):

* ``learning_sessions`` — per-student session state machine (created/started/
  active/paused/completed/expired/cancelled), resume location, idempotency,
  cross-device resume versioning.
* ``learning_progress`` — per-user, per-lesson durable progress aggregate.
* ``slide_progress`` / ``block_progress`` — fine-grained per-session completion.
* ``bookmarks`` / ``student_notes`` — soft-deleted student annotations.
* ``learning_events`` — append-only event stream consumed by rollup workers.
* ``session_analytics`` — per-session behavioural metrics (idle, velocity, ...).
* ``session_statistics`` — periodic rollups for analytics surfaces.

All child tables cascade from ``learning_sessions`` / ``users`` so deleting a
session or user never orphans progress rows. Composite indexes cover the hot
query patterns (status scans for the cleanup worker, per-user/per-lesson
progress reads, event-stream scans for the rollup workers).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009_learning_sessions"
down_revision = "0008_quiz_performance_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learning_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lesson_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lesson_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("device_id", sa.String(length=128), nullable=True),
        sa.Column("time_limit_minutes", sa.Integer(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_slide_position", sa.Integer(), nullable=False),
        sa.Column("current_block_position", sa.Integer(), nullable=False),
        sa.Column("current_section", sa.String(length=200), nullable=True),
        sa.Column("current_block_type", sa.String(length=30), nullable=True),
        sa.Column("completion_percentage", sa.Float(), nullable=False),
        sa.Column("total_time_seconds", sa.Integer(), nullable=False),
        sa.Column("resume_version", sa.Integer(), nullable=False),
        sa.Column("client_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_learning_sessions_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["generated_lessons.id"],
            name="fk_learning_sessions_lesson_id_generated_lessons",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["lesson_version_id"],
            ["generated_lesson_versions.id"],
            name="fk_lsessions_lversion_id_gen_lversions",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_learning_sessions"),
        sa.UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_learning_sessions_user_idempotency",
        ),
    )
    op.create_index("ix_learning_sessions_public_id", "learning_sessions", ["public_id"], unique=True)
    op.create_index("ix_learning_sessions_id", "learning_sessions", ["id"], unique=False)
    op.create_index("ix_learning_sessions_user_id", "learning_sessions", ["user_id"], unique=False)
    op.create_index("ix_learning_sessions_lesson_id", "learning_sessions", ["lesson_id"], unique=False)
    op.create_index("ix_learning_sessions_lesson_version_id", "learning_sessions", ["lesson_version_id"], unique=False)
    op.create_index("ix_learning_sessions_expires_at", "learning_sessions", ["expires_at"], unique=False)
    op.create_index("ix_learning_sessions_last_activity_at", "learning_sessions", ["last_activity_at"], unique=False)
    op.create_index("ix_learning_sessions_user_status", "learning_sessions", ["user_id", "status"], unique=False)
    op.create_index("ix_learning_sessions_lesson_status", "learning_sessions", ["lesson_id", "status"], unique=False)
    op.create_index("ix_learning_sessions_status_updated", "learning_sessions", ["status", "updated_at"], unique=False)

    op.create_table(
        "learning_progress",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lesson_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("current_slide_position", sa.Integer(), nullable=False),
        sa.Column("current_block_position", sa.Integer(), nullable=False),
        sa.Column("current_section", sa.String(length=200), nullable=True),
        sa.Column("current_block_type", sa.String(length=30), nullable=True),
        sa.Column("completed_slides", sa.Integer(), nullable=False),
        sa.Column("completed_blocks", sa.Integer(), nullable=False),
        sa.Column("completed_activities", sa.Integer(), nullable=False),
        sa.Column("completed_quizzes", sa.Integer(), nullable=False),
        sa.Column("total_slides", sa.Integer(), nullable=False),
        sa.Column("total_blocks", sa.Integer(), nullable=False),
        sa.Column("total_activities", sa.Integer(), nullable=False),
        sa.Column("total_quizzes", sa.Integer(), nullable=False),
        sa.Column("reading_completion_percent", sa.Float(), nullable=False),
        sa.Column("practice_completion_percent", sa.Float(), nullable=False),
        sa.Column("quiz_completion_percent", sa.Float(), nullable=False),
        sa.Column("overall_completion_percent", sa.Float(), nullable=False),
        sa.Column("time_spent_seconds", sa.Integer(), nullable=False),
        sa.Column("resume_version", sa.Integer(), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_learning_progress_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["generated_lessons.id"],
            name="fk_learning_progress_lesson_id_generated_lessons",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["learning_sessions.id"],
            name="fk_learning_progress_session_id_learning_sessions",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_learning_progress"),
        sa.UniqueConstraint(
            "user_id",
            "lesson_id",
            name="uq_learning_progress_user_lesson",
        ),
    )
    op.create_index("ix_learning_progress_public_id", "learning_progress", ["public_id"], unique=True)
    op.create_index("ix_learning_progress_id", "learning_progress", ["id"], unique=False)
    op.create_index("ix_learning_progress_user_id", "learning_progress", ["user_id"], unique=False)
    op.create_index("ix_learning_progress_lesson_id", "learning_progress", ["lesson_id"], unique=False)
    op.create_index("ix_learning_progress_last_activity_at", "learning_progress", ["last_activity_at"], unique=False)
    op.create_index("ix_learning_progress_user_status", "learning_progress", ["user_id", "status"], unique=False)
    op.create_index("ix_learning_progress_lesson_status", "learning_progress", ["lesson_id", "status"], unique=False)

    op.create_table(
        "slide_progress",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lesson_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slide_index", sa.Integer(), nullable=False),
        sa.Column("slide_title", sa.String(length=500), nullable=True),
        sa.Column("section", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("time_spent_seconds", sa.Integer(), nullable=False),
        sa.Column("activities_completed", sa.Integer(), nullable=False),
        sa.Column("quizzes_completed", sa.Integer(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["learning_sessions.id"],
            name="fk_slide_progress_session_id_learning_sessions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_slide_progress_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["generated_lessons.id"],
            name="fk_slide_progress_lesson_id_generated_lessons",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_slide_progress"),
        sa.UniqueConstraint(
            "session_id",
            "slide_index",
            name="uq_slide_progress_session_index",
        ),
    )
    op.create_index("ix_slide_progress_public_id", "slide_progress", ["public_id"], unique=True)
    op.create_index("ix_slide_progress_id", "slide_progress", ["id"], unique=False)
    op.create_index("ix_slide_progress_session_id", "slide_progress", ["session_id"], unique=False)
    op.create_index("ix_slide_progress_user_id", "slide_progress", ["user_id"], unique=False)
    op.create_index("ix_slide_progress_lesson_id", "slide_progress", ["lesson_id"], unique=False)
    op.create_index("ix_slide_progress_user_lesson", "slide_progress", ["user_id", "lesson_id", "slide_index"], unique=False)

    op.create_table(
        "block_progress",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lesson_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("block_position", sa.Integer(), nullable=False),
        sa.Column("block_type", sa.String(length=30), nullable=True),
        sa.Column("section", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("completion_kind", sa.String(length=20), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("time_spent_seconds", sa.Integer(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["learning_sessions.id"],
            name="fk_block_progress_session_id_learning_sessions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_block_progress_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["generated_lessons.id"],
            name="fk_block_progress_lesson_id_generated_lessons",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_block_progress"),
        sa.UniqueConstraint(
            "session_id",
            "block_position",
            name="uq_block_progress_session_position",
        ),
    )
    op.create_index("ix_block_progress_public_id", "block_progress", ["public_id"], unique=True)
    op.create_index("ix_block_progress_id", "block_progress", ["id"], unique=False)
    op.create_index("ix_block_progress_session_id", "block_progress", ["session_id"], unique=False)
    op.create_index("ix_block_progress_user_id", "block_progress", ["user_id"], unique=False)
    op.create_index("ix_block_progress_lesson_id", "block_progress", ["lesson_id"], unique=False)
    op.create_index("ix_block_progress_user_lesson", "block_progress", ["user_id", "lesson_id", "block_position"], unique=False)

    op.create_table(
        "bookmarks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lesson_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_type", sa.String(length=20), nullable=False),
        sa.Column("target_position", sa.Integer(), nullable=True),
        sa.Column("target_ref", sa.String(length=200), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("label", sa.String(length=100), nullable=True),
        sa.Column("notes", sa.String(length=2000), nullable=True),
        sa.Column("is_pinned", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_bookmarks_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["generated_lessons.id"],
            name="fk_bookmarks_lesson_id_generated_lessons",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["learning_sessions.id"],
            name="fk_bookmarks_session_id_learning_sessions",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_bookmarks"),
        sa.UniqueConstraint(
            "user_id",
            "lesson_id",
            "target_type",
            "target_position",
            "target_ref",
            name="uq_bookmarks_user_lesson_target",
        ),
    )
    op.create_index("ix_bookmarks_public_id", "bookmarks", ["public_id"], unique=True)
    op.create_index("ix_bookmarks_id", "bookmarks", ["id"], unique=False)
    op.create_index("ix_bookmarks_user_id", "bookmarks", ["user_id"], unique=False)
    op.create_index("ix_bookmarks_lesson_id", "bookmarks", ["lesson_id"], unique=False)
    op.create_index("ix_bookmarks_session_id", "bookmarks", ["session_id"], unique=False)
    op.create_index("ix_bookmarks_deleted_at", "bookmarks", ["deleted_at"], unique=False)
    op.create_index("ix_bookmarks_user_lesson", "bookmarks", ["user_id", "lesson_id", "target_type"], unique=False)
    op.create_index("ix_bookmarks_user_pinned", "bookmarks", ["user_id", "is_pinned"], unique=False)

    op.create_table(
        "student_notes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lesson_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_type", sa.String(length=20), nullable=False),
        sa.Column("target_position", sa.Integer(), nullable=True),
        sa.Column("target_ref", sa.String(length=200), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("is_pinned", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_sanitized", sa.Boolean(), nullable=False),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_student_notes_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["generated_lessons.id"],
            name="fk_student_notes_lesson_id_generated_lessons",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["learning_sessions.id"],
            name="fk_student_notes_session_id_learning_sessions",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_student_notes"),
    )
    op.create_index("ix_student_notes_public_id", "student_notes", ["public_id"], unique=True)
    op.create_index("ix_student_notes_id", "student_notes", ["id"], unique=False)
    op.create_index("ix_student_notes_user_id", "student_notes", ["user_id"], unique=False)
    op.create_index("ix_student_notes_lesson_id", "student_notes", ["lesson_id"], unique=False)
    op.create_index("ix_student_notes_session_id", "student_notes", ["session_id"], unique=False)
    op.create_index("ix_student_notes_deleted_at", "student_notes", ["deleted_at"], unique=False)
    op.create_index("ix_student_notes_user_lesson", "student_notes", ["user_id", "lesson_id", "target_type"], unique=False)
    op.create_index("ix_student_notes_user_updated", "student_notes", ["user_id", "updated_at"], unique=False)
    op.create_index("ix_student_notes_user_pinned", "student_notes", ["user_id", "is_pinned"], unique=False)

    op.create_table(
        "learning_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lesson_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("slide_position", sa.Integer(), nullable=True),
        sa.Column("block_position", sa.Integer(), nullable=True),
        sa.Column("section", sa.String(length=200), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_learning_events_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["learning_sessions.id"],
            name="fk_learning_events_session_id_learning_sessions",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["generated_lessons.id"],
            name="fk_learning_events_lesson_id_generated_lessons",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_learning_events"),
    )
    op.create_index("ix_learning_events_public_id", "learning_events", ["public_id"], unique=True)
    op.create_index("ix_learning_events_id", "learning_events", ["id"], unique=False)
    op.create_index("ix_learning_events_user_id", "learning_events", ["user_id"], unique=False)
    op.create_index("ix_learning_events_session_id", "learning_events", ["session_id"], unique=False)
    op.create_index("ix_learning_events_lesson_id", "learning_events", ["lesson_id"], unique=False)
    op.create_index("ix_learning_events_session_created", "learning_events", ["session_id", "created_at"], unique=False)
    op.create_index("ix_learning_events_user_type", "learning_events", ["user_id", "event_type", "created_at"], unique=False)
    op.create_index("ix_learning_events_user_lesson", "learning_events", ["user_id", "lesson_id", "created_at"], unique=False)

    op.create_table(
        "session_analytics",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lesson_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("total_time_seconds", sa.Integer(), nullable=False),
        sa.Column("slides_viewed", sa.Integer(), nullable=False),
        sa.Column("blocks_completed", sa.Integer(), nullable=False),
        sa.Column("activities_completed", sa.Integer(), nullable=False),
        sa.Column("quizzes_completed", sa.Integer(), nullable=False),
        sa.Column("questions_answered", sa.Integer(), nullable=False),
        sa.Column("correct_answers", sa.Integer(), nullable=False),
        sa.Column("avg_time_per_block_seconds", sa.Float(), nullable=False),
        sa.Column("avg_time_per_slide_seconds", sa.Float(), nullable=False),
        sa.Column("learning_velocity", sa.Float(), nullable=False),
        sa.Column("idle_seconds", sa.Integer(), nullable=False),
        sa.Column("distraction_events", sa.Integer(), nullable=False),
        sa.Column("completion_percentage", sa.Float(), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["learning_sessions.id"],
            name="fk_session_analytics_session_id_learning_sessions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_session_analytics_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["generated_lessons.id"],
            name="fk_session_analytics_lesson_id_generated_lessons",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_session_analytics"),
        sa.UniqueConstraint(
            "session_id",
            name="uq_session_analytics_session_id",
        ),
    )
    op.create_index("ix_session_analytics_public_id", "session_analytics", ["public_id"], unique=True)
    op.create_index("ix_session_analytics_id", "session_analytics", ["id"], unique=False)
    op.create_index("ix_session_analytics_session_id", "session_analytics", ["session_id"], unique=True)
    op.create_index("ix_session_analytics_user_id", "session_analytics", ["user_id"], unique=False)
    op.create_index("ix_session_analytics_lesson_id", "session_analytics", ["lesson_id"], unique=False)
    op.create_index("ix_session_analytics_user", "session_analytics", ["user_id", "lesson_id"], unique=False)

    op.create_table(
        "session_statistics",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lesson_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("period", sa.String(length=10), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sessions_count", sa.Integer(), nullable=False),
        sa.Column("total_time_seconds", sa.Integer(), nullable=False),
        sa.Column("slides_completed", sa.Integer(), nullable=False),
        sa.Column("blocks_completed", sa.Integer(), nullable=False),
        sa.Column("activities_completed", sa.Integer(), nullable=False),
        sa.Column("quizzes_completed", sa.Integer(), nullable=False),
        sa.Column("avg_completion_percent", sa.Float(), nullable=False),
        sa.Column("stats", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_session_statistics_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["generated_lessons.id"],
            name="fk_session_statistics_lesson_id_generated_lessons",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["learning_sessions.id"],
            name="fk_session_statistics_session_id_learning_sessions",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_session_statistics"),
        sa.UniqueConstraint(
            "user_id",
            "period",
            "period_start",
            name="uq_session_statistics_user_period",
        ),
    )
    op.create_index("ix_session_statistics_public_id", "session_statistics", ["public_id"], unique=True)
    op.create_index("ix_session_statistics_id", "session_statistics", ["id"], unique=False)
    op.create_index("ix_session_statistics_user_id", "session_statistics", ["user_id"], unique=False)
    op.create_index("ix_session_statistics_lesson_id", "session_statistics", ["lesson_id"], unique=False)
    op.create_index("ix_session_statistics_user_period", "session_statistics", ["user_id", "period"], unique=False)


def downgrade() -> None:
    op.drop_table("session_statistics")
    op.drop_table("session_analytics")
    op.drop_table("learning_events")
    op.drop_table("student_notes")
    op.drop_table("bookmarks")
    op.drop_table("block_progress")
    op.drop_table("slide_progress")
    op.drop_table("learning_progress")
    op.drop_table("learning_sessions")
