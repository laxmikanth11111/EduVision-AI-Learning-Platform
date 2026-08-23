"""document content extraction tables

Revision ID: 0002_document_content_extraction
Revises: 0001_initial
Create Date: 2026-08-01 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_document_content_extraction"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "presentations",
        sa.Column("extraction_status", sa.String(length=20), nullable=False, server_default="none"),
    )
    op.add_column(
        "presentations",
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "presentations",
        sa.Column("extraction_error", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_presentations_extraction_status",
        "presentations",
        ["extraction_status"],
        unique=False,
    )

    op.create_table(
        "content_units",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("presentation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("unit_type", sa.String(length=20), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("source_page", sa.Integer(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["presentation_id"],
            ["presentations.id"],
            name="fk_content_units_presentation_id_presentations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_content_units"),
        sa.UniqueConstraint(
            "presentation_id",
            "position",
            name="uq_content_units_pres_position",
        ),
    )
    op.create_index("ix_content_units_public_id", "content_units", ["public_id"], unique=True)
    op.create_index("ix_content_units_id", "content_units", ["id"], unique=False)
    op.create_index("ix_content_units_presentation_id", "content_units", ["presentation_id"], unique=False)
    op.create_index("ix_content_units_pres_position", "content_units", ["presentation_id", "position"], unique=False)

    op.create_table(
        "content_blocks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("content_unit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("block_type", sa.String(length=30), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["content_unit_id"],
            ["content_units.id"],
            name="fk_content_blocks_content_unit_id_content_units",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_content_blocks"),
        sa.UniqueConstraint(
            "content_unit_id",
            "position",
            name="uq_content_blocks_unit_position",
        ),
    )
    op.create_index("ix_content_blocks_public_id", "content_blocks", ["public_id"], unique=True)
    op.create_index("ix_content_blocks_id", "content_blocks", ["id"], unique=False)
    op.create_index("ix_content_blocks_content_unit_id", "content_blocks", ["content_unit_id"], unique=False)
    op.create_index("ix_content_blocks_unit_position", "content_blocks", ["content_unit_id", "position"], unique=False)


def downgrade() -> None:
    op.drop_table("content_blocks")
    op.drop_table("content_units")
    op.drop_index("ix_presentations_extraction_status", table_name="presentations")
    op.drop_column("presentations", "extraction_error")
    op.drop_column("presentations", "extracted_at")
    op.drop_column("presentations", "extraction_status")
