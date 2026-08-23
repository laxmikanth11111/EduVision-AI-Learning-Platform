"""learning activities & progress engine

Revision ID: 0010_learning_activities
Revises: 0009_learning_sessions
Create Date: 2026-08-03 00:00:00.000000

Adds the Interactive Learning Activities and Learning Progress Engine tables
(Phase 4D.3 + 4D.4):

* ``learning_activities`` — interactive activity definitions bound to a lesson
  (and optional lesson version) at a block/slide position, carrying the config
  the attempt evaluator consumes (options, accepted answers, matching pairs,
  ordering, rubric) plus the tags that feed the adaptive engine.
* ``activity_attempts`` — per-user attempts with the evaluator verdict,
  self-reported confidence and the signals the adaptive engine reads
  (needs-more-explanation, marked-difficult, difficulty feedback).
* ``activity_feedback`` — explicit ratings, difficulty feedback and comments.
* ``learning_milestones`` — one row per (user, milestone_type, scope_key) that
  accumulates progress toward a target and flips ``achieved`` when reached;
  ``scope_key`` is ``""`` for global milestones or ``lesson:<public_id>`` for
  per-lesson ones so a milestone type can be re-earned per lesson.
* ``activity_recommendations`` — personalised in-lesson practice queues built
  from weak attempt outcomes.

All rows cascade from ``users`` (and their owning lessons/activities/sessions)
so deleting a user, lesson, activity or session never orphans state. Composite
indexes cover the hot read patterns (user status scans, per-lesson activity
lists, per-user milestone/recommendation queries).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010_learning_activities"
down_revision = "0009_learning_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learning_activities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("lesson_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lesson_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("block_position", sa.Integer(), nullable=False),
        sa.Column("slide_position", sa.Integer(), nullable=False),
        sa.Column("section", sa.String(length=200), nullable=True),
        sa.Column("activity_type", sa.String(length=30), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("difficulty", sa.String(length=20), nullable=False),
        sa.Column("bloom_level", sa.String(length=20), nullable=True),
        sa.Column("topics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("concepts", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("learning_objectives", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("estimated_duration_seconds", sa.Integer(), nullable=False),
        sa.Column("scoring_model", sa.String(length=30), nullable=False),
        sa.Column("is_optional", sa.Boolean(), nullable=False),
        sa.Column("requires_explanation", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["generated_lessons.id"],
            name="fk_learning_activities_lesson_id_generated_lessons",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["lesson_version_id"],
            ["generated_lesson_versions.id"],
            name="fk_lactivities_lversion_id_gen_lversions",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_learning_activities"),
    )
    op.create_index("ix_learning_activities_public_id", "learning_activities", ["public_id"], unique=True)
    op.create_index("ix_learning_activities_id", "learning_activities", ["id"], unique=False)
    op.create_index("ix_learning_activities_lesson_id", "learning_activities", ["lesson_id"], unique=False)
    op.create_index("ix_learning_activities_lesson_version_id", "learning_activities", ["lesson_version_id"], unique=False)
    op.create_index("ix_learning_activities_lesson_type", "learning_activities", ["lesson_id", "activity_type"], unique=False)
    op.create_index("ix_learning_activities_version_position", "learning_activities", ["lesson_version_id", "block_position"], unique=False)

    op.create_table(
        "activity_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("activity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lesson_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lesson_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=True),
        sa.Column("is_correct", sa.Boolean(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("answer", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("response_meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("time_spent_seconds", sa.Integer(), nullable=False),
        sa.Column("confidence_level", sa.Integer(), nullable=True),
        sa.Column("difficulty_feedback", sa.String(length=20), nullable=True),
        sa.Column("needs_more_explanation", sa.Boolean(), nullable=False),
        sa.Column("marked_difficult", sa.Boolean(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_activity_attempts_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["activity_id"],
            ["learning_activities.id"],
            name="fk_activity_attempts_activity_id_learning_activities",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["generated_lessons.id"],
            name="fk_activity_attempts_lesson_id_generated_lessons",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["lesson_version_id"],
            ["generated_lesson_versions.id"],
            name="fk_aattempts_lversion_id_gen_lversions",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["learning_sessions.id"],
            name="fk_activity_attempts_session_id_learning_sessions",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_activity_attempts"),
        sa.UniqueConstraint(
            "user_id",
            "activity_id",
            "attempt_number",
            name="uq_activity_attempts_user_activity_number",
        ),
    )
    op.create_index("ix_activity_attempts_public_id", "activity_attempts", ["public_id"], unique=True)
    op.create_index("ix_activity_attempts_id", "activity_attempts", ["id"], unique=False)
    op.create_index("ix_activity_attempts_user_id", "activity_attempts", ["user_id"], unique=False)
    op.create_index("ix_activity_attempts_activity_id", "activity_attempts", ["activity_id"], unique=False)
    op.create_index("ix_activity_attempts_lesson_id", "activity_attempts", ["lesson_id"], unique=False)
    op.create_index("ix_activity_attempts_session_id", "activity_attempts", ["session_id"], unique=False)
    op.create_index("ix_activity_attempts_user_status", "activity_attempts", ["user_id", "status"], unique=False)
    op.create_index("ix_activity_attempts_user_lesson", "activity_attempts", ["user_id", "lesson_id", "updated_at"], unique=False)

    op.create_table(
        "activity_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("activity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("feedback_type", sa.String(length=30), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("difficulty_rating", sa.String(length=20), nullable=True),
        sa.Column("needs_more_explanation", sa.Boolean(), nullable=False),
        sa.Column("helpful", sa.Boolean(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_activity_feedback_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["activity_id"],
            ["learning_activities.id"],
            name="fk_activity_feedback_activity_id_learning_activities",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["activity_attempts.id"],
            name="fk_activity_feedback_attempt_id_activity_attempts",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["learning_sessions.id"],
            name="fk_activity_feedback_session_id_learning_sessions",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_activity_feedback"),
    )
    op.create_index("ix_activity_feedback_public_id", "activity_feedback", ["public_id"], unique=True)
    op.create_index("ix_activity_feedback_id", "activity_feedback", ["id"], unique=False)
    op.create_index("ix_activity_feedback_user_id", "activity_feedback", ["user_id"], unique=False)
    op.create_index("ix_activity_feedback_activity_id", "activity_feedback", ["activity_id"], unique=False)
    op.create_index("ix_activity_feedback_user_activity", "activity_feedback", ["user_id", "activity_id", "created_at"], unique=False)

    op.create_table(
        "learning_milestones",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("milestone_type", sa.String(length=40), nullable=False),
        sa.Column("scope_key", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("lesson_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("activity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("progress", sa.Float(), nullable=False),
        sa.Column("target", sa.Float(), nullable=True),
        sa.Column("achieved", sa.Boolean(), nullable=False),
        sa.Column("achieved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_learning_milestones_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["generated_lessons.id"],
            name="fk_learning_milestones_lesson_id_generated_lessons",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["activity_id"],
            ["learning_activities.id"],
            name="fk_learning_milestones_activity_id_learning_activities",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["learning_sessions.id"],
            name="fk_learning_milestones_session_id_learning_sessions",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_learning_milestones"),
        sa.UniqueConstraint(
            "user_id",
            "milestone_type",
            "scope_key",
            name="uq_learning_milestones_user_type_scope",
        ),
    )
    op.create_index("ix_learning_milestones_public_id", "learning_milestones", ["public_id"], unique=True)
    op.create_index("ix_learning_milestones_id", "learning_milestones", ["id"], unique=False)
    op.create_index("ix_learning_milestones_user_id", "learning_milestones", ["user_id"], unique=False)
    op.create_index("ix_learning_milestones_user_achieved", "learning_milestones", ["user_id", "achieved"], unique=False)

    op.create_table(
        "activity_recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lesson_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("recommendation_type", sa.String(length=30), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("activity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_activity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rationale", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_activity_recommendations_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["generated_lessons.id"],
            name="fk_activity_recommendations_lesson_id_generated_lessons",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["learning_sessions.id"],
            name="fk_activity_recommendations_session_id_learning_sessions",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["activity_id"],
            ["learning_activities.id"],
            name="fk_activity_recommendations_activity_id_learning_activities",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["target_activity_id"],
            ["learning_activities.id"],
            name="fk_arecs_target_act_id_lactivities",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_activity_recommendations"),
    )
    op.create_index("ix_activity_recommendations_public_id", "activity_recommendations", ["public_id"], unique=True)
    op.create_index("ix_activity_recommendations_id", "activity_recommendations", ["id"], unique=False)
    op.create_index("ix_activity_recommendations_user_id", "activity_recommendations", ["user_id"], unique=False)
    op.create_index("ix_activity_recommendations_lesson_id", "activity_recommendations", ["lesson_id"], unique=False)
    op.create_index("ix_activity_recommendations_user_status", "activity_recommendations", ["user_id", "status"], unique=False)
    op.create_index("ix_activity_recommendations_user_lesson", "activity_recommendations", ["user_id", "lesson_id", "status"], unique=False)


def downgrade() -> None:
    op.drop_table("activity_recommendations")
    op.drop_table("learning_milestones")
    op.drop_table("activity_feedback")
    op.drop_table("activity_attempts")
    op.drop_table("learning_activities")
