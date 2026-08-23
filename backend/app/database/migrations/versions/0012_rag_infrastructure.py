"""RAG infrastructure & embedding generation pipeline

Revision ID: 0012_rag_infrastructure
Revises: 0011_personalized_learning
Create Date: 2026-08-04 00:00:00.000000

Adds the RAG indexing foundation (Phase 4E.1) and embedding generation
pipeline (Phase 4E.2) tables:

* ``chunk_sections`` — a hierarchy of headings/sections/slides/content-units a
  chunk can be anchored to, with parent links, level and heading path.
* ``document_chunks`` — atomic retrievable units with source references
  (presentation/lesson/version/unit/block), ordering, token/char counts,
  content hash + checksum (change detection), language and retry state.
* ``chunk_embeddings`` — versioned vectors per chunk/provider/model with
  embedding hash and checksum for integrity verification.
* ``chunk_relationships`` — structural links (parent/child/next/related)
  between chunks for hierarchical retrieval later.
* ``vector_indexes`` — per-scope index metadata with chunking strategy,
  provider/model/dimension and source hash for incremental rebuilds.
* ``vector_index_versions`` — frozen snapshots of an index build.
* ``embedding_metadata`` — provider/model capability rows (dimension, token
  limits, fingerprint) used to validate and version embeddings.
* ``embedding_jobs`` — async job queue rows (index/refresh/cleanup) with
  idempotency keys and retry state.
* ``embedding_batches`` — per-job batches with sequence and progress counters.
* ``embedding_statistics`` — analytics-ready rollups (total/daily) over chunk
  and embedding counts, staleness and failures.

All child tables cascade from their parents; composite indexes cover the hot
scan patterns (pending jobs, per-index chunk scans, per-index stats lookups).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0012_rag_infrastructure"
down_revision = "0011_personalized_learning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chunk_sections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("presentation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lesson_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("section_type", sa.String(length=30), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("heading_path", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source_page", sa.Integer(), nullable=True),
        sa.Column("source_slide", sa.Integer(), nullable=True),
        sa.Column("source_unit_position", sa.Integer(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["chunk_sections.id"],
            name="fk_chunk_sections_parent_id_chunk_sections",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["presentation_id"],
            ["presentations.id"],
            name="fk_chunk_sections_presentation_id_presentations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["generated_lessons.id"],
            name="fk_chunk_sections_lesson_id_generated_lessons",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_chunk_sections"),
        sa.UniqueConstraint(
            "presentation_id",
            "position",
            "level",
            name="uq_chunk_sections_pres_pos_level",
        ),
    )
    op.create_index("ix_chunk_sections_public_id", "chunk_sections", ["public_id"], unique=True)
    op.create_index("ix_chunk_sections_id", "chunk_sections", ["id"], unique=False)
    op.create_index("ix_chunk_sections_presentation_id", "chunk_sections", ["presentation_id"], unique=False)
    op.create_index("ix_chunk_sections_lesson_id", "chunk_sections", ["lesson_id"], unique=False)
    op.create_index("ix_chunk_sections_parent_id", "chunk_sections", ["parent_id"], unique=False)
    op.create_index("ix_chunk_sections_deleted_at", "chunk_sections", ["deleted_at"], unique=False)
    op.create_index("ix_chunk_sections_pres_level", "chunk_sections", ["presentation_id", "level"], unique=False)

    op.create_table(
        "document_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("presentation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lesson_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lesson_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("content_unit_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("content_block_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("section_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("parent_chunk_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("chunk_type", sa.String(length=30), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("heading_path", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("character_count", sa.Integer(), nullable=False),
        sa.Column("chunk_hash", sa.String(length=64), nullable=True),
        sa.Column("checksum", sa.String(length=128), nullable=True),
        sa.Column("language", sa.String(length=10), nullable=True),
        sa.Column("source_page", sa.Integer(), nullable=True),
        sa.Column("source_slide", sa.Integer(), nullable=True),
        sa.Column("source_unit_position", sa.Integer(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("max_retries", sa.Integer(), nullable=False),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_state", sa.String(length=20), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["content_block_id"],
            ["content_blocks.id"],
            name="fk_document_chunks_content_block_id_content_blocks",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["content_unit_id"],
            ["content_units.id"],
            name="fk_document_chunks_content_unit_id_content_units",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["generated_lessons.id"],
            name="fk_document_chunks_lesson_id_generated_lessons",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["lesson_version_id"],
            ["generated_lesson_versions.id"],
            name="fk_document_chunks_lesson_version_id_generated_lesson_versions",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["parent_chunk_id"],
            ["document_chunks.id"],
            name="fk_document_chunks_parent_chunk_id_document_chunks",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["presentation_id"],
            ["presentations.id"],
            name="fk_document_chunks_presentation_id_presentations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["section_id"],
            ["chunk_sections.id"],
            name="fk_document_chunks_section_id_chunk_sections",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_chunks"),
        sa.UniqueConstraint(
            "presentation_id",
            "position",
            "version",
            name="uq_document_chunks_pres_position_version",
        ),
    )
    op.create_index("ix_document_chunks_public_id", "document_chunks", ["public_id"], unique=True)
    op.create_index("ix_document_chunks_id", "document_chunks", ["id"], unique=False)
    op.create_index("ix_document_chunks_presentation_id", "document_chunks", ["presentation_id"], unique=False)
    op.create_index("ix_document_chunks_lesson_id", "document_chunks", ["lesson_id"], unique=False)
    op.create_index("ix_document_chunks_lesson_version_id", "document_chunks", ["lesson_version_id"], unique=False)
    op.create_index("ix_document_chunks_content_unit_id", "document_chunks", ["content_unit_id"], unique=False)
    op.create_index("ix_document_chunks_content_block_id", "document_chunks", ["content_block_id"], unique=False)
    op.create_index("ix_document_chunks_section_id", "document_chunks", ["section_id"], unique=False)
    op.create_index("ix_document_chunks_parent_chunk_id", "document_chunks", ["parent_chunk_id"], unique=False)
    op.create_index("ix_document_chunks_chunk_hash", "document_chunks", ["chunk_hash"], unique=False)
    op.create_index("ix_document_chunks_deleted_at", "document_chunks", ["deleted_at"], unique=False)
    op.create_index("ix_document_chunks_source_position", "document_chunks", ["source", "position"], unique=False)
    op.create_index("ix_document_chunks_hash_version", "document_chunks", ["chunk_hash", "version"], unique=False)
    op.create_index("ix_document_chunks_pres_status", "document_chunks", ["presentation_id", "status"], unique=False)

    op.create_table(
        "chunk_embeddings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("dimension", sa.Integer(), nullable=False),
        sa.Column("vector", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("embedding_hash", sa.String(length=64), nullable=True),
        sa.Column("checksum", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["document_chunks.id"],
            name="fk_chunk_embeddings_chunk_id_document_chunks",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_chunk_embeddings"),
        sa.UniqueConstraint(
            "chunk_id",
            "provider",
            "model",
            "version",
            name="uq_chunk_embeddings_chunk_provider_model_version",
        ),
    )
    op.create_index("ix_chunk_embeddings_public_id", "chunk_embeddings", ["public_id"], unique=True)
    op.create_index("ix_chunk_embeddings_id", "chunk_embeddings", ["id"], unique=False)
    op.create_index("ix_chunk_embeddings_chunk_id", "chunk_embeddings", ["chunk_id"], unique=False)
    op.create_index("ix_chunk_embeddings_embedding_hash", "chunk_embeddings", ["embedding_hash"], unique=False)
    op.create_index("ix_chunk_embeddings_deleted_at", "chunk_embeddings", ["deleted_at"], unique=False)
    op.create_index("ix_chunk_embeddings_provider_model", "chunk_embeddings", ["provider", "model"], unique=False)
    op.create_index("ix_chunk_embeddings_status_version", "chunk_embeddings", ["status", "version"], unique=False)
    op.create_index("ix_chunk_embeddings_chunk_status", "chunk_embeddings", ["chunk_id", "status"], unique=False)

    op.create_table(
        "chunk_relationships",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("source_chunk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_chunk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("relationship_type", sa.String(length=30), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_chunk_id"],
            ["document_chunks.id"],
            name="fk_chunk_relationships_source_chunk_id_document_chunks",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_chunk_id"],
            ["document_chunks.id"],
            name="fk_chunk_relationships_target_chunk_id_document_chunks",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_chunk_relationships"),
        sa.UniqueConstraint(
            "source_chunk_id",
            "target_chunk_id",
            "relationship_type",
            name="uq_chunk_relationships_source_target_type",
        ),
    )
    op.create_index("ix_chunk_relationships_public_id", "chunk_relationships", ["public_id"], unique=True)
    op.create_index("ix_chunk_relationships_id", "chunk_relationships", ["id"], unique=False)
    op.create_index("ix_chunk_relationships_source_chunk_id", "chunk_relationships", ["source_chunk_id"], unique=False)
    op.create_index("ix_chunk_relationships_target_chunk_id", "chunk_relationships", ["target_chunk_id"], unique=False)
    op.create_index("ix_chunk_relationships_type", "chunk_relationships", ["relationship_type"], unique=False)

    op.create_table(
        "vector_indexes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("presentation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lesson_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("index_type", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("strategy", sa.String(length=20), nullable=False),
        sa.Column("chunk_size", sa.Integer(), nullable=False),
        sa.Column("chunk_overlap", sa.Integer(), nullable=False),
        sa.Column("max_chunk_tokens", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("dimension", sa.Integer(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("embedding_count", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=True),
        sa.Column("latest_version", sa.Integer(), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_state", sa.String(length=20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["generated_lessons.id"],
            name="fk_vector_indexes_lesson_id_generated_lessons",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["presentation_id"],
            ["presentations.id"],
            name="fk_vector_indexes_presentation_id_presentations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_vector_indexes"),
        sa.UniqueConstraint(
            "presentation_id",
            "index_type",
            name="uq_vector_indexes_presentation_index_type",
        ),
    )
    op.create_index("ix_vector_indexes_public_id", "vector_indexes", ["public_id"], unique=True)
    op.create_index("ix_vector_indexes_id", "vector_indexes", ["id"], unique=False)
    op.create_index("ix_vector_indexes_presentation_id", "vector_indexes", ["presentation_id"], unique=False)
    op.create_index("ix_vector_indexes_lesson_id", "vector_indexes", ["lesson_id"], unique=False)
    op.create_index("ix_vector_indexes_source_hash", "vector_indexes", ["source_hash"], unique=False)
    op.create_index("ix_vector_indexes_deleted_at", "vector_indexes", ["deleted_at"], unique=False)
    op.create_index("ix_vector_indexes_status_updated", "vector_indexes", ["status", "updated_at"], unique=False)
    op.create_index("ix_vector_indexes_presentation_status", "vector_indexes", ["presentation_id", "status"], unique=False)
    op.create_index("ix_vector_indexes_type_status", "vector_indexes", ["index_type", "status"], unique=False)

    op.create_table(
        "vector_index_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("index_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("embedding_count", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("changelog", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["index_id"],
            ["vector_indexes.id"],
            name="fk_vector_index_versions_index_id_vector_indexes",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_vector_index_versions"),
        sa.UniqueConstraint(
            "index_id",
            "version",
            name="uq_vector_index_versions_index_version",
        ),
    )
    op.create_index("ix_vector_index_versions_public_id", "vector_index_versions", ["public_id"], unique=True)
    op.create_index("ix_vector_index_versions_id", "vector_index_versions", ["id"], unique=False)
    op.create_index("ix_vector_index_versions_index_id", "vector_index_versions", ["index_id"], unique=False)
    op.create_index("ix_vector_index_versions_source_hash", "vector_index_versions", ["source_hash"], unique=False)
    op.create_index("ix_vector_index_versions_deleted_at", "vector_index_versions", ["deleted_at"], unique=False)
    op.create_index("ix_vector_index_versions_index_version", "vector_index_versions", ["index_id", "version"], unique=False)
    op.create_index("ix_vector_index_versions_status", "vector_index_versions", ["status"], unique=False)

    op.create_table(
        "embedding_metadata",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("index_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("dimension", sa.Integer(), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=True),
        sa.Column("max_tokens_per_input", sa.Integer(), nullable=False),
        sa.Column("supported_languages", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("config_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("fingerprint", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["index_id"],
            ["vector_indexes.id"],
            name="fk_embedding_metadata_index_id_vector_indexes",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_embedding_metadata"),
        sa.UniqueConstraint(
            "provider",
            "model",
            name="uq_embedding_metadata_provider_model",
        ),
    )
    op.create_index("ix_embedding_metadata_public_id", "embedding_metadata", ["public_id"], unique=True)
    op.create_index("ix_embedding_metadata_id", "embedding_metadata", ["id"], unique=False)
    op.create_index("ix_embedding_metadata_index_id", "embedding_metadata", ["index_id"], unique=False)
    op.create_index("ix_embedding_metadata_fingerprint", "embedding_metadata", ["fingerprint"], unique=False)
    op.create_index("ix_embedding_metadata_provider_model", "embedding_metadata", ["provider", "model"], unique=False)
    op.create_index("ix_embedding_metadata_status", "embedding_metadata", ["status"], unique=False)

    op.create_table(
        "embedding_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("index_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("presentation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lesson_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("job_type", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("total_items", sa.Integer(), nullable=False),
        sa.Column("processed_items", sa.Integer(), nullable=False),
        sa.Column("failed_items", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_state", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["index_id"],
            ["vector_indexes.id"],
            name="fk_embedding_jobs_index_id_vector_indexes",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["generated_lessons.id"],
            name="fk_embedding_jobs_lesson_id_generated_lessons",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["presentation_id"],
            ["presentations.id"],
            name="fk_embedding_jobs_presentation_id_presentations",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_embedding_jobs_user_id_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_embedding_jobs"),
        sa.UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_embedding_jobs_user_idempotency",
        ),
    )
    op.create_index("ix_embedding_jobs_public_id", "embedding_jobs", ["public_id"], unique=True)
    op.create_index("ix_embedding_jobs_id", "embedding_jobs", ["id"], unique=False)
    op.create_index("ix_embedding_jobs_index_id", "embedding_jobs", ["index_id"], unique=False)
    op.create_index("ix_embedding_jobs_user_id", "embedding_jobs", ["user_id"], unique=False)
    op.create_index("ix_embedding_jobs_presentation_id", "embedding_jobs", ["presentation_id"], unique=False)
    op.create_index("ix_embedding_jobs_lesson_id", "embedding_jobs", ["lesson_id"], unique=False)
    op.create_index("ix_embedding_jobs_deleted_at", "embedding_jobs", ["deleted_at"], unique=False)
    op.create_index("ix_embedding_jobs_status_priority", "embedding_jobs", ["status", "priority"], unique=False)
    op.create_index("ix_embedding_jobs_type_status", "embedding_jobs", ["job_type", "status"], unique=False)
    op.create_index("ix_embedding_jobs_index_status", "embedding_jobs", ["index_id", "status"], unique=False)
    op.create_index("ix_embedding_jobs_status_updated", "embedding_jobs", ["status", "updated_at"], unique=False)

    op.create_table(
        "embedding_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("total_items", sa.Integer(), nullable=False),
        sa.Column("processed_items", sa.Integer(), nullable=False),
        sa.Column("failed_items", sa.Integer(), nullable=False),
        sa.Column("request_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["embedding_jobs.id"],
            name="fk_embedding_batches_job_id_embedding_jobs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_embedding_batches"),
        sa.UniqueConstraint(
            "job_id",
            "sequence",
            name="uq_embedding_batches_job_sequence",
        ),
    )
    op.create_index("ix_embedding_batches_public_id", "embedding_batches", ["public_id"], unique=True)
    op.create_index("ix_embedding_batches_id", "embedding_batches", ["id"], unique=False)
    op.create_index("ix_embedding_batches_job_id", "embedding_batches", ["job_id"], unique=False)
    op.create_index("ix_embedding_batches_deleted_at", "embedding_batches", ["deleted_at"], unique=False)
    op.create_index("ix_embedding_batches_job_status", "embedding_batches", ["job_id", "status"], unique=False)
    op.create_index("ix_embedding_batches_status_updated", "embedding_batches", ["status", "updated_at"], unique=False)

    op.create_table(
        "embedding_statistics",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("index_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("period", sa.String(length=20), nullable=False),
        sa.Column("stats_date", sa.Date(), nullable=True),
        sa.Column("total_chunks", sa.Integer(), nullable=False),
        sa.Column("embedded_chunks", sa.Integer(), nullable=False),
        sa.Column("pending_chunks", sa.Integer(), nullable=False),
        sa.Column("failed_chunks", sa.Integer(), nullable=False),
        sa.Column("stale_chunks", sa.Integer(), nullable=False),
        sa.Column("orphan_embeddings", sa.Integer(), nullable=False),
        sa.Column("duplicate_embeddings", sa.Integer(), nullable=False),
        sa.Column("total_tokens_embedded", sa.Integer(), nullable=False),
        sa.Column("avg_dimension", sa.Float(), nullable=False),
        sa.Column("avg_tokens_per_chunk", sa.Float(), nullable=False),
        sa.Column("avg_embedding_latency_ms", sa.Float(), nullable=False),
        sa.Column("total_embeddings_generated", sa.Integer(), nullable=False),
        sa.Column("total_embedding_failures", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["index_id"],
            ["vector_indexes.id"],
            name="fk_embedding_statistics_index_id_vector_indexes",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_embedding_statistics"),
        sa.UniqueConstraint(
            "index_id",
            "period",
            "stats_date",
            name="uq_embedding_statistics_index_period_date",
        ),
    )
    op.create_index("ix_embedding_statistics_public_id", "embedding_statistics", ["public_id"], unique=True)
    op.create_index("ix_embedding_statistics_id", "embedding_statistics", ["id"], unique=False)
    op.create_index("ix_embedding_statistics_index_id", "embedding_statistics", ["index_id"], unique=False)
    op.create_index("ix_embedding_statistics_period_date", "embedding_statistics", ["period", "stats_date"], unique=False)
    op.create_index("ix_embedding_statistics_index_period", "embedding_statistics", ["index_id", "period"], unique=False)


def downgrade() -> None:
    op.drop_table("embedding_statistics")
    op.drop_table("embedding_batches")
    op.drop_table("embedding_jobs")
    op.drop_table("embedding_metadata")
    op.drop_table("vector_index_versions")
    op.drop_table("vector_indexes")
    op.drop_table("chunk_relationships")
    op.drop_table("chunk_embeddings")
    op.drop_table("document_chunks")
    op.drop_table("chunk_sections")
