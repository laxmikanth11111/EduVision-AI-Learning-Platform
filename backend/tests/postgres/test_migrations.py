"""PostgreSQL migration-parity tests (WS2).

These tests run against a scratch PostgreSQL database migrated to the current
Alembic head, proving the production migration lineage produces a working
schema (native ``jsonb`` columns, all tables, single head).
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.postgres.conftest import expected_migration_head

pytestmark = pytest.mark.postgres

# Columns converted to PortableJSONB in WS1 — each must be a native PG jsonb column.
EXPECTED_JSONB_COLUMNS: set[tuple[str, str]] = {
    ("answer_keys", "correct_option_ids"),
    ("answer_keys", "acceptable_answers"),
    ("answer_keys", "matching_pairs"),
    ("answer_keys", "correct_order"),
    ("effectiveness_assessments", "baseline_concept_scores"),
    ("effectiveness_assessments", "post_concept_scores"),
    ("effectiveness_assessments", "retention_concept_scores"),
    ("effectiveness_assessments", "events_summary"),
    ("learning_events", "metadata_json"),
    ("questions", "meta"),
    ("question_options", "meta"),
    ("quiz_versions", "generation_metadata"),
    ("score_summaries", "breakdown"),
    ("user_answers", "option_ids"),
    ("user_answers", "matching_pairs"),
("user_answers", "order_values"),
    ("user_feedback", "extra_json"),
    ("educational_memories", "memory_data"),
}

EXPECTED_TABLES: set[str] = {
    "users",
    "presentations",
    "generated_lessons",
    "quizzes",
    "quiz_versions",
    "questions",
    "question_options",
    "quiz_attempts",
    "answer_keys",
    "score_summaries",
    "user_answers",
    "user_feedback",
    "effectiveness_assessments",
    "learning_events",
"learning_sessions",
    "concepts",
    "educational_memories",
    "video_projects",
}


EXPECTED_HEAD = expected_migration_head()


async def test_alembic_revision_is_single_head(pg_engine: AsyncEngine):
    async with pg_engine.connect() as conn:
        row = await conn.execute(text("SELECT version_num FROM alembic_version"))
        assert row.scalar() == EXPECTED_HEAD


async def test_all_production_tables_exist(pg_engine: AsyncEngine):
    async with pg_engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public'"
            )
        )
        tables = {name for (name,) in result.all()}
    missing = EXPECTED_TABLES - tables
    assert not missing, f"tables missing after alembic upgrade head: {sorted(missing)}"


async def test_orm_tables_are_fully_covered_by_migrations(pg_engine: AsyncEngine):
    """Every table the ORM can query must exist after ``alembic upgrade head``.

    The default (SQLite) suites build their schema with ``metadata.create_all``,
    so they derive the schema *from the ORM* and are structurally incapable of
    detecting ORM/DB drift. Only this suite runs the real migration lineage.

    That blind spot had a concrete cost: ``VisualCanvas.lesson_id`` and the
    three ``app/models/analytics.py`` tables existed in the ORM but were never
    created by any migration, and both defects stayed invisible because
    ``EXPECTED_TABLES`` below was a hand-maintained allowlist of 18 tables that
    happened to omit them. Deriving the expectation from ORM metadata makes
    this a real parity gate instead of a spot check.
    """
    from app.models import Base  # noqa: PLC0415  (import registers all models)

    orm_tables = set(Base.metadata.tables)
    async with pg_engine.connect() as conn:
        result = await conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        )
        db_tables = {name for (name,) in result.all()}

    missing = orm_tables - db_tables
    assert not missing, (
        "ORM declares tables that no migration creates "
        f"(they will 500 on a fresh database): {sorted(missing)}"
    )


async def test_orm_columns_exist_for_every_table(pg_engine: AsyncEngine):
    """Catch the narrower ``VisualCanvas.lesson_id`` class of drift.

    A table can exist while one of its ORM columns does not. Because
    SQLAlchemy always emits the full column list in a ``SELECT``, a single
    missing column breaks *every* read of that table, not just the code path
    that happens to use it.
    """
    from app.models import Base  # noqa: PLC0415

    async with pg_engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = 'public'"
            )
        )
        db_columns: dict[str, set[str]] = {}
        for table, column in result.all():
            db_columns.setdefault(table, set()).add(column)

    problems: list[str] = []
    for table_name, table in Base.metadata.tables.items():
        if table_name not in db_columns:
            continue  # reported by test_orm_tables_are_fully_covered_by_migrations
        missing = {c.name for c in table.columns} - db_columns[table_name]
        if missing:
            problems.append(f"{table_name}: {sorted(missing)}")

    assert not problems, (
        "ORM columns absent from the migrated schema: " + "; ".join(sorted(problems))
    )


async def test_jsonb_columns_use_native_pg_jsonb(pg_engine: AsyncEngine):
    async with pg_engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND data_type = 'jsonb'"
            )
        )
        jsonb_columns = {(table, column) for table, column in result.all()}

    # The PortableJSONB WS1 conversion must map to native jsonb on PostgreSQL.
    missing = EXPECTED_JSONB_COLUMNS - jsonb_columns
    assert not missing, (
        f"these columns are NOT native jsonb after migrations: {sorted(missing)}"
    )


async def test_migrations_are_idempotent_only_forward(pg_engine: AsyncEngine):
    """The scratch DB is already at head; verify version is final."""
    async with pg_engine.connect() as conn:
        row = await conn.execute(text("SELECT version_num FROM alembic_version"))
        current = row.scalar()
        assert current == EXPECTED_HEAD
        # Ensure no migration is applied twice in the lineage (single head means
        # no merge branches to drift against).
        result = await conn.execute(
            text("SELECT version_num FROM alembic_version")
        )
        assert result.scalars().all() == [EXPECTED_HEAD]
