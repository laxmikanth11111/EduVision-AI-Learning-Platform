"""adaptive learning

Revision ID: 0007_adaptive_learning
Revises: 0006_quiz_ai_metadata
Create Date: 2026-08-03 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007_adaptive_learning"
down_revision = "0006_quiz_ai_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "student_learning_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("overall_mastery", sa.Numeric(5, 2), nullable=True),
        sa.Column("average_score", sa.Numeric(8, 2), nullable=True),
        sa.Column("average_percent_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("average_time_seconds", sa.Integer(), nullable=False),
        sa.Column("total_attempts", sa.Integer(), nullable=False),
        sa.Column("total_questions_answered", sa.Integer(), nullable=False),
        sa.Column("correct_answers", sa.Integer(), nullable=False),
        sa.Column("accuracy", sa.Numeric(5, 2), nullable=True),
        sa.Column("weak_concepts", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("strong_concepts", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("recommended_difficulty", sa.String(length=20), nullable=False),
        sa.Column("difficulty_progression", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("bloom_progress", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("objectives_completed", sa.Integer(), nullable=False),
        sa.Column("objectives_total", sa.Integer(), nullable=False),
        sa.Column("confidence_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("engagement_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("quiz_history", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("knowledge_graph", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("review_plan", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("recommended_next_lesson_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("recommended_next_lesson_public_id", sa.String(length=40), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("profile_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_student_learning_profiles_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recommended_next_lesson_id"],
            ["generated_lessons.id"],
            name="fk_slp_rec_next_lesson_id_gen_lessons",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_student_learning_profiles"),
        sa.UniqueConstraint(
            "user_id",
            name="uq_student_learning_profiles_user_id",
        ),
    )
    op.create_index("ix_student_learning_profiles_public_id", "student_learning_profiles", ["public_id"], unique=True)
    op.create_index("ix_student_learning_profiles_id", "student_learning_profiles", ["id"], unique=False)
    op.create_index("ix_student_learning_profiles_user_id", "student_learning_profiles", ["user_id"], unique=True)
    op.create_index("ix_student_learning_profiles_last_activity_at", "student_learning_profiles", ["last_activity_at"], unique=False)

    op.create_table(
        "topic_mastery",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("topic", sa.String(length=200), nullable=False),
        sa.Column("mastery", sa.Numeric(5, 2), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("correct", sa.Integer(), nullable=False),
        sa.Column("accuracy", sa.Numeric(5, 2), nullable=False),
        sa.Column("avg_time_seconds", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_topic_mastery_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_topic_mastery"),
        sa.UniqueConstraint(
            "user_id",
            "topic",
            name="uq_topic_mastery_user_topic",
        ),
    )
    op.create_index("ix_topic_mastery_public_id", "topic_mastery", ["public_id"], unique=True)
    op.create_index("ix_topic_mastery_id", "topic_mastery", ["id"], unique=False)
    op.create_index("ix_topic_mastery_user_id", "topic_mastery", ["user_id"], unique=False)

    op.create_table(
        "concept_mastery",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("topic", sa.String(length=200), nullable=False),
        sa.Column("concept", sa.String(length=200), nullable=False),
        sa.Column("mastery", sa.Numeric(5, 2), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("correct", sa.Integer(), nullable=False),
        sa.Column("accuracy", sa.Numeric(5, 2), nullable=False),
        sa.Column("avg_time_seconds", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_concept_mastery_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_concept_mastery"),
        sa.UniqueConstraint(
            "user_id",
            "topic",
            "concept",
            name="uq_concept_mastery_user_topic_concept",
        ),
    )
    op.create_index("ix_concept_mastery_public_id", "concept_mastery", ["public_id"], unique=True)
    op.create_index("ix_concept_mastery_id", "concept_mastery", ["id"], unique=False)
    op.create_index("ix_concept_mastery_user_id", "concept_mastery", ["user_id"], unique=False)

    op.create_table(
        "learning_recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recommendation_type", sa.String(length=30), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("target_type", sa.String(length=30), nullable=True),
        sa.Column("target_id", sa.String(length=40), nullable=True),
        sa.Column("rationale", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_learning_recommendations_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_learning_recommendations"),
    )
    op.create_index("ix_learning_recommendations_public_id", "learning_recommendations", ["public_id"], unique=True)
    op.create_index("ix_learning_recommendations_id", "learning_recommendations", ["id"], unique=False)
    op.create_index("ix_learning_recommendations_user_id", "learning_recommendations", ["user_id"], unique=False)
    op.create_index("ix_learning_recommendations_user_status", "learning_recommendations", ["user_id", "status"], unique=False)
    op.create_index("ix_learning_recommendations_user_type", "learning_recommendations", ["user_id", "recommendation_type"], unique=False)

    op.create_table(
        "adaptive_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_adaptive_history_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_adaptive_history"),
    )
    op.create_index("ix_adaptive_history_public_id", "adaptive_history", ["public_id"], unique=True)
    op.create_index("ix_adaptive_history_id", "adaptive_history", ["id"], unique=False)
    op.create_index("ix_adaptive_history_user_id", "adaptive_history", ["user_id"], unique=False)
    op.create_index("ix_adaptive_history_user_event", "adaptive_history", ["user_id", "event_type"], unique=False)

    op.create_table(
        "progress_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period", sa.String(length=10), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_progress_snapshots_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_progress_snapshots"),
        sa.UniqueConstraint(
            "user_id",
            "period",
            "period_start",
            name="uq_progress_snapshots_user_period_start",
        ),
    )
    op.create_index("ix_progress_snapshots_public_id", "progress_snapshots", ["public_id"], unique=True)
    op.create_index("ix_progress_snapshots_id", "progress_snapshots", ["id"], unique=False)
    op.create_index("ix_progress_snapshots_user_id", "progress_snapshots", ["user_id"], unique=False)
    op.create_index("ix_progress_snapshots_user_period", "progress_snapshots", ["user_id", "period"], unique=False)


def downgrade() -> None:
    op.drop_table("progress_snapshots")
    op.drop_table("adaptive_history")
    op.drop_table("learning_recommendations")
    op.drop_table("concept_mastery")
    op.drop_table("topic_mastery")
    op.drop_table("student_learning_profiles")
