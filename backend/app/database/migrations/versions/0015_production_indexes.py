"""Production Performance Indexes (Phase 4H)

Revision ID: 0015_production_indexes
Revises: 0014_export_engine
Create Date: 2026-08-05 00:00:00.000000

Adds optimized composite indexes for high-frequency query paths:
* presentations(user_id, status)
* quiz_attempts(user_id, completed_at)
* learning_sessions(user_id, status)
* document_chunks(scope_type, scope_id)
* activity_attempts(user_id, activity_id)
* tutor_messages(conversation_id, created_at)
* assistant_messages(conversation_id, created_at)
"""

from __future__ import annotations

from alembic import op

revision = "0015_production_indexes"
down_revision = "0014_export_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_presentations_user_status",
        "presentations",
        ["owner_id", "status"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "ix_quiz_attempts_user_completed",
        "quiz_attempts",
        ["user_id", "completed_at"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "ix_learning_sessions_user_status",
        "learning_sessions",
        ["user_id", "status"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "ix_document_chunks_scope",
        "document_chunks",
        ["chunk_type", "source"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "ix_activity_attempts_user_activity",
        "activity_attempts",
        ["user_id", "activity_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "ix_tutor_messages_conv_created",
        "tutor_messages",
        ["conversation_id", "created_at"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "ix_assistant_messages_conv_created",
        "assistant_messages",
        ["conversation_id", "created_at"],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_assistant_messages_conv_created", table_name="assistant_messages")
    op.drop_index("ix_tutor_messages_conv_created", table_name="tutor_messages")
    op.drop_index("ix_activity_attempts_user_activity", table_name="activity_attempts")
    op.drop_index("ix_document_chunks_scope", table_name="document_chunks")
    op.drop_index("ix_learning_sessions_user_status", table_name="learning_sessions")
    op.drop_index("ix_quiz_attempts_user_completed", table_name="quiz_attempts")
    op.drop_index("ix_presentations_user_status", table_name="presentations")
