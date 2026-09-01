"""WS2 PostgreSQL parity additions (Phase 2)

Revision ID: 0026_ws2_pg_parity
Revises: 0025_fk_indexes
Create Date: 2026-09-01 00:00:00.000000

Closes gaps between the Alembic lineage and the ORM metadata that only become
visible when migrations run against a real PostgreSQL database:

* ``concepts`` — the VisualCanvasRepository table existed only in ORM metadata
  (``metadata.create_all``) and was never migrated; created here to match the
  ``Concept`` model (native ``jsonb`` for ``prerequisites``/``source_references``).

* ``learning_events`` — the legacy ``0009`` shape used ``payload`` and omitted
  the modern ``LearningEvent`` columns. The missing columns (``resource_type``,
  ``resource_id``, ``concept_id``, ``presentation_id``, ``metadata_json``,
  ``occurred_at``) are ADDED here as native jsonb where appropriate. The legacy
  ``0009`` columns are deliberately left in place (dormant) to avoid destructive
  drops on populated databases; that residual drift is documented in the P2
  report rather than papered over.

* ``user_answers.order_values`` — declared PortableJSONB on ``UserAnswer`` but
  never migrated; added as native jsonb.

* ``questions.concept_id`` — declared on ``Question`` (UUID, indexed) but never
  migrated; added so quiz inserts work against a migrated database.

* ``answer_keys.public_id`` — the ``0005`` migration kept a NOT NULL
  ``public_id`` column that the current ``AnswerKey`` model no longer manages;
  relaxed to nullable in ``0026`` so inserts work (the ORM never reads/writes
  it; the residual column is documented in the P2 report).

Everything here is additive, so it also applies cleanly to the production
database (which is currently at ``0018_topic_outlines``).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision = "0026_ws2_pg_parity"
down_revision = "0025_fk_indexes"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    """True when the table exists on the current connection."""
    return inspect(op.get_bind()).has_table(name)


def _column_names(table: str) -> set[str]:
    return {c["name"] for c in inspect(op.get_bind()).get_columns(table)}


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    if column.name not in _column_names(table):
        op.add_column(table, column)


def upgrade() -> None:
    # ── concepts (VisualCanvasRepository) ──────────────────────────────────────
    if not _table_exists("concepts"):
        op.create_table(
            "concepts",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("public_id", sa.String(length=40), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("topic", sa.String(length=200), nullable=True),
            sa.Column("presentation_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("lesson_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column(
                "difficulty_level",
                sa.String(length=20),
                nullable=False,
                server_default="intermediate",
            ),
            sa.Column("prerequisites", postgresql.JSONB(), nullable=True),
            sa.Column("source_references", postgresql.JSONB(), nullable=True),
            sa.Column(
                "status", sa.String(length=20), nullable=False, server_default="active"
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["presentation_id"],
                ["presentations.id"],
                name="fk_concepts_presentation_id_presentations",
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["lesson_id"],
                ["generated_lessons.id"],
                name="fk_concepts_lesson_id_generated_lessons",
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("id", name="pk_concepts"),
            sa.UniqueConstraint(
                "presentation_id", "name", name="uq_concepts_presentation_name"
            ),
        )
        op.create_index("ix_concepts_id", "concepts", ["id"], unique=False)
        op.create_index("ix_concepts_public_id", "concepts", ["public_id"], unique=True)
        op.create_index("ix_concepts_presentation_id", "concepts", ["presentation_id"], unique=False)
        op.create_index("ix_concepts_lesson_id", "concepts", ["lesson_id"], unique=False)
        op.create_index("ix_concepts_topic", "concepts", ["topic"], unique=False)

    # ── learning_events: add the modern LearningEvent columns ──────────────────
    if _table_exists("learning_events"):
        _add_column_if_missing(
            "learning_events", sa.Column("resource_type", sa.String(length=50), nullable=True)
        )
        _add_column_if_missing(
            "learning_events", sa.Column("resource_id", sa.String(length=100), nullable=True)
        )
        _add_column_if_missing(
            "learning_events", sa.Column("concept_id", sa.String(length=100), nullable=True)
        )
        _add_column_if_missing(
            "learning_events", sa.Column("presentation_id", postgresql.UUID(as_uuid=True), nullable=True)
        )
        _add_column_if_missing(
            "learning_events", sa.Column("metadata_json", postgresql.JSONB(), nullable=True)
        )
        _add_column_if_missing(
            "learning_events",
            sa.Column(
                "occurred_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
        )
        op.create_index(
            "ix_learning_events_presentation",
            "learning_events",
            ["presentation_id"],
            unique=False,
            if_not_exists=True,
        )
        op.create_index(
            "ix_learning_events_user_occurred",
            "learning_events",
            ["user_id", "occurred_at"],
            unique=False,
            if_not_exists=True,
        )

    # ── user_answers: add the missing PortableJSONB column ─────────────────────
    if _table_exists("user_answers"):
        _add_column_if_missing(
            "user_answers", sa.Column("order_values", postgresql.JSONB(), nullable=True)
        )

    # ── questions: add the missing concept_id column ────────────────────────────
    if _table_exists("questions"):
        _add_column_if_missing(
            "questions", sa.Column("concept_id", postgresql.UUID(as_uuid=True), nullable=True)
        )
        op.create_index(
            "ix_questions_concept_id",
            "questions",
            ["concept_id"],
            unique=False,
            if_not_exists=True,
        )

    # ── answer_keys: the ORM no longer manages public_id — relax it ─────────────
    if _table_exists("answer_keys"):
        op.alter_column("answer_keys", "public_id", nullable=True)
        # Model maps scoring_rule as nullable; migration 0005 declared NOT NULL.
        op.alter_column("answer_keys", "scoring_rule", nullable=True)

    # ── question_explanations: same legacy NOT NULL public_id pattern ──────────
    if _table_exists("question_explanations"):
        op.alter_column("question_explanations", "public_id", nullable=True)


def downgrade() -> None:
    if _table_exists("concepts"):
        op.drop_table("concepts")
    if _table_exists("learning_events"):
        for column in (
            "occurred_at",
            "metadata_json",
            "presentation_id",
            "concept_id",
            "resource_id",
            "resource_type",
        ):
            if column in _column_names("learning_events"):
                op.drop_column("learning_events", column)
    if _table_exists("user_answers") and "order_values" in _column_names("user_answers"):
        op.drop_column("user_answers", "order_values")
    if _table_exists("questions") and "concept_id" in _column_names("questions"):
        op.drop_column("questions", "concept_id")
    if _table_exists("answer_keys"):
        bind = op.get_bind()
        for column in ("public_id", "scoring_rule"):
            if column in _column_names("answer_keys") and not bind.execute(
                sa.text(
                    f"SELECT 1 FROM answer_keys WHERE {column} IS NULL LIMIT 1"
                )
            ).first():
                op.alter_column("answer_keys", column, nullable=False)
    if _table_exists("question_explanations") and "public_id" in _column_names("question_explanations"):
        bind = op.get_bind()
        if not bind.execute(
            sa.text(
                "SELECT 1 FROM question_explanations "
                "WHERE public_id IS NULL LIMIT 1"
            )
        ).first():
            op.alter_column("question_explanations", "public_id", nullable=False)
