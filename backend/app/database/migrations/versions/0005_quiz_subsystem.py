"""quiz subsystem

Revision ID: 0005_quiz_subsystem
Revises: 0004_generated_lessons
Create Date: 2026-08-03 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_quiz_subsystem"
down_revision = "0004_generated_lessons"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "quizzes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("presentation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lesson_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lesson_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("difficulty", sa.String(length=20), nullable=True),
        sa.Column("language", sa.String(length=10), nullable=True),
        sa.Column("passing_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("time_limit_minutes", sa.Integer(), nullable=True),
        sa.Column("shuffle_questions", sa.Boolean(), nullable=False),
        sa.Column("shuffle_options", sa.Boolean(), nullable=False),
        sa.Column("show_feedback_after", sa.Boolean(), nullable=False),
        sa.Column("max_attempts_per_user", sa.Integer(), nullable=False),
        sa.Column("latest_version", sa.Integer(), nullable=False),
        sa.Column("published_version", sa.Integer(), nullable=True),
        sa.Column("question_count", sa.Integer(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_state", sa.String(length=20), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["presentation_id"],
            ["presentations.id"],
            name="fk_quizzes_presentation_id_presentations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_quizzes_user_id_users",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["generated_lessons.id"],
            name="fk_quizzes_lesson_id_generated_lessons",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["lesson_version_id"],
            ["generated_lesson_versions.id"],
            name="fk_quizzes_lesson_version_id_generated_lesson_versions",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_quizzes"),
    )
    op.create_index("ix_quizzes_public_id", "quizzes", ["public_id"], unique=True)
    op.create_index("ix_quizzes_id", "quizzes", ["id"], unique=False)
    op.create_index("ix_quizzes_presentation_id", "quizzes", ["presentation_id"], unique=False)
    op.create_index("ix_quizzes_user_id", "quizzes", ["user_id"], unique=False)
    op.create_index("ix_quizzes_status", "quizzes", ["status"], unique=False)
    op.create_index("ix_quizzes_lesson_id", "quizzes", ["lesson_id"], unique=False)
    op.create_index("ix_quizzes_presentation_status", "quizzes", ["presentation_id", "status"], unique=False)
    op.create_index(
        "uq_quizzes_user_idempotency",
        "quizzes",
        ["user_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    op.create_table(
        "quiz_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("quiz_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("language", sa.String(length=10), nullable=True),
        sa.Column("difficulty", sa.String(length=20), nullable=True),
        sa.Column("lesson_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider", sa.String(length=30), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("request_id", sa.String(length=40), nullable=True),
        sa.Column("correlation_id", sa.String(length=40), nullable=True),
        sa.Column("prompt_version", sa.String(length=32), nullable=True),
        sa.Column("payload_schema_version", sa.String(length=32), nullable=True),
        sa.Column("prompt_hash", sa.String(length=64), nullable=True),
        sa.Column("payload_hash", sa.String(length=64), nullable=True),
        sa.Column("generation_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_cost", sa.Numeric(10, 6), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("provider_retry_count", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("validation_status", sa.String(length=20), nullable=True),
        sa.Column("validation_issues", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("validation_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("validation_version", sa.String(length=32), nullable=True),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("quality_issues", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("quality_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("quality_version", sa.String(length=32), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["quiz_id"],
            ["quizzes.id"],
            name="fk_quiz_versions_quiz_id_quizzes",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["lesson_version_id"],
            ["generated_lesson_versions.id"],
            name="fk_quiz_versions_lesson_version_id_generated_lesson_versions",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_quiz_versions"),
        sa.UniqueConstraint(
            "quiz_id",
            "version",
            name="uq_quiz_versions_quiz_version",
        ),
    )
    op.create_index("ix_quiz_versions_public_id", "quiz_versions", ["public_id"], unique=True)
    op.create_index("ix_quiz_versions_id", "quiz_versions", ["id"], unique=False)
    op.create_index("ix_quiz_versions_quiz_id", "quiz_versions", ["quiz_id"], unique=False)
    op.create_index("ix_quiz_versions_status", "quiz_versions", ["status"], unique=False)

    op.create_table(
        "quiz_metadata",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("quiz_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("meta_schema_version", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["quiz_version_id"],
            ["quiz_versions.id"],
            name="fk_quiz_metadata_quiz_version_id_quiz_versions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_quiz_metadata"),
    )
    op.create_index("ix_quiz_metadata_public_id", "quiz_metadata", ["public_id"], unique=True)
    op.create_index("ix_quiz_metadata_id", "quiz_metadata", ["id"], unique=False)
    op.create_index("ix_quiz_metadata_quiz_version_id", "quiz_metadata", ["quiz_version_id"], unique=True)

    op.create_table(
        "questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("quiz_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("question_type", sa.String(length=30), nullable=False),
        sa.Column("stem", sa.Text(), nullable=False),
        sa.Column("bloom_level", sa.String(length=20), nullable=True),
        sa.Column("difficulty", sa.String(length=20), nullable=True),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("scenario_context", sa.Text(), nullable=True),
        sa.Column("source_ref", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("updated_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["quiz_version_id"],
            ["quiz_versions.id"],
            name="fk_questions_quiz_version_id_quiz_versions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_questions"),
        sa.UniqueConstraint(
            "quiz_version_id",
            "position",
            name="uq_questions_version_position",
        ),
    )
    op.create_index("ix_questions_public_id", "questions", ["public_id"], unique=True)
    op.create_index("ix_questions_id", "questions", ["id"], unique=False)
    op.create_index("ix_questions_quiz_version_id", "questions", ["quiz_version_id"], unique=False)
    op.create_index("ix_questions_version_type", "questions", ["quiz_version_id", "question_type"], unique=False)
    op.create_index("ix_questions_version_bloom", "questions", ["quiz_version_id", "bloom_level"], unique=False)
    op.create_index("ix_questions_version_difficulty", "questions", ["quiz_version_id", "difficulty"], unique=False)

    op.create_table(
        "question_options",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=True),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            name="fk_question_options_question_id_questions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_question_options"),
        sa.UniqueConstraint(
            "question_id",
            "position",
            name="uq_question_options_question_position",
        ),
    )
    op.create_index("ix_question_options_public_id", "question_options", ["public_id"], unique=True)
    op.create_index("ix_question_options_id", "question_options", ["id"], unique=False)
    op.create_index("ix_question_options_question_id", "question_options", ["question_id"], unique=False)

    op.create_table(
        "answer_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("answer_type", sa.String(length=30), nullable=False),
        sa.Column("correct_option_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("correct_text", sa.Text(), nullable=True),
        sa.Column("acceptable_answers", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("matching_pairs", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("correct_order", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("scoring_rule", sa.String(length=20), nullable=False),
        sa.Column("points_override", sa.Integer(), nullable=True),
        sa.Column("case_sensitive", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            name="fk_answer_keys_question_id_questions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_answer_keys"),
    )
    op.create_index("ix_answer_keys_public_id", "answer_keys", ["public_id"], unique=True)
    op.create_index("ix_answer_keys_id", "answer_keys", ["id"], unique=False)
    op.create_index("ix_answer_keys_question_id", "answer_keys", ["question_id"], unique=True)

    op.create_table(
        "question_explanations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("reference", sa.Text(), nullable=True),
        sa.Column("display_timing", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            name="fk_question_explanations_question_id_questions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_question_explanations"),
    )
    op.create_index("ix_question_explanations_public_id", "question_explanations", ["public_id"], unique=True)
    op.create_index("ix_question_explanations_id", "question_explanations", ["id"], unique=False)
    op.create_index("ix_question_explanations_question_id", "question_explanations", ["question_id"], unique=False)

    op.create_table(
        "quiz_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("quiz_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quiz_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("score", sa.Numeric(8, 2), nullable=True),
        sa.Column("max_score", sa.Numeric(8, 2), nullable=False),
        sa.Column("percent_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("time_spent_seconds", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("is_practice", sa.Boolean(), nullable=False),
        sa.Column("client_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("graded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["quiz_id"],
            ["quizzes.id"],
            name="fk_quiz_attempts_quiz_id_quizzes",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["quiz_version_id"],
            ["quiz_versions.id"],
            name="fk_quiz_attempts_quiz_version_id_quiz_versions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_quiz_attempts_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_quiz_attempts"),
        sa.UniqueConstraint(
            "quiz_version_id",
            "user_id",
            "attempt_number",
            name="uq_quiz_attempts_version_user_number",
        ),
    )
    op.create_index("ix_quiz_attempts_public_id", "quiz_attempts", ["public_id"], unique=True)
    op.create_index("ix_quiz_attempts_id", "quiz_attempts", ["id"], unique=False)
    op.create_index("ix_quiz_attempts_quiz_id", "quiz_attempts", ["quiz_id"], unique=False)
    op.create_index("ix_quiz_attempts_quiz_version_id", "quiz_attempts", ["quiz_version_id"], unique=False)
    op.create_index("ix_quiz_attempts_user_id", "quiz_attempts", ["user_id"], unique=False)
    op.create_index("ix_quiz_attempts_started_at", "quiz_attempts", ["started_at"], unique=False)
    op.create_index("ix_quiz_attempts_quiz_user", "quiz_attempts", ["quiz_id", "user_id"], unique=False)
    op.create_index("ix_quiz_attempts_version_status", "quiz_attempts", ["quiz_version_id", "status"], unique=False)
    op.create_index(
        "uq_quiz_attempts_user_idempotency",
        "quiz_attempts",
        ["user_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    op.create_table(
        "question_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=True),
        sa.Column("points_earned", sa.Numeric(8, 2), nullable=False),
        sa.Column("points_possible", sa.Numeric(8, 2), nullable=False),
        sa.Column("time_spent_seconds", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("feedback", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["quiz_attempts.id"],
            name="fk_question_attempts_attempt_id_quiz_attempts",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            name="fk_question_attempts_question_id_questions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_question_attempts"),
        sa.UniqueConstraint(
            "attempt_id",
            "question_id",
            name="uq_question_attempts_attempt_question",
        ),
    )
    op.create_index("ix_question_attempts_public_id", "question_attempts", ["public_id"], unique=True)
    op.create_index("ix_question_attempts_id", "question_attempts", ["id"], unique=False)
    op.create_index("ix_question_attempts_attempt_id", "question_attempts", ["attempt_id"], unique=False)
    op.create_index("ix_question_attempts_question_id", "question_attempts", ["question_id"], unique=False)
    op.create_index("ix_question_attempts_attempt_position", "question_attempts", ["attempt_id", "position"], unique=False)

    op.create_table(
        "student_answers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_attempt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("answer_type", sa.String(length=30), nullable=False),
        sa.Column("option_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("text_value", sa.Text(), nullable=True),
        sa.Column("matching_pairs", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("order", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_auto_graded", sa.Boolean(), nullable=False),
        sa.Column("grading_status", sa.String(length=20), nullable=False),
        sa.Column("graded_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("graded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["quiz_attempts.id"],
            name="fk_student_answers_attempt_id_quiz_attempts",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["question_attempt_id"],
            ["question_attempts.id"],
            name="fk_student_answers_question_attempt_id_question_attempts",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_student_answers"),
    )
    op.create_index("ix_student_answers_public_id", "student_answers", ["public_id"], unique=True)
    op.create_index("ix_student_answers_id", "student_answers", ["id"], unique=False)
    op.create_index("ix_student_answers_attempt_id", "student_answers", ["attempt_id"], unique=False)
    op.create_index("ix_student_answers_question_attempt_id", "student_answers", ["question_attempt_id"], unique=True)

    op.create_table(
        "score_summaries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("total_points", sa.Numeric(8, 2), nullable=False),
        sa.Column("earned_points", sa.Numeric(8, 2), nullable=False),
        sa.Column("percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("correct_count", sa.Integer(), nullable=False),
        sa.Column("incorrect_count", sa.Integer(), nullable=False),
        sa.Column("partially_correct_count", sa.Integer(), nullable=False),
        sa.Column("unanswered_count", sa.Integer(), nullable=False),
        sa.Column("breakdown", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("graded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scoring_version", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["quiz_attempts.id"],
            name="fk_score_summaries_attempt_id_quiz_attempts",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_score_summaries"),
    )
    op.create_index("ix_score_summaries_public_id", "score_summaries", ["public_id"], unique=True)
    op.create_index("ix_score_summaries_id", "score_summaries", ["id"], unique=False)
    op.create_index("ix_score_summaries_attempt_id", "score_summaries", ["attempt_id"], unique=True)

    op.create_table(
        "difficulty_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("base_difficulty", sa.String(length=20), nullable=False),
        sa.Column("estimated_difficulty", sa.Float(), nullable=True),
        sa.Column("discrimination", sa.Float(), nullable=True),
        sa.Column("guess_factor", sa.Float(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("correct_count", sa.Integer(), nullable=False),
        sa.Column("accuracy", sa.Numeric(5, 2), nullable=True),
        sa.Column("avg_time_seconds", sa.Float(), nullable=False),
        sa.Column("p_value", sa.Numeric(5, 2), nullable=True),
        sa.Column("calibration_version", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            name="fk_difficulty_profiles_question_id_questions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_difficulty_profiles"),
    )
    op.create_index("ix_difficulty_profiles_public_id", "difficulty_profiles", ["public_id"], unique=True)
    op.create_index("ix_difficulty_profiles_id", "difficulty_profiles", ["id"], unique=False)
    op.create_index("ix_difficulty_profiles_question_id", "difficulty_profiles", ["question_id"], unique=True)

    op.create_table(
        "quiz_version_stats",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=40), nullable=False),
        sa.Column("quiz_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("completed_count", sa.Integer(), nullable=False),
        sa.Column("completion_rate", sa.Numeric(5, 2), nullable=True),
        sa.Column("avg_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("avg_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("question_stats", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("difficulty_trend", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("bloom_distribution", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("last_aggregated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("aggregation_version", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["quiz_version_id"],
            ["quiz_versions.id"],
            name="fk_quiz_version_stats_quiz_version_id_quiz_versions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_quiz_version_stats"),
    )
    op.create_index("ix_quiz_version_stats_public_id", "quiz_version_stats", ["public_id"], unique=True)
    op.create_index("ix_quiz_version_stats_id", "quiz_version_stats", ["id"], unique=False)
    op.create_index("ix_quiz_version_stats_quiz_version_id", "quiz_version_stats", ["quiz_version_id"], unique=True)


def downgrade() -> None:
    op.drop_table("quiz_version_stats")
    op.drop_table("difficulty_profiles")
    op.drop_table("score_summaries")
    op.drop_table("student_answers")
    op.drop_table("question_attempts")
    op.drop_table("quiz_attempts")
    op.drop_table("question_explanations")
    op.drop_table("answer_keys")
    op.drop_table("question_options")
    op.drop_table("questions")
    op.drop_table("quiz_metadata")
    op.drop_table("quiz_versions")
    op.drop_table("quizzes")
