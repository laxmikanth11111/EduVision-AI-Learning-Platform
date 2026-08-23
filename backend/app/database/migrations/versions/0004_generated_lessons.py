"""generated lessons, versions and blocks

Revision ID: 0004_generated_lessons
Revises: 0003_ai_usage_log
Create Date: 2026-08-02 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_generated_lessons"
down_revision = "0003_ai_usage_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "generated_lessons",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("presentation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("language", sa.String(length=10), nullable=True),
        sa.Column("difficulty", sa.String(length=20), nullable=True),
        sa.Column("model_override", sa.String(length=100), nullable=True),
        sa.Column("latest_version", sa.Integer(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_state", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["presentation_id"],
            ["presentations.id"],
            name="fk_generated_lessons_presentation_id_presentations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_generated_lessons_user_id_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_generated_lessons"),
    )
    op.create_index("ix_generated_lessons_public_id", "generated_lessons", ["public_id"], unique=True)
    op.create_index("ix_generated_lessons_id", "generated_lessons", ["id"], unique=False)
    op.create_index("ix_generated_lessons_presentation_id", "generated_lessons", ["presentation_id"], unique=False)
    op.create_index("ix_generated_lessons_mode", "generated_lessons", ["mode"], unique=False)
    op.create_index("ix_generated_lessons_status", "generated_lessons", ["status"], unique=False)
    op.create_index(
        "uq_generated_lessons_user_idempotency",
        "generated_lessons",
        ["user_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    op.create_table(
        "generated_lesson_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("lesson_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("language", sa.String(length=10), nullable=True),
        sa.Column("difficulty", sa.String(length=20), nullable=True),
        sa.Column("provider", sa.String(length=30), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("request_id", sa.String(length=40), nullable=True),
        sa.Column("correlation_id", sa.String(length=40), nullable=True),
        sa.Column("prompt_version", sa.String(length=32), nullable=True),
        sa.Column("payload_schema_version", sa.String(length=32), nullable=True),
        sa.Column("generation_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_cost", sa.Numeric(10, 6), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("provider_retry_count", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("quality_issues", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("quality_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("quality_version", sa.String(length=32), nullable=True),
        sa.Column("prompt_hash", sa.String(length=64), nullable=True),
        sa.Column("payload_hash", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["generated_lessons.id"],
            name="fk_generated_lesson_versions_lesson_id_generated_lessons",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_generated_lesson_versions"),
        sa.UniqueConstraint(
            "lesson_id",
            "version",
            name="uq_generated_lesson_versions_lesson_version",
        ),
    )
    op.create_index("ix_generated_lesson_versions_public_id", "generated_lesson_versions", ["public_id"], unique=True)
    op.create_index("ix_generated_lesson_versions_id", "generated_lesson_versions", ["id"], unique=False)
    op.create_index("ix_generated_lesson_versions_lesson_id", "generated_lesson_versions", ["lesson_id"], unique=False)

    op.create_table(
        "generated_blocks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("lesson_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("block_type", sa.String(length=30), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("heading", sa.String(length=500), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["lesson_version_id"],
            ["generated_lesson_versions.id"],
            name="fk_generated_blocks_lesson_version_id_generated_lesson_versions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_generated_blocks"),
        sa.UniqueConstraint(
            "lesson_version_id",
            "position",
            name="uq_generated_blocks_version_position",
        ),
    )
    op.create_index("ix_generated_blocks_public_id", "generated_blocks", ["public_id"], unique=True)
    op.create_index("ix_generated_blocks_id", "generated_blocks", ["id"], unique=False)
    op.create_index("ix_generated_blocks_lesson_version_id", "generated_blocks", ["lesson_version_id"], unique=False)


def downgrade() -> None:
    op.drop_table("generated_blocks")
    op.drop_table("generated_lesson_versions")
    op.drop_table("generated_lessons")
