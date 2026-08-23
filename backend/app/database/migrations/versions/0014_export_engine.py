"""Downloads & Export Engine

Revision ID: 0014_export_engine
Revises: 0013_ai_tutor
Create Date: 2026-08-05 00:00:00.000000

Adds the Downloads & Export Engine (Phase 4F) tables:

* ``export_jobs`` — async export generation jobs with lifecycle, retry state and progress tracking.
* ``export_files`` — generated export artifact metadata, storage paths, sha256 checksums and expiration dates.
* ``export_templates`` — layout, CSS, header/footer HTML templates for exports.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0014_export_engine"
down_revision = "0013_ai_tutor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. export_jobs
    op.create_table(
        "export_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("format", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("template", sa.String(length=30), nullable=False, server_default="standard"),
        sa.Column("target_id", sa.String(length=100), nullable=True),
        sa.Column("options", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("progress_percentage", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_state", sa.String(length=20), nullable=False, server_default="none"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index("ix_export_jobs_public_id", "export_jobs", ["public_id"])
    op.create_index("ix_export_jobs_user_id", "export_jobs", ["user_id"])
    op.create_index("ix_export_jobs_user_status", "export_jobs", ["user_id", "status"])
    op.create_index("ix_export_jobs_kind_format", "export_jobs", ["kind", "format"])
    op.create_index("ix_export_jobs_deleted_at", "export_jobs", ["deleted_at"])

    # 2. export_files
    op.create_table(
        "export_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("download_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_state", sa.String(length=20), nullable=False, server_default="none"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["export_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index("ix_export_files_public_id", "export_files", ["public_id"])
    op.create_index("ix_export_files_job_id", "export_files", ["job_id"])
    op.create_index("ix_export_files_user_id", "export_files", ["user_id"])
    op.create_index("ix_export_files_job_user", "export_files", ["job_id", "user_id"])
    op.create_index("ix_export_files_expires_at", "export_files", ["expires_at"])
    op.create_index("ix_export_files_deleted_at", "export_files", ["deleted_at"])

    # 3. export_templates
    op.create_table(
        "export_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("template_key", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("format", sa.String(length=20), nullable=False),
        sa.Column("css_styles", sa.Text(), nullable=True),
        sa.Column("header_html", sa.Text(), nullable=True),
        sa.Column("footer_html", sa.Text(), nullable=True),
        sa.Column("config_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
        sa.UniqueConstraint("template_key"),
    )
    op.create_index("ix_export_templates_public_id", "export_templates", ["public_id"])
    op.create_index("ix_export_templates_template_key", "export_templates", ["template_key"])
    op.create_index("ix_export_templates_kind_format", "export_templates", ["kind", "format"])
    op.create_index("ix_export_templates_deleted_at", "export_templates", ["deleted_at"])

    # Seed default export templates
    now = datetime.now(UTC)
    export_templates_table = sa.table(
        "export_templates",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("public_id", sa.String),
        sa.column("name", sa.String),
        sa.column("template_key", sa.String),
        sa.column("description", sa.String),
        sa.column("kind", sa.String),
        sa.column("format", sa.String),
        sa.column("css_styles", sa.String),
        sa.column("header_html", sa.String),
        sa.column("footer_html", sa.String),
        sa.column("config_json", postgresql.JSONB),
        sa.column("is_default", sa.Boolean),
        sa.column("is_active", sa.Boolean),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )

    templates = [
        {
            "id": uuid.uuid4(),
            "public_id": f"exptpl_{uuid.uuid4().hex[:16]}",
            "name": "Standard Template",
            "template_key": "standard",
            "description": "Standard clean layout for study guides and documents",
            "kind": "notes",
            "format": "pdf",
            "css_styles": "body { font-family: sans-serif; margin: 40px; color: #333; } h1 { color: #1a365d; }",
            "header_html": "<header><h1>EduVision AI</h1></header>",
            "footer_html": "<footer><p>Generated by EduVision AI Platform</p></footer>",
            "config_json": {"page_size": "letter", "margin": "1in"},
            "is_default": True,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": uuid.uuid4(),
            "public_id": f"exptpl_{uuid.uuid4().hex[:16]}",
            "name": "Compact Template",
            "template_key": "compact",
            "description": "Compact dense layout for quick reference notes",
            "kind": "notes",
            "format": "pdf",
            "css_styles": "body { font-family: sans-serif; margin: 20px; font-size: 11pt; color: #222; }",
            "header_html": None,
            "footer_html": "<footer><p>EduVision AI</p></footer>",
            "config_json": {"page_size": "letter", "margin": "0.5in"},
            "is_default": False,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": uuid.uuid4(),
            "public_id": f"exptpl_{uuid.uuid4().hex[:16]}",
            "name": "Modern Dark Template",
            "template_key": "modern",
            "description": "Modern styled template with vibrant accent headers",
            "kind": "notes",
            "format": "html",
            "css_styles": "body { font-family: 'Inter', sans-serif; background: #0f172a; color: #f8fafc; padding: 2rem; }",
            "header_html": "<header><h1 style='color:#38bdf8'>EduVision AI Study Guide</h1></header>",
            "footer_html": "<footer><p style='color:#94a3b8'>EduVision AI Learning Platform</p></footer>",
            "config_json": {"theme": "dark"},
            "is_default": False,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        },
    ]
    op.bulk_insert(export_templates_table, templates)


def downgrade() -> None:
    op.drop_table("export_templates")
    op.drop_table("export_files")
    op.drop_table("export_jobs")
