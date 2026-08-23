"""AI usage accounting table

Revision ID: 0003_ai_usage_log
Revises: 0002_document_content_extraction
Create Date: 2026-08-02 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_ai_usage_log"
down_revision = "0002_document_content_extraction"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_usage_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("finish_reason", sa.String(length=32), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost", sa.Numeric(12, 6), nullable=False, server_default="0.000000"),
        sa.Column("latency_ms", sa.Float(), nullable=False, server_default="0"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cache_hit", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("resource_type", sa.String(length=32), nullable=True),
        sa.Column("resource_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_ai_usage_logs"),
    )
    op.create_index("ix_ai_usage_logs_public_id", "ai_usage_logs", ["public_id"], unique=True)
    op.create_index("ix_ai_usage_logs_id", "ai_usage_logs", ["id"], unique=False)
    op.create_index("ix_ai_usage_logs_request_id", "ai_usage_logs", ["request_id"], unique=False)
    op.create_index("ix_ai_usage_logs_correlation_id", "ai_usage_logs", ["correlation_id"], unique=False)
    op.create_index("ix_ai_usage_logs_provider", "ai_usage_logs", ["provider"], unique=False)
    op.create_index("ix_ai_usage_logs_model", "ai_usage_logs", ["model"], unique=False)
    op.create_index("ix_ai_usage_logs_status", "ai_usage_logs", ["status"], unique=False)
    op.create_index("ix_ai_usage_logs_resource_id", "ai_usage_logs", ["resource_id"], unique=False)


def downgrade() -> None:
    op.drop_table("ai_usage_logs")
