"""Missing Foreign-Key Indexes (Phase 1 integrity)

Revision ID: 0025_fk_indexes
Revises: 0024_p3_feedback_and_comparison
Create Date: 2026-09-01 00:00:00.000000

Adds B-tree indexes on foreign-key columns that were referenced in queries but
declared without an index. These are purely additive: indexing an existing
column never fails on populated data and never changes row semantics.

The following columns already have index coverage (column-level ``index=True``,
a standalone ``Index()``, or a unique constraint that provides a backing
unique index) and are intentionally NOT re-indexed here:
* quiz_attempts.quiz_id        -> covered by ix_quiz_attempts_quiz_user
* quiz_versions.quiz_id        -> covered by ix_quiz_versions_quiz_id
* answer_keys.question_id      -> covered by unique constraint
* question_explanations.question_id -> covered by unique constraint
* score_summaries.attempt_id   -> covered by unique constraint

Indexes added:
* question_attempts(question_id)
* quiz_attempts(quiz_version_id)
* quizzes(lesson_version_id)
* user_answers(question_attempt_id)
"""

from __future__ import annotations

from alembic import op

revision = "0025_fk_indexes"
down_revision = "0024_p3_feedback_and_comparison"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_question_attempts_question_id",
        "question_attempts",
        ["question_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "ix_quiz_attempts_quiz_version_id",
        "quiz_attempts",
        ["quiz_version_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "ix_quizzes_lesson_version_id",
        "quizzes",
        ["lesson_version_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "ix_user_answers_question_attempt_id",
        "user_answers",
        ["question_attempt_id"],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_user_answers_question_attempt_id", table_name="user_answers")
    op.drop_index("ix_quizzes_lesson_version_id", table_name="quizzes")
    op.drop_index("ix_quiz_attempts_quiz_version_id", table_name="quiz_attempts")
    op.drop_index("ix_question_attempts_question_id", table_name="question_attempts")
