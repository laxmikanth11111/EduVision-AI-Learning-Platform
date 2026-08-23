"""personalized learning & AI learning assistant

Revision ID: 0011_personalized_learning
Revises: 0010_learning_activities
Create Date: 2026-08-04 00:00:00.000000

Adds the Personalized Learning Experience (Phase 4D.5) and AI Learning
Assistant (Phase 4D.6) tables:

* ``learning_paths`` — a personalised sequence of lessons for a student with
  versioned ordering, progress and config.
* ``learning_goals`` — measurable student goals (mastery targets, lesson
  completion, quiz scores, study time, streaks, activity counts) with target
  date and achieved timestamp.
* ``study_plans`` — dated daily plans of learning/review items; the per-day
  structure (items + completion status) lives in the ``days`` JSON so plans
  can be regenerated without losing per-item history.
* ``review_schedules`` — spaced-repetition review items for weak topics with
  the mastery value frozen at scheduling time.
* ``assistant_sessions`` — context-scoped AI assistant workspaces (per
  student/lesson anchor) holding slide/block position and context version.
* ``assistant_conversations`` — soft-deleted conversation threads with the
  anchor (session/lesson/slide/block) and async summary fields.
* ``assistant_messages`` — sanitized user/assistant turns with model, token
  usage, latency, status and a client id for replay protection.
* ``assistant_context_snapshots`` — frozen context blobs a turn was answered
  from, with prompt hash, so conversations remain reproducible.

All child tables cascade from ``users``; conversations cascade from assistant
sessions; messages cascade from conversations. Composite indexes cover the
hot read patterns (per-user status scans, per-user dated plan reads, weak
review queues, per-conversation message streams).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011_personalized_learning"
down_revision = "0010_learning_activities"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learning_paths",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("sequence", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("current_position", sa.Integer(), nullable=False),
        sa.Column("progress_percent", sa.Float(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("context_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_learning_paths_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_learning_paths"),
    )
    op.create_index("ix_learning_paths_public_id", "learning_paths", ["public_id"], unique=True)
    op.create_index("ix_learning_paths_id", "learning_paths", ["id"], unique=False)
    op.create_index("ix_learning_paths_user_id", "learning_paths", ["user_id"], unique=False)
    op.create_index("ix_learning_paths_user_status", "learning_paths", ["user_id", "status"], unique=False)
    op.create_index("ix_learning_paths_status_updated", "learning_paths", ["status", "updated_at"], unique=False)

    op.create_table(
        "learning_goals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("path_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("goal_type", sa.String(length=30), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("target_value", sa.Float(), nullable=True),
        sa.Column("current_value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=20), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("achieved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("progress_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_learning_goals_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["path_id"],
            ["learning_paths.id"],
            name="fk_learning_goals_path_id_learning_paths",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_learning_goals"),
    )
    op.create_index("ix_learning_goals_public_id", "learning_goals", ["public_id"], unique=True)
    op.create_index("ix_learning_goals_id", "learning_goals", ["id"], unique=False)
    op.create_index("ix_learning_goals_user_id", "learning_goals", ["user_id"], unique=False)
    op.create_index("ix_learning_goals_path_id", "learning_goals", ["path_id"], unique=False)
    op.create_index("ix_learning_goals_user_status", "learning_goals", ["user_id", "status"], unique=False)
    op.create_index("ix_learning_goals_user_type", "learning_goals", ["user_id", "goal_type"], unique=False)
    op.create_index("ix_learning_goals_path", "learning_goals", ["path_id", "status"], unique=False)

    op.create_table(
        "study_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("path_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("days", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("days_count", sa.Integer(), nullable=False),
        sa.Column("completed_items", sa.Integer(), nullable=False),
        sa.Column("total_items", sa.Integer(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_study_plans_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["path_id"],
            ["learning_paths.id"],
            name="fk_study_plans_path_id_learning_paths",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_study_plans"),
    )
    op.create_index("ix_study_plans_public_id", "study_plans", ["public_id"], unique=True)
    op.create_index("ix_study_plans_id", "study_plans", ["id"], unique=False)
    op.create_index("ix_study_plans_user_id", "study_plans", ["user_id"], unique=False)
    op.create_index("ix_study_plans_path_id", "study_plans", ["path_id"], unique=False)
    op.create_index("ix_study_plans_user_status", "study_plans", ["user_id", "status"], unique=False)
    op.create_index("ix_study_plans_user_dates", "study_plans", ["user_id", "start_date", "end_date"], unique=False)
    op.create_index("ix_study_plans_path", "study_plans", ["path_id", "status"], unique=False)

    op.create_table(
        "review_schedules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lesson_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("topic", sa.String(length=300), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("scheduled_date", sa.Date(), nullable=False),
        sa.Column("interval_days", sa.Integer(), nullable=False),
        sa.Column("mastery_at_schedule", sa.Float(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_review_schedules_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["generated_lessons.id"],
            name="fk_review_schedules_lesson_id_generated_lessons",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_review_schedules"),
    )
    op.create_index("ix_review_schedules_public_id", "review_schedules", ["public_id"], unique=True)
    op.create_index("ix_review_schedules_id", "review_schedules", ["id"], unique=False)
    op.create_index("ix_review_schedules_user_id", "review_schedules", ["user_id"], unique=False)
    op.create_index("ix_review_schedules_lesson_id", "review_schedules", ["lesson_id"], unique=False)
    op.create_index("ix_review_schedules_scheduled_date", "review_schedules", ["scheduled_date"], unique=False)
    op.create_index("ix_review_schedules_user_status", "review_schedules", ["user_id", "status"], unique=False)
    op.create_index("ix_review_schedules_user_date", "review_schedules", ["user_id", "scheduled_date"], unique=False)
    op.create_index("ix_review_schedules_user_topic", "review_schedules", ["user_id", "topic"], unique=False)

    op.create_table(
        "assistant_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lesson_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("session_public_id", sa.String(length=40), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("slide_position", sa.Integer(), nullable=False),
        sa.Column("block_position", sa.Integer(), nullable=False),
        sa.Column("context_version", sa.String(length=32), nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_assistant_sessions_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["generated_lessons.id"],
            name="fk_assistant_sessions_lesson_id_generated_lessons",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_assistant_sessions"),
    )
    op.create_index("ix_assistant_sessions_public_id", "assistant_sessions", ["public_id"], unique=True)
    op.create_index("ix_assistant_sessions_id", "assistant_sessions", ["id"], unique=False)
    op.create_index("ix_assistant_sessions_user_id", "assistant_sessions", ["user_id"], unique=False)
    op.create_index("ix_assistant_sessions_lesson_id", "assistant_sessions", ["lesson_id"], unique=False)
    op.create_index("ix_assistant_sessions_last_message_at", "assistant_sessions", ["last_message_at"], unique=False)
    op.create_index("ix_assistant_sessions_user_status", "assistant_sessions", ["user_id", "status"], unique=False)
    op.create_index("ix_assistant_sessions_user_updated", "assistant_sessions", ["user_id", "updated_at"], unique=False)
    op.create_index("ix_assistant_sessions_lesson", "assistant_sessions", ["lesson_id", "status"], unique=False)

    op.create_table(
        "assistant_conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lesson_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("session_public_id", sa.String(length=40), nullable=True),
        sa.Column("lesson_public_id", sa.String(length=40), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("slide_position", sa.Integer(), nullable=False),
        sa.Column("block_position", sa.Integer(), nullable=False),
        sa.Column("context_version", sa.String(length=32), nullable=False),
        sa.Column("message_count", sa.Integer(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("summary_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_assistant_conversations_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["assistant_sessions.id"],
            name="fk_assistant_conversations_session_id_assistant_sessions",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["generated_lessons.id"],
            name="fk_assistant_conversations_lesson_id_generated_lessons",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_assistant_conversations"),
    )
    op.create_index("ix_assistant_conversations_public_id", "assistant_conversations", ["public_id"], unique=True)
    op.create_index("ix_assistant_conversations_id", "assistant_conversations", ["id"], unique=False)
    op.create_index("ix_assistant_conversations_user_id", "assistant_conversations", ["user_id"], unique=False)
    op.create_index("ix_assistant_conversations_session_id", "assistant_conversations", ["session_id"], unique=False)
    op.create_index("ix_assistant_conversations_lesson_id", "assistant_conversations", ["lesson_id"], unique=False)
    op.create_index("ix_assistant_conversations_last_message_at", "assistant_conversations", ["last_message_at"], unique=False)
    op.create_index("ix_assistant_conversations_deleted_at", "assistant_conversations", ["deleted_at"], unique=False)
    op.create_index("ix_assistant_conversations_user_status", "assistant_conversations", ["user_id", "status"], unique=False)
    op.create_index("ix_assistant_conversations_user_updated", "assistant_conversations", ["user_id", "updated_at"], unique=False)
    op.create_index("ix_assistant_conversations_session", "assistant_conversations", ["session_id", "status"], unique=False)
    op.create_index("ix_assistant_conversations_lesson", "assistant_conversations", ["lesson_id", "status"], unique=False)

    op.create_table(
        "assistant_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("client_message_id", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("provider", sa.String(length=40), nullable=True),
        sa.Column("tokens_in", sa.Integer(), nullable=False),
        sa.Column("tokens_out", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column("message_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["assistant_conversations.id"],
            name="fk_assistant_messages_conversation_id_assistant_conversations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_assistant_messages_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_assistant_messages"),
    )
    op.create_index("ix_assistant_messages_public_id", "assistant_messages", ["public_id"], unique=True)
    op.create_index("ix_assistant_messages_id", "assistant_messages", ["id"], unique=False)
    op.create_index("ix_assistant_messages_conversation_id", "assistant_messages", ["conversation_id"], unique=False)
    op.create_index("ix_assistant_messages_user_id", "assistant_messages", ["user_id"], unique=False)
    op.create_index("ix_assistant_messages_conversation_created", "assistant_messages", ["conversation_id", "created_at"], unique=False)
    op.create_index("ix_assistant_messages_user_created", "assistant_messages", ["user_id", "created_at"], unique=False)
    op.create_index("ix_assistant_messages_client_id", "assistant_messages", ["conversation_id", "client_message_id"], unique=False)

    op.create_table(
        "assistant_context_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lesson_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lesson_public_id", sa.String(length=40), nullable=True),
        sa.Column("session_public_id", sa.String(length=40), nullable=True),
        sa.Column("slide_position", sa.Integer(), nullable=False),
        sa.Column("block_position", sa.Integer(), nullable=False),
        sa.Column("context_version", sa.String(length=32), nullable=False),
        sa.Column("prompt_hash", sa.String(length=64), nullable=True),
        sa.Column("context", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_assistant_context_snapshots_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["assistant_conversations.id"],
            name="fk_ac_snapshots_conversation_id_assistant_convs",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["generated_lessons.id"],
            name="fk_assistant_context_snapshots_lesson_id_generated_lessons",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_assistant_context_snapshots"),
    )
    op.create_index("ix_assistant_context_snapshots_public_id", "assistant_context_snapshots", ["public_id"], unique=True)
    op.create_index("ix_assistant_context_snapshots_id", "assistant_context_snapshots", ["id"], unique=False)
    op.create_index("ix_assistant_context_snapshots_user_id", "assistant_context_snapshots", ["user_id"], unique=False)
    op.create_index("ix_assistant_context_snapshots_conversation_id", "assistant_context_snapshots", ["conversation_id"], unique=False)
    op.create_index("ix_assistant_context_snapshots_lesson_id", "assistant_context_snapshots", ["lesson_id"], unique=False)
    op.create_index("ix_assistant_context_snapshots_user_created", "assistant_context_snapshots", ["user_id", "created_at"], unique=False)
    op.create_index("ix_assistant_context_snapshots_conversation", "assistant_context_snapshots", ["conversation_id", "created_at"], unique=False)
    op.create_index("ix_assistant_context_snapshots_lesson", "assistant_context_snapshots", ["lesson_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_table("assistant_context_snapshots")
    op.drop_table("assistant_messages")
    op.drop_table("assistant_conversations")
    op.drop_table("assistant_sessions")
    op.drop_table("review_schedules")
    op.drop_table("study_plans")
    op.drop_table("learning_goals")
    op.drop_table("learning_paths")
