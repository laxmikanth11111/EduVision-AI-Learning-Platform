"""Quiz API request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

# ── Quiz ─────────────────────────────────────────────────────────────────────


class QuizSummary(BaseModel):
    """Compact quiz representation for list views."""

    id: str
    title: str | None = None
    description: str | None = None
    status: str
    mode: str
    difficulty: str | None = None
    question_count: int
    attempt_count: int
    max_attempts_per_user: int
    time_limit_minutes: int | None = None
    passing_score: float | None = None
    presentation_id: str
    created_at: datetime


class QuizDetail(BaseModel):
    """Full quiz representation."""

    id: str
    title: str | None = None
    description: str | None = None
    status: str
    mode: str
    difficulty: str | None = None
    language: str | None = None
    question_count: int
    attempt_count: int
    max_attempts_per_user: int
    time_limit_minutes: int | None = None
    passing_score: float | None = None
    shuffle_questions: bool
    shuffle_options: bool
    show_feedback_after: bool
    presentation_id: str
    lesson_id: str | None = None
    created_at: datetime


# ── Questions (delivery — no answers) ────────────────────────────────────────


class QuizOptionResponse(BaseModel):
    """A single answer option (no correctness revealed during delivery)."""

    id: str
    position: int
    text: str


class QuizQuestionResponse(BaseModel):
    """A question as presented to the learner during an attempt."""

    id: str
    position: int
    question_type: str
    stem: str
    bloom_level: str | None = None
    difficulty: str | None = None
    points: int
    scenario_context: str | None = None
    options: list[QuizOptionResponse] = []


# ── Attempt ──────────────────────────────────────────────────────────────────


class StartAttemptResponse(BaseModel):
    """Returned when an attempt is started."""

    attempt_id: str
    quiz_id: str
    quiz_version_id: str
    attempt_number: int
    status: str
    started_at: datetime
    questions: list[QuizQuestionResponse]
    adaptive: bool = False
    adaptive_rationale: str | None = None


class StartAttemptRequest(BaseModel):
    """Request body for starting an attempt."""

    adaptive: bool = False


class AnswerSubmission(BaseModel):
    """A single answer within a bulk submission."""

    question_id: str
    option_ids: list[str] | None = None
    text_value: str | None = None
    matching_pairs: list[dict[str, str]] | None = None
    order_values: list[str] | None = None


class SubmitQuizRequest(BaseModel):
    """Request body for submitting all answers at once."""

    answers: list[AnswerSubmission]
    time_spent_seconds: int | None = Field(None, ge=0)


class SingleAnswerRequest(BaseModel):
    """Request body for answering a single question."""

    option_ids: list[str] | None = None
    text_value: str | None = None
    matching_pairs: list[dict[str, str]] | None = None
    order_values: list[str] | None = None
    time_spent_seconds: int | None = Field(None, ge=0)


class NextQuestionRequest(BaseModel):
    """Request body for fetching the next delivery question.

    ``answer`` is optional: when the learner has just finished a question, its
    answer is persisted through this call so within-attempt adaptation reacts
    to it before the next question is selected.
    """

    answer: AnswerSubmission | None = None


class NextQuestionResponse(BaseModel):
    """The next question to present during an in-progress attempt."""

    attempt_id: str
    quiz_id: str
    adaptive: bool = False
    adaptive_rationale: str | None = None
    next_question: QuizQuestionResponse | None = None
    answered_count: int = 0
    remaining_count: int = 0
    completed: bool = False


class QuestionFeedback(BaseModel):
    """Per-question feedback after submission."""

    question_id: str
    position: int
    is_correct: bool | None = None
    points_earned: float
    points_possible: float
    explanation: str | None = None
    correct_answer: Any = None
    concept_id: str | None = None
    concept_name: str | None = None


class ScoreBreakdown(BaseModel):
    """Aggregate score breakdown."""

    total_points: float
    earned_points: float
    percent: float
    correct_count: int
    incorrect_count: int
    partially_correct_count: int
    unanswered_count: int


class AttemptResult(BaseModel):
    """Full result of a completed quiz attempt."""

    attempt_id: str
    quiz_id: str
    lesson_id: str | None = None
    status: str
    attempt_number: int
    score: float | None = None
    max_score: float | None = None
    percent_score: float | None = None
    time_spent_seconds: int | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    passed: bool | None = None
    score_breakdown: ScoreBreakdown | None = None
    question_feedback: list[QuestionFeedback] = []
    recommendations: dict[str, Any] | None = None


class AttemptSummary(BaseModel):
    """Compact attempt representation for list views."""

    attempt_id: str
    quiz_id: str
    status: str
    attempt_number: int
    score: float | None = None
    max_score: float | None = None
    percent_score: float | None = None
    time_spent_seconds: int | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    passed: bool | None = None


# ── Quiz Generation ─────────────────────────────────────────────────────────


class GenerateQuizRequest(BaseModel):
    """Request body for AI-powered quiz generation from a lesson."""

    lesson_id: str
    num_questions: int = Field(default=5, ge=1, le=20)
    difficulty: str = Field(default="intermediate")


class GenerateQuizResponse(BaseModel):
    """Response after quiz generation."""

    quiz_id: str
    title: str | None = None
    question_count: int
    status: str
