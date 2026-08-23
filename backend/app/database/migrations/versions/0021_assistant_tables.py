"""AI learning assistant tables (Phase 4D.6)

Revision ID: 0021_assistant_tables
Revises: 0020_create_users
Create Date: 2026-08-19 00:00:00.000000

Creates the four assistant tables that back the AI learning assistant:
  - assistant_sessions
  - assistant_conversations
  - assistant_messages
  - assistant_context_snapshots
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0021_assistant_tables"
down_revision = "0020_create_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assistant_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lesson_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("session_public_id", sa.String(length=40), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False, server_default="AI Assistant"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("slide_position", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("block_position", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("context_version", sa.String(length=32), nullable=False, server_default="1"),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["generated_lessons.id"],
            name="fk_assistant_sessions_lesson_id_generated_lessons",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_assistant_sessions"),
    )
    op.create_index("ix_assistant_sessions_public_id", "assistant_sessions", ["public_id"], unique=True)
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
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("slide_position", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("block_position", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("context_version", sa.String(length=32), nullable=False, server_default="1"),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("summary_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
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
    op.create_index("ix_assistant_conversations_user_id", "assistant_conversations", ["user_id"], unique=False)
    op.create_index("ix_assistant_conversations_session_id", "assistant_conversations", ["session_id"], unique=False)
    op.create_index("ix_assistant_conversations_lesson_id", "assistant_conversations", ["lesson_id"], unique=False)
    op.create_index("ix_assistant_conversations_last_message_at", "assistant_conversations", ["last_message_at"], unique=False)
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
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("client_message_id", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("provider", sa.String(length=40), nullable=True),
        sa.Column("tokens_in", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("tokens_out", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default=sa.text("0")),
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
        sa.PrimaryKeyConstraint("id", name="pk_assistant_messages"),
    )
    op.create_index("ix_assistant_messages_public_id", "assistant_messages", ["public_id"], unique=True)
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
        sa.Column("slide_position", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("block_position", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("context_version", sa.String(length=32), nullable=False, server_default="1"),
        sa.Column("prompt_hash", sa.String(length=64), nullable=True),
        sa.Column("context", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["assistant_conversations.id"],
            name="fk_assistant_context_snapshots_conversation_id_assistant_conversations",
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
