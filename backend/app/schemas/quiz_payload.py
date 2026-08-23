"""Strict AI JSON contract for quiz generation (``QuizPayload``).

Defines the exact structure the AI model must return. Payloads are parsed with
``QuizPayload.model_validate_json`` (extra fields rejected, per-type answer-key
rules enforced) before any database persistence.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from shared.constants import (
    AnswerType,
    BloomLevel,
    QuestionType,
    QuizDifficulty,
    ScoringRule,
)

MAX_STEM_CHARS = 2000
MAX_OPTION_TEXT_CHARS = 500
MAX_QUESTION_TITLE_CHARS = 500
MAX_QUESTION_DESC_CHARS = 4000
MAX_QUESTION_ID_CHARS = 64
MAX_ANSWER_CHARS = 500
MAX_SCENARIO_CHARS = 4000


class OptionPayload(BaseModel):
    """A single multiple-choice style option.

    ``is_correct`` is ``None`` (absent) for relational question types where
    correctness lives in the answer key.
    """

    model_config = ConfigDict(extra="forbid")

    id: str | None = Field(default=None, max_length=MAX_QUESTION_ID_CHARS)
    text: str = Field(min_length=1, max_length=MAX_OPTION_TEXT_CHARS)
    is_correct: bool | None = None
    meta: dict[str, Any] | None = None


class MatchPairPayload(BaseModel):
    """One left/right pair for a matching question."""

    model_config = ConfigDict(extra="forbid")

    left: str = Field(min_length=1, max_length=MAX_ANSWER_CHARS)
    right: str = Field(min_length=1, max_length=MAX_ANSWER_CHARS)


class AnswerPayload(BaseModel):
    """Type-specific answer key.

    ``answer_type`` is optional for non-scenario questions (defaults to the
    question type); it is required for ``scenario`` questions to declare the
    inner type. Only the fields relevant to the resolved type may be populated.
    """

    model_config = ConfigDict(extra="forbid")

    answer_type: str | None = None
    correct_option_idxs: list[int] | None = None
    value: bool | None = None
    acceptable_answers: list[str] | None = None
    scoring_rule: str | None = None
    case_sensitive: bool = False
    pairs: list[MatchPairPayload] | None = None
    correct_order: list[str] | None = None

    @model_validator(mode="after")
    def _validate_type_specific(self) -> AnswerPayload:
        if self.answer_type is None:
            return self
        try:
            at = AnswerType(self.answer_type)
        except ValueError as exc:
            raise ValueError(f"invalid answer_type: {self.answer_type!r}") from exc

        if at is AnswerType.MULTIPLE_CHOICE and (
            not self.correct_option_idxs or len(self.correct_option_idxs) != 1
        ):
            raise ValueError(
                "multiple_choice requires exactly one correct_option_idx"
            )
        if at is AnswerType.MULTIPLE_SELECT and (
            not self.correct_option_idxs or len(self.correct_option_idxs) < 2
        ):
            raise ValueError(
                "multiple_select requires at least two correct_option_idxs"
            )
        if at is AnswerType.TRUE_FALSE and self.value is None:
            raise ValueError("true_false requires an answer_key.value")
        if at is AnswerType.FILL_BLANK:
            if not self.acceptable_answers:
                raise ValueError("fill_blank requires acceptable_answers")
            if self.scoring_rule not in (ScoringRule.EXACT.value, ScoringRule.REGEX.value):
                raise ValueError(
                    "fill_blank scoring_rule must be 'exact' or 'regex'"
                )
        if at is AnswerType.SHORT_ANSWER:
            if not self.acceptable_answers:
                raise ValueError("short_answer requires acceptable_answers")
            if self.scoring_rule not in (
                ScoringRule.EXACT.value,
                ScoringRule.CONTAINS.value,
                ScoringRule.REGEX.value,
                ScoringRule.FUZZY.value,
            ):
                raise ValueError(
                    "short_answer scoring_rule must be exact, contains, regex or fuzzy"
                )
        if at is AnswerType.MATCHING and (not self.pairs or len(self.pairs) < 2):
            raise ValueError("matching requires at least two pairs")
        if at is AnswerType.ORDERING and (
            not self.correct_order or len(self.correct_order) < 2
        ):
            raise ValueError("ordering requires at least two items")
        return self


class QuestionMetaPayload(BaseModel):
    """Per-question enrichment metadata recorded into ``questions.meta``."""

    model_config = ConfigDict(extra="forbid")

    learning_objective: str | None = Field(default=None, max_length=500)
    estimated_time_seconds: int | None = Field(default=None, ge=1, le=3600)
    topic: str | None = Field(default=None, max_length=200)
    knowledge_area: str | None = Field(default=None, max_length=200)
    reference: str | None = Field(default=None, max_length=500)
    tags: list[str] = []


class QuestionPayload(BaseModel):
    """A single generated question."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=MAX_QUESTION_ID_CHARS)
    type: str
    bloom_level: str | None = None
    difficulty: str | None = None
    stem: str = Field(min_length=1, max_length=MAX_STEM_CHARS)
    points: int = Field(default=1, ge=1, le=100)
    scenario_context: str | None = Field(default=None, max_length=MAX_SCENARIO_CHARS)
    options: list[OptionPayload] | None = None
    answer_key: AnswerPayload
    explanation: str | None = Field(default=None, max_length=4000)
    source_ref: str | None = Field(default=None, max_length=255)
    meta: QuestionMetaPayload | None = None

    @model_validator(mode="after")
    def _validate_cross_field(self) -> QuestionPayload:
        try:
            qtype = QuestionType(self.type)
        except ValueError as exc:
            raise ValueError(f"invalid question type: {self.type!r}") from exc

        if qtype is QuestionType.SCENARIO:
            if not self.scenario_context:
                raise ValueError("scenario questions require scenario_context")
            if not self.answer_key.answer_type:
                raise ValueError(
                    "scenario questions require answer_key.answer_type (inner type)"
                )
            inner = AnswerType(self.answer_key.answer_type)
        else:
            if self.answer_key.answer_type and self.answer_key.answer_type != self.type:
                raise ValueError(
                    "answer_key.answer_type must match the question type"
                )
            inner = AnswerType(self.type)

        # Normalize the answer key so its own type-specific validator runs.
        if self.answer_key.answer_type != inner.value:
            normalized = self.answer_key.model_copy(update={"answer_type": inner.value})
            self.answer_key = AnswerPayload.model_validate(normalized.model_dump())

        options = self.options or []
        ak = self.answer_key

        if inner is AnswerType.MULTIPLE_CHOICE:
            if len(options) < 2:
                raise ValueError("multiple_choice requires at least two options")
            correct = [i for i, o in enumerate(options) if o.is_correct is True]
            if len(correct) != 1:
                raise ValueError("multiple_choice requires exactly one correct option")
            if ak.correct_option_idxs is None or ak.correct_option_idxs[0] not in correct:
                raise ValueError(
                    "answer_key.correct_option_idxs must reference the correct option"
                )
        elif inner is AnswerType.MULTIPLE_SELECT:
            if len(options) < 3:
                raise ValueError("multiple_select requires at least three options")
            correct = [i for i, o in enumerate(options) if o.is_correct is True]
            if len(correct) < 2:
                raise ValueError(
                    "multiple_select requires at least two correct options"
                )
            if ak.correct_option_idxs is None or set(ak.correct_option_idxs) != set(
                correct
            ):
                raise ValueError(
                    "answer_key.correct_option_idxs must match the correct options"
                )
        elif inner is AnswerType.TRUE_FALSE:
            if len(options) != 2:
                raise ValueError("true_false requires exactly two options")
        elif inner in (AnswerType.FILL_BLANK, AnswerType.SHORT_ANSWER):
            if options:
                raise ValueError(f"{inner.value} questions must not define options")
        elif inner is AnswerType.MATCHING:
            if options:
                raise ValueError("matching questions must not define options")
            pairs = ak.pairs or []
            lefts = [p.left for p in pairs]
            rights = [p.right for p in pairs]
            if len(set(lefts)) != len(lefts):
                raise ValueError("matching pairs must have unique left items")
            if len(set(rights)) != len(rights):
                raise ValueError("matching pairs must have unique right items")
        elif inner is AnswerType.ORDERING:
            if options:
                raise ValueError("ordering questions must not define options")
            order = ak.correct_order or []
            if len(set(order)) != len(order):
                raise ValueError("ordering items must be unique")

        if self.bloom_level is not None:
            BloomLevel(self.bloom_level)
        if self.difficulty is not None:
            QuizDifficulty(self.difficulty)
        return self


class ValidationMetadata(BaseModel):
    """Version-level metadata generated alongside the quiz."""

    model_config = ConfigDict(extra="forbid")

    bloom_distribution: dict[str, int] = {}
    estimated_time_seconds: int | None = None
    topic_coverage: list[str] = []
    coverage_summary: str | None = None
    generated_at: datetime | None = None
    validator_version: str | None = None


class QuizPayload(BaseModel):
    """Root AI output contract."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=MAX_QUESTION_TITLE_CHARS)
    description: str | None = Field(default=None, max_length=MAX_QUESTION_DESC_CHARS)
    language: str | None = Field(default=None, max_length=10)
    difficulty: str | None = None
    passing_score: float | None = Field(default=None, ge=0, le=100)
    time_limit_minutes: int | None = Field(default=None, ge=1, le=240)
    shuffle_questions: bool = True
    shuffle_options: bool = True
    show_feedback_after: bool = True
    max_attempts_per_user: int = Field(default=1, ge=1, le=100)
    metadata: ValidationMetadata | None = None
    questions: list[QuestionPayload]

    @model_validator(mode="after")
    def _validate_root(self) -> QuizPayload:
        if not self.questions:
            raise ValueError("payload must contain at least one question")
        ids = [q.id for q in self.questions]
        if len(ids) != len(set(ids)):
            raise ValueError("question ids must be unique")
        if self.difficulty is not None:
            QuizDifficulty(self.difficulty)
        return self

    def payload_hash(self) -> str:
        import hashlib

        raw = self.model_dump_json(exclude_none=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
