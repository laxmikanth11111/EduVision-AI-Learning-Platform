"""initial schema for EduVision AI backend

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-31 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("is_verified", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("avatar_url", sa.String(length=500), nullable=True),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("login_attempts", sa.Integer(), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_ip", sa.String(length=45), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
    )
    op.create_index("ix_users_id", "users", ["id"], unique=False)
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "presentation_folders",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name="fk_presentation_folders_owner_id_users", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_id"], ["presentation_folders.id"], name="fk_presentation_folders_parent_id_presentation_folders", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_presentation_folders"),
        sa.UniqueConstraint("owner_id", "parent_id", "name", name="uq_presentation_folders_sibling"),
    )
    op.create_index("ix_presentation_folders_id", "presentation_folders", ["id"], unique=False)
    op.create_index("ix_presentation_folders_parent_id", "presentation_folders", ["parent_id"], unique=False)
    op.create_index("ix_presentation_folders_owner_id", "presentation_folders", ["owner_id"], unique=False)
    op.create_index("ix_presentation_folders_owner_parent", "presentation_folders", ["owner_id", "parent_id"], unique=False)

    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("refresh_token_hash", sa.String(length=128), nullable=False),
        sa.Column("device_info", sa.String(length=500), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_revoked", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_sessions_user_id_users", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_sessions"),
        sa.UniqueConstraint("refresh_token_hash", name="uq_sessions_refresh_token_hash"),
    )
    op.create_index("ix_sessions_user_active", "sessions", ["user_id", "is_revoked", "expires_at"], unique=False)
    op.create_index("ix_sessions_id", "sessions", ["id"], unique=False)
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"], unique=False)

    op.create_table(
        "verification_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("token_type", sa.String(length=30), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_used", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_verification_tokens_user_id_users", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_verification_tokens"),
    )
    op.create_index("ix_verification_tokens_id", "verification_tokens", ["id"], unique=False)
    op.create_index("ix_verification_tokens_lookup", "verification_tokens", ["token_hash", "token_type", "is_used"], unique=False)
    op.create_index("ix_verification_tokens_token_hash", "verification_tokens", ["token_hash"], unique=False)
    op.create_index("ix_verification_tokens_user_id", "verification_tokens", ["user_id"], unique=False)

    op.create_table(
        "presentations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("topic", sa.String(length=300), nullable=True),
        sa.Column("visibility", sa.String(length=20), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("folder_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("slide_count", sa.Integer(), nullable=False),
        sa.Column("file_key", sa.String(length=500), nullable=True),
        sa.Column("file_name", sa.String(length=255), nullable=True),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=True),
        sa.Column("thumbnail_key", sa.String(length=500), nullable=True),
        sa.Column("subject_id", sa.String(length=100), nullable=True),
        sa.Column("subject_confidence", sa.Float(), nullable=True),
        sa.Column("grade_level", sa.String(length=50), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name="fk_presentations_owner_id_users", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["folder_id"], ["presentation_folders.id"], name="fk_presentations_folder_id_presentation_folders", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_presentations"),
    )
    op.create_index("ix_presentations_title", "presentations", ["title"], unique=False)
    op.create_index("ix_presentations_deleted_at", "presentations", ["deleted_at"], unique=False)
    op.create_index("ix_presentations_folder_id", "presentations", ["folder_id"], unique=False)
    op.create_index("ix_presentations_public_id", "presentations", ["public_id"], unique=True)
    op.create_index("ix_presentations_owner_id", "presentations", ["owner_id"], unique=False)
    op.create_index("ix_presentations_subject_id", "presentations", ["subject_id"], unique=False)
    op.create_index("ix_presentations_id", "presentations", ["id"], unique=False)
    op.create_index("ix_presentations_status", "presentations", ["status"], unique=False)
    op.create_index("ix_presentations_topic", "presentations", ["topic"], unique=False)
    op.create_index("ix_presentations_owner_status", "presentations", ["owner_id", "status"], unique=False)
    op.create_index("ix_presentations_visibility", "presentations", ["visibility"], unique=False)

    op.create_table(
        "presentation_analytics",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("presentation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("view_count", sa.Integer(), nullable=False),
        sa.Column("unique_viewers", sa.Integer(), nullable=False),
        sa.Column("quiz_attempts", sa.Integer(), nullable=False),
        sa.Column("publish_count", sa.Integer(), nullable=False),
        sa.Column("learning_sessions", sa.Integer(), nullable=False),
        sa.Column("avg_quiz_score", sa.Float(), nullable=True),
        sa.Column("completion_rate", sa.Float(), nullable=True),
        sa.Column("last_viewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["presentation_id"], ["presentations.id"], name="fk_presentation_analytics_presentation_id_presentations", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_presentation_analytics"),
    )
    op.create_index("ix_presentation_analytics_presentation_id", "presentation_analytics", ["presentation_id"], unique=True)
    op.create_index("ix_presentation_analytics_id", "presentation_analytics", ["id"], unique=False)

    op.create_table(
        "presentation_audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("presentation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], name="fk_presentation_audit_logs_actor_id_users", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["presentation_id"], ["presentations.id"], name="fk_presentation_audit_logs_presentation_id_presentations", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_presentation_audit_logs"),
    )
    op.create_index("ix_presentation_audit_logs_created_at", "presentation_audit_logs", ["created_at"], unique=False)
    op.create_index("ix_presentation_audit_logs_actor_id", "presentation_audit_logs", ["actor_id"], unique=False)
    op.create_index("ix_presentation_audit_logs_id", "presentation_audit_logs", ["id"], unique=False)
    op.create_index("ix_presentation_audit_logs_pres_created", "presentation_audit_logs", ["presentation_id", "created_at"], unique=False)
    op.create_index("ix_presentation_audit_logs_entity_id", "presentation_audit_logs", ["entity_id"], unique=False)
    op.create_index("ix_presentation_audit_logs_action", "presentation_audit_logs", ["action"], unique=False)
    op.create_index("ix_presentation_audit_logs_presentation_id", "presentation_audit_logs", ["presentation_id"], unique=False)

    op.create_table(
        "presentation_collaborators",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("presentation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["presentation_id"], ["presentations.id"], name="fk_presentation_collaborators_presentation_id_presentations", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_presentation_collaborators_user_id_users", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_presentation_collaborators"),
        sa.UniqueConstraint("presentation_id", "user_id", name="uq_presentation_collaborators_pres_user"),
    )
    op.create_index("ix_presentation_collaborators_id", "presentation_collaborators", ["id"], unique=False)
    op.create_index("ix_presentation_collaborators_user_id", "presentation_collaborators", ["user_id"], unique=False)
    op.create_index("ix_presentation_collaborators_presentation_id", "presentation_collaborators", ["presentation_id"], unique=False)

    op.create_table(
        "presentation_tags",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("presentation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["presentation_id"], ["presentations.id"], name="fk_presentation_tags_presentation_id_presentations", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_presentation_tags"),
        sa.UniqueConstraint("presentation_id", "name", name="uq_presentation_tags_pres_name"),
    )
    op.create_index("ix_presentation_tags_presentation_id", "presentation_tags", ["presentation_id"], unique=False)
    op.create_index("ix_presentation_tags_id", "presentation_tags", ["id"], unique=False)
    op.create_index("ix_presentation_tags_name", "presentation_tags", ["name"], unique=False)

    op.create_table(
        "presentation_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("presentation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("slide_count", sa.Integer(), nullable=False),
        sa.Column("diff_summary", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_presentation_versions_created_by_users", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["presentation_id"], ["presentations.id"], name="fk_presentation_versions_presentation_id_presentations", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_presentation_versions"),
        sa.UniqueConstraint("presentation_id", "version_number", name="uq_presentation_versions_pres_version"),
    )
    op.create_index("ix_presentation_versions_public_id", "presentation_versions", ["public_id"], unique=True)
    op.create_index("ix_presentation_versions_created", "presentation_versions", ["created_at"], unique=False)
    op.create_index("ix_presentation_versions_id", "presentation_versions", ["id"], unique=False)
    op.create_index("ix_presentation_versions_created_by", "presentation_versions", ["created_by"], unique=False)
    op.create_index("ix_presentation_versions_presentation_id", "presentation_versions", ["presentation_id"], unique=False)


def downgrade() -> None:
    op.drop_table("presentation_versions")
    op.drop_table("presentation_tags")
    op.drop_table("presentation_collaborators")
    op.drop_table("presentation_audit_logs")
    op.drop_table("presentation_analytics")
    op.drop_table("presentations")
    op.drop_table("verification_tokens")
    op.drop_table("sessions")
    op.drop_table("presentation_folders")
    op.drop_table("users")
