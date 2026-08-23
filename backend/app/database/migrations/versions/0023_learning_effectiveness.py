"""Add P2 learning effectiveness infrastructure.

Revision ID: 0023_learning_effectiveness
Revises: 0022_terminology_migration
Create Date: 2026-08-20 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0023_learning_effectiveness"
down_revision = "0022_terminology"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # ── quizzes: add assessment_type column ──────────────────────────────
    quiz_cols = {c["name"] for c in inspector.get_columns("quizzes")}
    if "assessment_type" not in quiz_cols:
        op.add_column(
            "quizzes",
            sa.Column("assessment_type", sa.String(30), nullable=False, server_default="normal"),
        )
        op.create_index("ix_quizzes_assessment_type", "quizzes", ["assessment_type"])

    # ── learning_events ─────────────────────────────────────────────────
    if "learning_events" not in inspector.get_table_names():
        op.create_table(
            "learning_events",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("public_id", sa.String(40), nullable=False),
            sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("event_type", sa.String(50), nullable=False),
            sa.Column("resource_type", sa.String(50), nullable=True),
            sa.Column("resource_id", sa.String(100), nullable=True),
            sa.Column("concept_id", sa.String(100), nullable=True),
            sa.Column("presentation_id", UUID(as_uuid=True), nullable=True),
            sa.Column("metadata_json", JSONB, nullable=True),
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_learning_events_public_id", "learning_events", ["public_id"], unique=True)
        op.create_index("ix_learning_events_user_id", "learning_events", ["user_id"])
        op.create_index("ix_learning_events_event_type", "learning_events", ["event_type"])
        op.create_index("ix_learning_events_user_type", "learning_events", ["user_id", "event_type"])
        op.create_index("ix_learning_events_user_occurred", "learning_events", ["user_id", "occurred_at"])
        op.create_index("ix_learning_events_presentation", "learning_events", ["presentation_id"])

    # ── effectiveness_assessments ───────────────────────────────────────
    if "effectiveness_assessments" not in inspector.get_table_names():
        op.create_table(
            "effectiveness_assessments",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("public_id", sa.String(40), nullable=False),
            sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("presentation_id", UUID(as_uuid=True), sa.ForeignKey("presentations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("experiment_group", sa.String(50), nullable=True),
            sa.Column("baseline_quiz_id", UUID(as_uuid=True), nullable=True),
            sa.Column("baseline_score", sa.Float, nullable=True),
            sa.Column("baseline_concept_scores", JSONB, nullable=True),
            sa.Column("post_quiz_id", UUID(as_uuid=True), nullable=True),
            sa.Column("post_score", sa.Float, nullable=True),
            sa.Column("post_concept_scores", JSONB, nullable=True),
            sa.Column("retention_quiz_id", UUID(as_uuid=True), nullable=True),
            sa.Column("retention_score", sa.Float, nullable=True),
            sa.Column("retention_concept_scores", JSONB, nullable=True),
            sa.Column("retention_delay_hours", sa.Integer, nullable=True),
            sa.Column("absolute_gain", sa.Float, nullable=True),
            sa.Column("normalized_gain", sa.Float, nullable=True),
            sa.Column("retention_loss", sa.Float, nullable=True),
            sa.Column("retention_pct", sa.Float, nullable=True),
            sa.Column("total_learning_time_seconds", sa.Integer, nullable=True),
            sa.Column("events_summary", JSONB, nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="in_progress"),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_effectiveness_assessments_public_id", "effectiveness_assessments", ["public_id"], unique=True)
        op.create_index("ix_effectiveness_assessments_user_id", "effectiveness_assessments", ["user_id"])
        op.create_index("ix_effectiveness_assessments_presentation_id", "effectiveness_assessments", ["presentation_id"])
        op.create_index("ix_effectiveness_user_presentation", "effectiveness_assessments", ["user_id", "presentation_id"])
        op.create_index("ix_effectiveness_status", "effectiveness_assessments", ["status"])

    # ── user_feedback ───────────────────────────────────────────────────
    if "user_feedback" not in inspector.get_table_names():
        op.create_table(
            "user_feedback",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("public_id", sa.String(40), nullable=False),
            sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("presentation_id", UUID(as_uuid=True), nullable=True),
            sa.Column("assessment_id", UUID(as_uuid=True), nullable=True),
            sa.Column("perceived_understanding", sa.Integer, nullable=True),
            sa.Column("confidence", sa.Integer, nullable=True),
            sa.Column("usefulness", sa.Integer, nullable=True),
            sa.Column("visual_usefulness", sa.Integer, nullable=True),
            sa.Column("tutor_usefulness", sa.Integer, nullable=True),
            sa.Column("recommendation_usefulness", sa.Integer, nullable=True),
            sa.Column("overall_experience", sa.Integer, nullable=True),
            sa.Column("qualitative_feedback", sa.Text, nullable=True),
            sa.Column("extra_json", JSONB, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_user_feedback_public_id", "user_feedback", ["public_id"], unique=True)
        op.create_index("ix_user_feedback_user_id", "user_feedback", ["user_id"])
        op.create_index("ix_user_feedback_presentation_id", "user_feedback", ["presentation_id"])


def downgrade() -> None:
    op.drop_table("user_feedback")
    op.drop_table("effectiveness_assessments")
    op.drop_table("learning_events")
    op.drop_index("ix_quizzes_assessment_type", table_name="quizzes")
    op.drop_column("quizzes", "assessment_type")
