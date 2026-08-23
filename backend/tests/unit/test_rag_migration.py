from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

from sqlalchemy import UniqueConstraint

from app.database.base import Base

MIGRATIONS_DIR = (
    Path(__file__).resolve().parents[2] / "app" / "database" / "migrations" / "versions"
)

RAG_TABLE_ORDER = [
    "chunk_sections",
    "document_chunks",
    "chunk_embeddings",
    "chunk_relationships",
    "vector_indexes",
    "vector_index_versions",
    "embedding_metadata",
    "embedding_jobs",
    "embedding_batches",
    "embedding_statistics",
]


def _load_migration() -> object:
    module_name = "0012_rag_infrastructure"
    module_path = MIGRATIONS_DIR / f"{module_name}.py"
    assert module_path.exists(), f"migration {module_path} not found"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestRagMigration:
    def test_revision_chain(self) -> None:
        migration = _load_migration()
        assert migration.revision == "0012_rag_infrastructure"
        assert migration.down_revision == "0011_personalized_learning"

    def test_rag_tables_registered_in_models(self) -> None:
        for table in RAG_TABLE_ORDER:
            assert table in Base.metadata.tables, f"{table} missing from model metadata"

    def test_migration_creates_tables_in_plan_order(self) -> None:
        module_path = MIGRATIONS_DIR / "0012_rag_infrastructure.py"
        tree = ast.parse(module_path.read_text(encoding="utf-8"))

        created: list[str] = []
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "create_table"
                and node.args
                and isinstance(node.args[0], ast.Constant)
            ):
                created.append(str(node.args[0].value))

        assert created == RAG_TABLE_ORDER

    def test_migration_downgrade_drops_in_reverse(self) -> None:
        module_path = MIGRATIONS_DIR / "0012_rag_infrastructure.py"
        tree = ast.parse(module_path.read_text(encoding="utf-8"))

        dropped: list[str] = []
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "drop_table"
                and node.args
                and isinstance(node.args[0], ast.Constant)
            ):
                dropped.append(str(node.args[0].value))

        assert dropped == list(reversed(RAG_TABLE_ORDER))

    def test_key_columns_exist_in_models(self) -> None:
        tables = Base.metadata.tables

        for table, cols in {
            "chunk_sections": (
                "presentation_id",
                "lesson_id",
                "parent_id",
                "public_id",
                "section_type",
                "position",
                "level",
                "heading_path",
                "metadata",
                "status",
                "version",
                "deleted_at",
            ),
            "document_chunks": (
                "presentation_id",
                "lesson_id",
                "lesson_version_id",
                "content_unit_id",
                "content_block_id",
                "section_id",
                "parent_chunk_id",
                "chunk_type",
                "source",
                "content",
                "position",
                "level",
                "token_count",
                "character_count",
                "chunk_hash",
                "checksum",
                "language",
                "metadata",
                "status",
                "version",
                "retry_count",
                "max_retries",
                "next_retry_at",
                "retry_state",
                "deleted_at",
            ),
            "chunk_embeddings": (
                "chunk_id",
                "provider",
                "model",
                "dimension",
                "vector",
                "token_count",
                "embedding_hash",
                "checksum",
                "status",
                "version",
                "metadata",
                "deleted_at",
            ),
            "chunk_relationships": (
                "source_chunk_id",
                "target_chunk_id",
                "relationship_type",
                "metadata",
                "status",
            ),
            "vector_indexes": (
                "presentation_id",
                "lesson_id",
                "index_type",
                "status",
                "strategy",
                "chunk_size",
                "chunk_overlap",
                "max_chunk_tokens",
                "provider",
                "model",
                "dimension",
                "chunk_count",
                "embedding_count",
                "total_tokens",
                "source_hash",
                "latest_version",
                "config",
                "started_at",
                "completed_at",
                "error_message",
                "retry_state",
                "version",
                "deleted_at",
            ),
            "vector_index_versions": (
                "index_id",
                "version",
                "status",
                "source_hash",
                "chunk_count",
                "embedding_count",
                "total_tokens",
                "config",
                "changelog",
                "metadata",
                "deleted_at",
            ),
            "embedding_metadata": (
                "index_id",
                "provider",
                "model",
                "dimension",
                "model_version",
                "max_tokens_per_input",
                "supported_languages",
                "config_snapshot",
                "fingerprint",
                "status",
                "version",
                "metadata",
            ),
            "embedding_jobs": (
                "index_id",
                "user_id",
                "presentation_id",
                "lesson_id",
                "job_type",
                "status",
                "priority",
                "idempotency_key",
                "total_items",
                "processed_items",
                "failed_items",
                "payload",
                "result",
                "error_code",
                "error_message",
                "attempt_count",
                "max_attempts",
                "next_retry_at",
                "retry_state",
                "started_at",
                "completed_at",
                "version",
                "deleted_at",
            ),
            "embedding_batches": (
                "job_id",
                "status",
                "sequence",
                "total_items",
                "processed_items",
                "failed_items",
                "request_ids",
                "result",
                "error_code",
                "error_message",
                "started_at",
                "completed_at",
                "version",
                "deleted_at",
            ),
            "embedding_statistics": (
                "index_id",
                "period",
                "stats_date",
                "total_chunks",
                "embedded_chunks",
                "pending_chunks",
                "failed_chunks",
                "stale_chunks",
                "orphan_embeddings",
                "duplicate_embeddings",
                "total_tokens_embedded",
                "avg_dimension",
                "avg_tokens_per_chunk",
                "avg_embedding_latency_ms",
                "total_embeddings_generated",
                "total_embedding_failures",
                "status",
                "version",
            ),
        }.items():
            for col in cols:
                assert col in tables[table].columns, f"{table}.{col} missing"

    def test_unique_constraints_defined(self) -> None:
        tables = Base.metadata.tables
        for table in RAG_TABLE_ORDER:
            public_id_unique = tables[table].c["public_id"].unique
            constraint_has_public_id = any(
                "public_id" in tuple(c.name for c in constraint.columns)
                for constraint in tables[table].constraints
                if isinstance(constraint, UniqueConstraint)
            )
            assert public_id_unique or constraint_has_public_id, (
                f"{table} has no unique public_id constraint"
            )

    def test_foreign_keys_cascade_semantics(self) -> None:
        tables = Base.metadata.tables

        def ondelete(table: str, column: str) -> str:
            fk = tables[table].c[column].foreign_keys
            assert fk, f"{table}.{column} has no FK"
            return next(iter(fk)).ondelete

        assert ondelete("chunk_sections", "presentation_id") == "CASCADE"
        assert ondelete("chunk_sections", "lesson_id") == "CASCADE"
        assert ondelete("chunk_sections", "parent_id") == "CASCADE"
        assert ondelete("document_chunks", "presentation_id") == "CASCADE"
        assert ondelete("document_chunks", "lesson_id") == "CASCADE"
        assert ondelete("document_chunks", "lesson_version_id") == "SET NULL"
        assert ondelete("document_chunks", "content_unit_id") == "SET NULL"
        assert ondelete("document_chunks", "content_block_id") == "SET NULL"
        assert ondelete("document_chunks", "section_id") == "SET NULL"
        assert ondelete("document_chunks", "parent_chunk_id") == "CASCADE"
        assert ondelete("chunk_embeddings", "chunk_id") == "CASCADE"
        assert ondelete("chunk_relationships", "source_chunk_id") == "CASCADE"
        assert ondelete("chunk_relationships", "target_chunk_id") == "CASCADE"
        assert ondelete("vector_indexes", "presentation_id") == "CASCADE"
        assert ondelete("vector_indexes", "lesson_id") == "CASCADE"
        assert ondelete("vector_index_versions", "index_id") == "CASCADE"
        assert ondelete("embedding_metadata", "index_id") == "SET NULL"
        assert ondelete("embedding_jobs", "index_id") == "SET NULL"
        assert ondelete("embedding_jobs", "presentation_id") == "SET NULL"
        assert ondelete("embedding_jobs", "lesson_id") == "SET NULL"
        assert ondelete("embedding_batches", "job_id") == "CASCADE"
        assert ondelete("embedding_statistics", "index_id") == "SET NULL"

    def test_migration_and_model_agree_on_table_count(self) -> None:
        migration = _load_migration()
        upgrade_source = migration.__doc__ or ""
        model_tables = {t for t in Base.metadata.tables if t in set(RAG_TABLE_ORDER)}
        assert model_tables == set(RAG_TABLE_ORDER)
        assert len(RAG_TABLE_ORDER) == 10
        assert upgrade_source
