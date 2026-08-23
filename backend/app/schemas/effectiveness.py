"""P2 Learning Effectiveness schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ── Assessment Type ──────────────────────────────────────────────────────

class AssessmentType:
    BASELINE = "baseline"
    POST = "post"
    RETENTION = "retention"
    NORMAL = "normal"


# ── Learning Events ──────────────────────────────────────────────────────

class LearningEventCreate(BaseModel):
    event_type: str
    resource_type: str | None = None
    resource_id: str | None = None
    concept_id: str | None = None
    presentation_id: str | None = None
    metadata_json: dict[str, Any] | None = None
    occurred_at: datetime | None = None


class LearningEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    public_id: str
    event_type: str
    resource_type: str | None
    resource_id: str | None
    concept_id: str | None
    occurred_at: datetime


class LearningEventListResponse(BaseModel):
    events: list[LearningEventResponse]
    total: int


# ── Effectiveness Assessment ────────────────────────────────────────────

class StartAssessmentRequest(BaseModel):
    presentation_id: str
    assessment_type: str = Field(
        ..., pattern="^(baseline|post|retention)$",
    )
    experiment_group: str | None = None
    retention_delay_hours: int | None = Field(None, ge=1, le=720)


class StartAssessmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    assessment_public_id: str
    quiz_id: str | None = None
    assessment_type: str
    message: str


class RecordScoreRequest(BaseModel):
    quiz_attempt_id: str
    concept_scores: dict[str, float] | None = None


class LearningGainResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    assessment_public_id: str
    presentation_id: str
    experiment_group: str | None = None
    baseline_score: float | None
    post_score: float | None
    absolute_gain: float | None
    normalized_gain: float | None
    retention_score: float | None
    retention_loss: float | None
    retention_pct: float | None
    status: str
    completed_at: datetime | None


class EffectivenessReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    assessment_public_id: str
    presentation_id: str
    presentation_title: str | None
    experiment_group: str | None = None
    baseline_score: float | None
    post_score: float | None
    absolute_gain: float | None
    normalized_gain: float | None
    retention_score: float | None
    retention_loss: float | None
    retention_pct: float | None
    total_learning_time_seconds: int | None
    events_summary: dict[str, Any] | None
    concept_improvements: list[dict[str, Any]]
    weak_concepts: list[str]
    strong_concepts: list[str]
    status: str
    completed_at: datetime | None


class GroupComparisonResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    group_a: str
    group_b: str
    group_a_count: int
    group_b_count: int
    group_a_avg_baseline: float | None
    group_b_avg_baseline: float | None
    group_a_avg_post: float | None
    group_b_avg_post: float | None
    group_a_avg_absolute_gain: float | None
    group_b_avg_absolute_gain: float | None
    group_a_avg_normalized_gain: float | None
    group_b_avg_normalized_gain: float | None
    group_a_avg_retention_score: float | None
    group_b_avg_retention_score: float | None
    group_a_avg_retention_loss: float | None
    group_b_avg_retention_loss: float | None
    group_a_avg_retention_pct: float | None
    group_b_avg_retention_pct: float | None
    group_a_completed: int
    group_b_completed: int


class UserEffectivenessSummary(BaseModel):
    total_assessments: int
    completed_assessments: int
    avg_baseline_score: float | None
    avg_post_score: float | None
    avg_absolute_gain: float | None
    avg_normalized_gain: float | None
    total_learning_time_seconds: int
    presentations_covered: int


# ── User Feedback ────────────────────────────────────────────────────────

class FeedbackSubmitRequest(BaseModel):
    presentation_id: str | None = None
    assessment_id: str | None = None
    perceived_understanding: int | None = Field(None, ge=1, le=5)
    confidence: int | None = Field(None, ge=1, le=5)
    usefulness: int | None = Field(None, ge=1, le=5)
    visual_usefulness: int | None = Field(None, ge=1, le=5)
    animation_usefulness: int | None = Field(None, ge=1, le=5)
    tutor_usefulness: int | None = Field(None, ge=1, le=5)
    recommendation_usefulness: int | None = Field(None, ge=1, le=5)
    overall_experience: int | None = Field(None, ge=1, le=5)
    qualitative_feedback: str | None = Field(None, max_length=2000)


class FeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    public_id: str
    perceived_understanding: int | None
    confidence: int | None
    usefulness: int | None
    visual_usefulness: int | None
    animation_usefulness: int | None
    tutor_usefulness: int | None
    recommendation_usefulness: int | None
    overall_experience: int | None
    qualitative_feedback: str | None
    created_at: datetime


class FeedbackSummary(BaseModel):
    total_count: int
    avg_perceived_understanding: float | None
    avg_confidence: float | None
    avg_usefulness: float | None
    avg_visual_usefulness: float | None
    avg_animation_usefulness: float | None
    avg_tutor_usefulness: float | None
    avg_recommendation_usefulness: float | None
    avg_overall_experience: float | None
