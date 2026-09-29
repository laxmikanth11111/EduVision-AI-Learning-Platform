"""Schema-parity fixes: canvas lesson link, event_type width, missing indexes.

Revision ID: 0038_schema_parity_fixes
Revises: 0037_teaching_continuity
Create Date: 2026-09-28 12:00:00.000000

Aligns the live PostgreSQL schema with the SQLAlchemy models where the two had
drifted. Every statement is guarded so the migration is idempotent and safe on a
database that already received the change out-of-band.

1. ``visual_canvases.lesson_id`` — **active breakage**. The ORM column, the
   ``ix_visual_canvases_lesson_id`` index, the ``save_visual_model`` write path
   and ``POST /api/v1/visual/canvases`` all existed, but no migration ever
   created the column: it had only been added to a developer database by a
   manual ``ALTER TABLE``. On any freshly migrated database *every* read of
   ``VisualCanvas`` fails, because SQLAlchemy always selects the full column
   list::

      ProgrammingError: column visual_canvases.lesson_id does not exist

   which took down the whole visual-learning canvas surface, not just the
   lesson-scoped write path.

2. ``learning_events.event_type`` — declared ``String(50)`` in the ORM but
   created ``varchar(40)`` by migration 0009 (migration 0023's ``String(50)``
   definition is dead code on the linear chain because its whole
   ``create_table`` is behind an existence guard). Any event type longer than
   40 characters raised ``value too long for type character varying(40)``.
   Widening the column to 50 aligns the database with the model. In PostgreSQL
   widening ``varchar`` does not rewrite the table.

3. ``ix_learning_events_event_type`` and ``ix_lesson_annotations_lesson_mode``
   — declared in the ORM but never created. Migration 0023's index creation for
   ``learning_events`` sits inside the same guarded block as its unused
   ``create_table``, and migration 0037 never created the annotation composite
   index.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0038_schema_parity_fixes"
down_revision = "0037_teaching_continuity"
branch_labels = None
depends_on = None

CANVASES_TABLE = "visual_canvases"
EVENTS_TABLE = "learning_events"
ANNOTATIONS_TABLE = "lesson_annotations"

_LESSONS_TABLE = "generated_lessons"
_FK_LESSONS = "fk_visual_canvases_lesson_id_generated_lessons"


def _inspector() -> sa.Inspector | None:
    bind = op.get_bind()
    if bind is None:
        return None
    return inspect(bind)


def _table_exists(table: str) -> bool:
    insp = _inspector()
    return True if insp is None else insp.has_table(table)


def _column_exists(table: str, column: str) -> bool:
    insp = _inspector()
    if insp is None:
        return True
    return column in {c["name"] for c in insp.get_columns(table)}


def _index_exists(table: str, index: str) -> bool:
    insp = _inspector()
    if insp is None:
        return False
    return index in {i["name"] for i in insp.get_indexes(table)}


def _fk_exists(table: str, name: str) -> bool:
    insp = _inspector()
    if insp is None:
        return False
    return name in {fk.get("name") for fk in insp.get_foreign_keys(table)}


def _is_postgres() -> bool:
    bind = op.get_bind()
    return bool(bind is not None and bind.dialect.name == "postgresql")


def upgrade() -> None:
    # ── 1. visual_canvases.lesson_id (active breakage on fresh databases) ──
    if _table_exists(CANVASES_TABLE) and not _column_exists(CANVASES_TABLE, "lesson_id"):
        op.add_column(
            CANVASES_TABLE,
            sa.Column("lesson_id", sa.Uuid(as_uuid=True), nullable=True),
        )
        if _table_exists(_LESSONS_TABLE) and not _fk_exists(CANVASES_TABLE, _FK_LESSONS):
            op.create_foreign_key(
                _FK_LESSONS,
                CANVASES_TABLE,
                _LESSONS_TABLE,
                ["lesson_id"],
                ["id"],
                ondelete="SET NULL",
            )
        if not _index_exists(CANVASES_TABLE, "ix_visual_canvases_lesson_id"):
            op.create_index(
                "ix_visual_canvases_lesson_id",
                CANVASES_TABLE,
                ["lesson_id"],
                unique=False,
            )

    # ── 2. learning_events.event_type: varchar(40) -> varchar(50) ──
    # Matches the ORM declaration. Widening varchar is metadata-only in
    # PostgreSQL; on any other backend fall back to a MODIFY/BATCH rewrite.
    if _table_exists(EVENTS_TABLE) and _column_exists(EVENTS_TABLE, "event_type"):
        insp = _inspector()
        width = None
        if insp is not None:
            for c in insp.get_columns(EVENTS_TABLE):
                if c["name"] == "event_type":
                    length = getattr(c["type"], "length", None)
                    if length is not None and int(length) < 50:
                        width = int(length)
                    break
        if width is not None:
            if _is_postgres():
                op.execute(
                    "ALTER TABLE learning_events "
                    "ALTER COLUMN event_type TYPE VARCHAR(50)"
                )
            else:
                with op.batch_alter_table(EVENTS_TABLE) as batch:
                    batch.alter_column(
                        "event_type",
                        existing_type=sa.String(length=width),
                        type_=sa.String(length=50),
                        existing_nullable=False,
                    )

        if not _index_exists(EVENTS_TABLE, "ix_learning_events_event_type"):
            op.create_index(
                "ix_learning_events_event_type",
                EVENTS_TABLE,
                ["event_type"],
                unique=False,
            )

    # ── 3. lesson_annotations composite index (ORM-declared, never created) ──
    if _table_exists(ANNOTATIONS_TABLE) and not _index_exists(
        ANNOTATIONS_TABLE, "ix_lesson_annotations_lesson_mode"
    ):
        op.create_index(
            "ix_lesson_annotations_lesson_mode",
            ANNOTATIONS_TABLE,
            ["lesson_id", "player_mode"],
            unique=False,
        )


def downgrade() -> None:
    if _table_exists(ANNOTATIONS_TABLE) and _index_exists(
        ANNOTATIONS_TABLE, "ix_lesson_annotations_lesson_mode"
    ):
        op.drop_index("ix_lesson_annotations_lesson_mode", table_name=ANNOTATIONS_TABLE)

    if _table_exists(EVENTS_TABLE):
        if _index_exists(EVENTS_TABLE, "ix_learning_events_event_type"):
            op.drop_index("ix_learning_events_event_type", table_name=EVENTS_TABLE)
        if _is_postgres():
            op.execute(
                "ALTER TABLE learning_events "
                "ALTER COLUMN event_type TYPE VARCHAR(40)"
            )

    if _table_exists(CANVASES_TABLE) and _column_exists(CANVASES_TABLE, "lesson_id"):
        if _index_exists(CANVASES_TABLE, "ix_visual_canvases_lesson_id"):
            op.drop_index("ix_visual_canvases_lesson_id", table_name=CANVASES_TABLE)
        if _fk_exists(CANVASES_TABLE, _FK_LESSONS):
            op.drop_constraint(_FK_LESSONS, CANVASES_TABLE, type_="foreignkey")
        op.drop_column(CANVASES_TABLE, "lesson_id")
