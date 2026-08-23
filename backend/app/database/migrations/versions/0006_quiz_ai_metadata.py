"""quiz ai metadata

Revision ID: 0006_quiz_ai_metadata
Revises: 0005_quiz_subsystem
Create Date: 2026-08-03 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_quiz_ai_metadata"
down_revision = "0005_quiz_subsystem"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "questions",
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "quizzes",
        sa.Column("model_override", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "quizzes",
        sa.Column("target_units", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "quizzes",
        sa.Column("question_types", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "quizzes",
        sa.Column("requested_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "quizzes",
        sa.Column("bloom_levels", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "quizzes",
        sa.Column("learning_objectives", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("quizzes", "learning_objectives")
    op.drop_column("quizzes", "bloom_levels")
    op.drop_column("quizzes", "requested_count")
    op.drop_column("quizzes", "question_types")
    op.drop_column("quizzes", "target_units")
    op.drop_column("quizzes", "model_override")
    op.drop_column("questions", "meta")
