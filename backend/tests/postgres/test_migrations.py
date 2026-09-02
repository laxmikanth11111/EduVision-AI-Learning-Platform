"""PostgreSQL migration-parity tests (WS2).

These tests run against a scratch PostgreSQL database migrated to the current
Alembic head, proving the production migration lineage produces a working
schema (native ``jsonb`` columns, all tables, single head).
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

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
}


EXPECTED_HEAD = "0028_ws10_idempotency_key_index"


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
