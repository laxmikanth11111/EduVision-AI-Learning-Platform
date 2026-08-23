"""AI Retrieval Engine & Intelligent AI Tutor

Revision ID: 0013_ai_tutor
Revises: 0012_rag_infrastructure
Create Date: 2026-08-04 00:00:00.000000

Adds the AI Retrieval Engine (Phase 4E.3) and Intelligent AI Tutor (Phase 4E.4)
tables:

* ``tutor_sessions`` — retrieval-scoped workspaces anchoring tutoring to a
  presentation/lesson, with aggregate token/usage analytics.
* ``tutor_conversations`` — continuous tutoring conversations holding the
  rolling summary and aggregate counters.
* ``tutor_messages`` — sanitized user/assistant turns with model, token usage,
  retrieval and answer metadata for full auditability.
* ``tutor_citations`` — source attributions linking answers to retrieved chunks
  with verification state.
* ``tutor_contexts`` — frozen retrieval snapshots (query, chunks, scores) so
  answers are reproducible.
* ``tutor_recommendations`` — personalized next-step suggestions.
* ``tutor_analytics`` — period rollups of usage/quality metrics.
* ``tutor_memories`` — durable learner facts spanning conversations.
* ``tutor_summaries`` — rolling conversation summaries.
* ``tutor_feedback`` — learner feedback on answers.
* ``tutor_confidences`` — per-answer confidence with component breakdown.
* ``tutor_search_history`` — audit log of every retrieval executed.

All child tables cascade from their parents; composite indexes cover the hot
scan patterns (per-user active rows, per-conversation message streams, citation
and confidence lookups by message).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0013_ai_tutor"
down_revision = "0012_rag_infrastructure"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tutor_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("presentation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lesson_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lesson_public_id", sa.String(length=40), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("mode", sa.String(length=30), nullable=False),
        sa.Column("difficulty", sa.String(length=20), nullable=True),
        sa.Column("language", sa.String(length=10), nullable=True),
        sa.Column("context_version", sa.String(length=32), nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("message_count", sa.Integer(), nullable=False),
        sa.Column("total_tokens_in", sa.Integer(), nullable=False),
        sa.Column("total_tokens_out", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("retry_state", sa.String(length=20), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["generated_lessons.id"],
            name="fk_tutor_sessions_lesson_id_generated_lessons",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["presentation_id"],
            ["presentations.id"],
            name="fk_tutor_sessions_presentation_id_presentations",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_tutor_sessions_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tutor_sessions"),
    )
    op.create_index("ix_tutor_sessions_public_id", "tutor_sessions", ["public_id"], unique=True)
    op.create_index("ix_tutor_sessions_id", "tutor_sessions", ["id"], unique=False)
    op.create_index("ix_tutor_sessions_user_id", "tutor_sessions", ["user_id"], unique=False)
    op.create_index("ix_tutor_sessions_presentation_id", "tutor_sessions", ["presentation_id"], unique=False)
    op.create_index("ix_tutor_sessions_lesson_id", "tutor_sessions", ["lesson_id"], unique=False)
    op.create_index("ix_tutor_sessions_last_message_at", "tutor_sessions", ["last_message_at"], unique=False)
    op.create_index("ix_tutor_sessions_deleted_at", "tutor_sessions", ["deleted_at"], unique=False)
    op.create_index("ix_tutor_sessions_user_status", "tutor_sessions", ["user_id", "status"], unique=False)
    op.create_index("ix_tutor_sessions_user_updated", "tutor_sessions", ["user_id", "updated_at"], unique=False)
    op.create_index("ix_tutor_sessions_lesson", "tutor_sessions", ["lesson_id", "status"], unique=False)

    op.create_table(
        "tutor_conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("session_public_id", sa.String(length=40), nullable=True),
        sa.Column("lesson_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lesson_public_id", sa.String(length=40), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("summary_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("context_version", sa.String(length=32), nullable=False),
        sa.Column("message_count", sa.Integer(), nullable=False),
        sa.Column("total_tokens_in", sa.Integer(), nullable=False),
        sa.Column("total_tokens_out", sa.Integer(), nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("retry_state", sa.String(length=20), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["generated_lessons.id"],
            name="fk_tutor_conversations_lesson_id_generated_lessons",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["tutor_sessions.id"],
            name="fk_tutor_conversations_session_id_tutor_sessions",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_tutor_conversations_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tutor_conversations"),
    )
    op.create_index("ix_tutor_conversations_public_id", "tutor_conversations", ["public_id"], unique=True)
    op.create_index("ix_tutor_conversations_id", "tutor_conversations", ["id"], unique=False)
    op.create_index("ix_tutor_conversations_user_id", "tutor_conversations", ["user_id"], unique=False)
    op.create_index("ix_tutor_conversations_session_id", "tutor_conversations", ["session_id"], unique=False)
    op.create_index("ix_tutor_conversations_lesson_id", "tutor_conversations", ["lesson_id"], unique=False)
    op.create_index("ix_tutor_conversations_last_message_at", "tutor_conversations", ["last_message_at"], unique=False)
    op.create_index("ix_tutor_conversations_deleted_at", "tutor_conversations", ["deleted_at"], unique=False)
    op.create_index("ix_tutor_conversations_user_status", "tutor_conversations", ["user_id", "status"], unique=False)
    op.create_index("ix_tutor_conversations_user_updated", "tutor_conversations", ["user_id", "updated_at"], unique=False)
    op.create_index("ix_tutor_conversations_session_status", "tutor_conversations", ["session_id", "status"], unique=False)

    op.create_table(
        "tutor_messages",
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
        sa.Column("retrieval_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("answer_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("retry_state", sa.String(length=20), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["tutor_conversations.id"],
            name="fk_tutor_messages_conversation_id_tutor_conversations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_tutor_messages_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tutor_messages"),
    )
    op.create_index("ix_tutor_messages_public_id", "tutor_messages", ["public_id"], unique=True)
    op.create_index("ix_tutor_messages_id", "tutor_messages", ["id"], unique=False)
    op.create_index("ix_tutor_messages_conversation_id", "tutor_messages", ["conversation_id"], unique=False)
    op.create_index("ix_tutor_messages_user_id", "tutor_messages", ["user_id"], unique=False)
    op.create_index("ix_tutor_messages_deleted_at", "tutor_messages", ["deleted_at"], unique=False)
    op.create_index("ix_tutor_messages_conversation_created", "tutor_messages", ["conversation_id", "created_at"], unique=False)
    op.create_index("ix_tutor_messages_user_created", "tutor_messages", ["user_id", "created_at"], unique=False)
    op.create_index("ix_tutor_messages_client_id", "tutor_messages", ["conversation_id", "client_message_id"], unique=False)

    op.create_table(
        "tutor_citations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("chunk_public_id", sa.String(length=40), nullable=True),
        sa.Column("presentation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lesson_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("citation_number", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("heading_path", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("excerpt", sa.Text(), nullable=True),
        sa.Column("source_page", sa.Integer(), nullable=True),
        sa.Column("source_slide", sa.Integer(), nullable=True),
        sa.Column("source_unit_position", sa.Integer(), nullable=True),
        sa.Column("relevance_score", sa.Float(), nullable=False),
        sa.Column("similarity_score", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("verification_status", sa.String(length=30), nullable=True),
        sa.Column("verification_score", sa.Float(), nullable=True),
        sa.Column("verification_details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("retry_state", sa.String(length=20), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["document_chunks.id"],
            name="fk_tutor_citations_chunk_id_document_chunks",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["tutor_conversations.id"],
            name="fk_tutor_citations_conversation_id_tutor_conversations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["tutor_messages.id"],
            name="fk_tutor_citations_message_id_tutor_messages",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_tutor_citations_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tutor_citations"),
    )
    op.create_index("ix_tutor_citations_public_id", "tutor_citations", ["public_id"], unique=True)
    op.create_index("ix_tutor_citations_id", "tutor_citations", ["id"], unique=False)
    op.create_index("ix_tutor_citations_conversation_id", "tutor_citations", ["conversation_id"], unique=False)
    op.create_index("ix_tutor_citations_message_id", "tutor_citations", ["message_id"], unique=False)
    op.create_index("ix_tutor_citations_user_id", "tutor_citations", ["user_id"], unique=False)
    op.create_index("ix_tutor_citations_chunk_id", "tutor_citations", ["chunk_id"], unique=False)
    op.create_index("ix_tutor_citations_chunk_public_id", "tutor_citations", ["chunk_public_id"], unique=False)
    op.create_index("ix_tutor_citations_presentation_id", "tutor_citations", ["presentation_id"], unique=False)
    op.create_index("ix_tutor_citations_lesson_id", "tutor_citations", ["lesson_id"], unique=False)
    op.create_index("ix_tutor_citations_deleted_at", "tutor_citations", ["deleted_at"], unique=False)
    op.create_index("ix_tutor_citations_message_status", "tutor_citations", ["message_id", "status"], unique=False)
    op.create_index("ix_tutor_citations_conversation_status", "tutor_citations", ["conversation_id", "status"], unique=False)

    op.create_table(
        "tutor_contexts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("search_type", sa.String(length=30), nullable=False),
        sa.Column("top_k", sa.Integer(), nullable=False),
        sa.Column("candidate_k", sa.Integer(), nullable=False),
        sa.Column("similarity_threshold", sa.Float(), nullable=False),
        sa.Column("chunks", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("scores", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("fused_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("retry_state", sa.String(length=20), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["tutor_conversations.id"],
            name="fk_tutor_contexts_conversation_id_tutor_conversations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["tutor_messages.id"],
            name="fk_tutor_contexts_message_id_tutor_messages",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_tutor_contexts_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tutor_contexts"),
    )
    op.create_index("ix_tutor_contexts_public_id", "tutor_contexts", ["public_id"], unique=True)
    op.create_index("ix_tutor_contexts_id", "tutor_contexts", ["id"], unique=False)
    op.create_index("ix_tutor_contexts_conversation_id", "tutor_contexts", ["conversation_id"], unique=False)
    op.create_index("ix_tutor_contexts_message_id", "tutor_contexts", ["message_id"], unique=False)
    op.create_index("ix_tutor_contexts_user_id", "tutor_contexts", ["user_id"], unique=False)
    op.create_index("ix_tutor_contexts_deleted_at", "tutor_contexts", ["deleted_at"], unique=False)
    op.create_index("ix_tutor_contexts_conversation_version", "tutor_contexts", ["conversation_id", "version"], unique=False)
    op.create_index("ix_tutor_contexts_message_status", "tutor_contexts", ["message_id", "status"], unique=False)

    op.create_table(
        "tutor_recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("recommendation_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("lesson_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lesson_public_id", sa.String(length=40), nullable=True),
        sa.Column("activity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("quiz_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("retry_state", sa.String(length=20), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["tutor_conversations.id"],
            name="fk_tutor_recommendations_conversation_id_tutor_conversations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["tutor_messages.id"],
            name="fk_tutor_recommendations_message_id_tutor_messages",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_tutor_recommendations_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tutor_recommendations"),
    )
    op.create_index("ix_tutor_recommendations_public_id", "tutor_recommendations", ["public_id"], unique=True)
    op.create_index("ix_tutor_recommendations_id", "tutor_recommendations", ["id"], unique=False)
    op.create_index("ix_tutor_recommendations_conversation_id", "tutor_recommendations", ["conversation_id"], unique=False)
    op.create_index("ix_tutor_recommendations_message_id", "tutor_recommendations", ["message_id"], unique=False)
    op.create_index("ix_tutor_recommendations_user_id", "tutor_recommendations", ["user_id"], unique=False)
    op.create_index("ix_tutor_recommendations_lesson_id", "tutor_recommendations", ["lesson_id"], unique=False)
    op.create_index("ix_tutor_recommendations_activity_id", "tutor_recommendations", ["activity_id"], unique=False)
    op.create_index("ix_tutor_recommendations_quiz_id", "tutor_recommendations", ["quiz_id"], unique=False)
    op.create_index("ix_tutor_recommendations_deleted_at", "tutor_recommendations", ["deleted_at"], unique=False)
    op.create_index("ix_tutor_recommendations_user_status", "tutor_recommendations", ["user_id", "status"], unique=False)
    op.create_index("ix_tutor_recommendations_conversation_status", "tutor_recommendations", ["conversation_id", "status"], unique=False)

    op.create_table(
        "tutor_analytics",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("period", sa.String(length=20), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("message_count", sa.Integer(), nullable=False),
        sa.Column("assistant_message_count", sa.Integer(), nullable=False),
        sa.Column("total_tokens_in", sa.Integer(), nullable=False),
        sa.Column("total_tokens_out", sa.Integer(), nullable=False),
        sa.Column("total_latency_ms", sa.Integer(), nullable=False),
        sa.Column("avg_confidence", sa.Float(), nullable=True),
        sa.Column("citation_count", sa.Integer(), nullable=False),
        sa.Column("grounded_count", sa.Integer(), nullable=False),
        sa.Column("ungrounded_count", sa.Integer(), nullable=False),
        sa.Column("grounded_rate", sa.Float(), nullable=True),
        sa.Column("retrieval_candidates_total", sa.Integer(), nullable=False),
        sa.Column("retrieval_candidates_avg", sa.Float(), nullable=True),
        sa.Column("feedback_helpful_count", sa.Integer(), nullable=False),
        sa.Column("feedback_not_helpful_count", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("retry_state", sa.String(length=20), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["tutor_sessions.id"],
            name="fk_tutor_analytics_session_id_tutor_sessions",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_tutor_analytics_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tutor_analytics"),
    )
    op.create_index("ix_tutor_analytics_public_id", "tutor_analytics", ["public_id"], unique=True)
    op.create_index("ix_tutor_analytics_id", "tutor_analytics", ["id"], unique=False)
    op.create_index("ix_tutor_analytics_user_id", "tutor_analytics", ["user_id"], unique=False)
    op.create_index("ix_tutor_analytics_session_id", "tutor_analytics", ["session_id"], unique=False)
    op.create_index("ix_tutor_analytics_deleted_at", "tutor_analytics", ["deleted_at"], unique=False)
    op.create_index("ix_tutor_analytics_period_date", "tutor_analytics", ["period", "period_start"], unique=False)
    op.create_index("ix_tutor_analytics_user_period", "tutor_analytics", ["user_id", "period"], unique=False)

    op.create_table(
        "tutor_memories",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("memory_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("retry_state", sa.String(length=20), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["tutor_conversations.id"],
            name="fk_tutor_memories_conversation_id_tutor_conversations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_tutor_memories_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tutor_memories"),
    )
    op.create_index("ix_tutor_memories_public_id", "tutor_memories", ["public_id"], unique=True)
    op.create_index("ix_tutor_memories_id", "tutor_memories", ["id"], unique=False)
    op.create_index("ix_tutor_memories_user_id", "tutor_memories", ["user_id"], unique=False)
    op.create_index("ix_tutor_memories_conversation_id", "tutor_memories", ["conversation_id"], unique=False)
    op.create_index("ix_tutor_memories_source_message_id", "tutor_memories", ["source_message_id"], unique=False)
    op.create_index("ix_tutor_memories_key", "tutor_memories", ["key"], unique=False)
    op.create_index("ix_tutor_memories_last_seen_at", "tutor_memories", ["last_seen_at"], unique=False)
    op.create_index("ix_tutor_memories_last_confirmed_at", "tutor_memories", ["last_confirmed_at"], unique=False)
    op.create_index("ix_tutor_memories_expires_at", "tutor_memories", ["expires_at"], unique=False)
    op.create_index("ix_tutor_memories_deleted_at", "tutor_memories", ["deleted_at"], unique=False)
    op.create_index("ix_tutor_memories_user_kind_status", "tutor_memories", ["user_id", "kind", "status"], unique=False)
    op.create_index("ix_tutor_memories_user_key", "tutor_memories", ["user_id", "key"], unique=False)

    op.create_table(
        "tutor_summaries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=True),
        sa.Column("summary_window_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary_window_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("messages_included", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("provider", sa.String(length=40), nullable=True),
        sa.Column("tokens_used", sa.Integer(), nullable=False),
        sa.Column("summary_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("retry_state", sa.String(length=20), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["tutor_conversations.id"],
            name="fk_tutor_summaries_conversation_id_tutor_conversations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_tutor_summaries_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tutor_summaries"),
    )
    op.create_index("ix_tutor_summaries_public_id", "tutor_summaries", ["public_id"], unique=True)
    op.create_index("ix_tutor_summaries_id", "tutor_summaries", ["id"], unique=False)
    op.create_index("ix_tutor_summaries_conversation_id", "tutor_summaries", ["conversation_id"], unique=False)
    op.create_index("ix_tutor_summaries_user_id", "tutor_summaries", ["user_id"], unique=False)
    op.create_index("ix_tutor_summaries_deleted_at", "tutor_summaries", ["deleted_at"], unique=False)
    op.create_index("ix_tutor_summaries_conversation_created", "tutor_summaries", ["conversation_id", "created_at"], unique=False)
    op.create_index("ix_tutor_summaries_user_status", "tutor_summaries", ["user_id", "status"], unique=False)

    op.create_table(
        "tutor_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("feedback_type", sa.String(length=20), nullable=False),
        sa.Column("comment", sa.String(length=2000), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("retry_state", sa.String(length=20), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["tutor_conversations.id"],
            name="fk_tutor_feedback_conversation_id_tutor_conversations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["tutor_messages.id"],
            name="fk_tutor_feedback_message_id_tutor_messages",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_tutor_feedback_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tutor_feedback"),
    )
    op.create_index("ix_tutor_feedback_public_id", "tutor_feedback", ["public_id"], unique=True)
    op.create_index("ix_tutor_feedback_id", "tutor_feedback", ["id"], unique=False)
    op.create_index("ix_tutor_feedback_conversation_id", "tutor_feedback", ["conversation_id"], unique=False)
    op.create_index("ix_tutor_feedback_message_id", "tutor_feedback", ["message_id"], unique=False)
    op.create_index("ix_tutor_feedback_user_id", "tutor_feedback", ["user_id"], unique=False)
    op.create_index("ix_tutor_feedback_deleted_at", "tutor_feedback", ["deleted_at"], unique=False)
    op.create_index("ix_tutor_feedback_message_type", "tutor_feedback", ["message_id", "feedback_type"], unique=False)
    op.create_index("ix_tutor_feedback_user_created", "tutor_feedback", ["user_id", "created_at"], unique=False)

    op.create_table(
        "tutor_confidences",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("level", sa.String(length=10), nullable=False),
        sa.Column("retrieval_score", sa.Float(), nullable=False),
        sa.Column("citation_overlap_score", sa.Float(), nullable=False),
        sa.Column("model_self_score", sa.Float(), nullable=False),
        sa.Column("component_scores", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("retry_state", sa.String(length=20), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["tutor_conversations.id"],
            name="fk_tutor_confidences_conversation_id_tutor_conversations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["tutor_messages.id"],
            name="fk_tutor_confidences_message_id_tutor_messages",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_tutor_confidences_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tutor_confidences"),
    )
    op.create_index("ix_tutor_confidences_public_id", "tutor_confidences", ["public_id"], unique=True)
    op.create_index("ix_tutor_confidences_id", "tutor_confidences", ["id"], unique=False)
    op.create_index("ix_tutor_confidences_conversation_id", "tutor_confidences", ["conversation_id"], unique=False)
    op.create_index("ix_tutor_confidences_message_id", "tutor_confidences", ["message_id"], unique=False)
    op.create_index("ix_tutor_confidences_user_id", "tutor_confidences", ["user_id"], unique=False)
    op.create_index("ix_tutor_confidences_deleted_at", "tutor_confidences", ["deleted_at"], unique=False)
    op.create_index("ix_tutor_confidences_message_score", "tutor_confidences", ["message_id", "score"], unique=False)
    op.create_index("ix_tutor_confidences_conversation_score", "tutor_confidences", ["conversation_id", "score"], unique=False)

    op.create_table(
        "tutor_search_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("search_type", sa.String(length=30), nullable=False),
        sa.Column("top_k", sa.Integer(), nullable=False),
        sa.Column("candidate_k", sa.Integer(), nullable=False),
        sa.Column("results_count", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("retrieval_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("retry_state", sa.String(length=20), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["tutor_conversations.id"],
            name="fk_tutor_search_history_conversation_id_tutor_conversations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_tutor_search_history_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tutor_search_history"),
    )
    op.create_index("ix_tutor_search_history_public_id", "tutor_search_history", ["public_id"], unique=True)
    op.create_index("ix_tutor_search_history_id", "tutor_search_history", ["id"], unique=False)
    op.create_index("ix_tutor_search_history_conversation_id", "tutor_search_history", ["conversation_id"], unique=False)
    op.create_index("ix_tutor_search_history_message_id", "tutor_search_history", ["message_id"], unique=False)
    op.create_index("ix_tutor_search_history_user_id", "tutor_search_history", ["user_id"], unique=False)
    op.create_index("ix_tutor_search_history_deleted_at", "tutor_search_history", ["deleted_at"], unique=False)
    op.create_index("ix_tutor_search_history_user_created", "tutor_search_history", ["user_id", "created_at"], unique=False)
    op.create_index("ix_tutor_search_history_conversation_created", "tutor_search_history", ["conversation_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_table("tutor_search_history")
    op.drop_table("tutor_confidences")
    op.drop_table("tutor_feedback")
    op.drop_table("tutor_summaries")
    op.drop_table("tutor_memories")
    op.drop_table("tutor_analytics")
    op.drop_table("tutor_recommendations")
    op.drop_table("tutor_contexts")
    op.drop_table("tutor_citations")
    op.drop_table("tutor_messages")
    op.drop_table("tutor_conversations")
    op.drop_table("tutor_sessions")
