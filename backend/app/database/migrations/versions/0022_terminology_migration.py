"""Rename legacy student/teacher tables to universal terminology.

Tables renamed:
  student_answers          → user_answers
  student_analytics_snapshots → learning_analytics_snapshots
  teacher_analytics_snapshots → creator_analytics_snapshots

Revision ID: 0022_terminology
"""

from alembic import context, op
from sqlalchemy import inspect

revision = "0022_terminology"
down_revision = "0021_assistant_tables"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    """True when the table exists on the current connection.

    Offline rendering has no live connection, so it emits the unconditional
    SQL (matching the pre-guard output).
    """
    if context.is_offline_mode():
        return True
    return inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    # ── student_answers → user_answers ─────────────────────────────────────────
    op.rename_table("student_answers", "user_answers")
    op.execute(
        "ALTER INDEX IF EXISTS pk_student_answers RENAME TO pk_user_answers"
    )
    op.execute(
        "ALTER INDEX IF EXISTS ix_student_answers_public_id RENAME TO ix_user_answers_public_id"
    )
    op.execute(
        "ALTER INDEX IF EXISTS ix_student_answers_id RENAME TO ix_user_answers_id"
    )
    op.execute(
        "ALTER INDEX IF EXISTS ix_student_answers_attempt_id RENAME TO ix_user_answers_attempt_id"
    )
    op.execute(
        "ALTER INDEX IF EXISTS ix_student_answers_question_attempt_id RENAME TO ix_user_answers_question_attempt_id"
    )
    op.execute(
        "ALTER INDEX IF EXISTS fk_student_answers_attempt_id_quiz_attempts RENAME TO fk_user_answers_attempt_id_quiz_attempts"
    )
    op.execute(
        "ALTER INDEX IF EXISTS fk_student_answers_question_attempt_id_question_attempts RENAME TO fk_user_answers_question_attempt_id_question_attempts"
    )

    # ── student_analytics_snapshots → learning_analytics_snapshots ──────────────
    if _table_exists("student_analytics_snapshots"):
        op.rename_table("student_analytics_snapshots", "learning_analytics_snapshots")
        op.execute(
            "ALTER INDEX IF EXISTS ix_student_analytics_user_date RENAME TO ix_learning_analytics_user_date"
        )

    # ── teacher_analytics_snapshots → creator_analytics_snapshots ───────────────
    if _table_exists("teacher_analytics_snapshots"):
        op.rename_table("teacher_analytics_snapshots", "creator_analytics_snapshots")


def downgrade() -> None:
    if _table_exists("creator_analytics_snapshots"):
        op.rename_table("creator_analytics_snapshots", "teacher_analytics_snapshots")
    if _table_exists("learning_analytics_snapshots"):
        op.rename_table("learning_analytics_snapshots", "student_analytics_snapshots")
        op.execute(
            "ALTER INDEX IF EXISTS ix_learning_analytics_user_date RENAME TO ix_student_analytics_user_date"
        )
    op.rename_table("user_answers", "student_answers")
    op.execute(
        "ALTER INDEX IF EXISTS pk_user_answers RENAME TO pk_student_answers"
    )
    op.execute(
        "ALTER INDEX IF EXISTS ix_user_answers_public_id RENAME TO ix_student_answers_public_id"
    )
    op.execute(
        "ALTER INDEX IF EXISTS ix_user_answers_id RENAME TO ix_student_answers_id"
    )
    op.execute(
        "ALTER INDEX IF EXISTS ix_user_answers_attempt_id RENAME TO ix_student_answers_attempt_id"
    )
    op.execute(
        "ALTER INDEX IF EXISTS ix_user_answers_question_attempt_id RENAME TO ix_student_answers_question_attempt_id"
    )
    op.execute(
        "ALTER INDEX IF EXISTS fk_user_answers_attempt_id_quiz_attempts RENAME TO fk_student_answers_attempt_id_quiz_attempts"
    )
    op.execute(
        "ALTER INDEX IF EXISTS fk_user_answers_question_attempt_id_question_attempts RENAME TO fk_student_answers_question_attempt_id_question_attempts"
    )
