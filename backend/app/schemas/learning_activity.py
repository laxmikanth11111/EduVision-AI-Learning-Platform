"""API schemas for interactive activities and the progress engine (4D.3/4D.4)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ActivityAttemptResponse(BaseModel):
    id: str
    activity_id: str | None = None
    attempt_number: int = 1
    status: str
    outcome: str | None = None
    is_correct: bool | None = None
    score: float | None = None
    time_spent_seconds: int = 0
    confidence_level: int | None = None
    difficulty_feedback: str | None = None
    needs_more_explanation: bool = False
    marked_difficult: bool = False
    started_at: datetime | None = None
    completed_at: datetime | None = None
    evaluated_at: datetime | None = None
    created_at: datetime | None = None


class ActivityUserSummary(BaseModel):
    total_attempts: int = 0
    best_score: float | None = None
    last_outcome: str | None = None
    needs_more_explanation: bool = False
    is_correct: bool | None = None


class ActivityResponse(BaseModel):
    id: str
    lesson_id: str | None = None
    block_position: int = 0
    slide_position: int = 0
    section: str | None = None
    activity_type: str
    title: str
    prompt: str | None = None
    instructions: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    difficulty: str = "beginner"
    bloom_level: str | None = None
    topics: list[str] = Field(default_factory=list)
    concepts: list[str] = Field(default_factory=list)
    learning_objectives: list[str] = Field(default_factory=list)
    estimated_duration_seconds: int = 120
    scoring_model: str = "exact"
    is_optional: bool = False
    is_assessed: bool = False
    user_summary: ActivityUserSummary | None = None
    attempt: ActivityAttemptResponse | None = None


class StartActivityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_public_id: str | None = Field(default=None, max_length=128)


class SubmitActivityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: dict[str, Any] | None = None
    session_public_id: str | None = Field(default=None, max_length=128)
    time_spent_seconds: int = Field(default=0, ge=0, le=3600 * 8)
    confidence_level: int | None = Field(default=None, ge=1, le=5)
    difficulty_feedback: str | None = Field(default=None, max_length=20)
    needs_more_explanation: bool = False
    marked_difficult: bool = False


class SubmitActivityResponse(BaseModel):
    attempt: ActivityAttemptResponse
    activity_id: str | None = None
    lesson_id: str | None = None
    is_assessed: bool = False
    verdict: str | None = None
    score: float | None = None
    is_correct: bool | None = None
    correct_answer: Any | None = None
    explanation: str | None = None


class ActivityFeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feedback_type: str = Field(default="note", max_length=30)
    rating: int | None = Field(default=None, ge=1, le=5)
    difficulty_rating: str | None = Field(default=None, max_length=20)
    needs_more_explanation: bool = False
    helpful: bool | None = None
    comment: str | None = Field(default=None, max_length=2000)
    session_public_id: str | None = Field(default=None, max_length=128)
    attempt_public_id: str | None = Field(default=None, max_length=128)


class ActivityFeedbackResponse(BaseModel):
    id: str
    activity_id: str | None = None
    feedback_type: str = "note"
    needs_more_explanation: bool = False


class ProgressOverviewResponse(BaseModel):
    lessons_started: int = 0
    lessons_completed: int = 0
    activities_completed: int = 0
    activities_attempted: int = 0
    accuracy_percent: float | None = None
    time_spent_seconds: int = 0
    streak_days: int = 0
    achievements: int = 0
    updated_at: datetime


class ProgressHistoryResponse(BaseModel):
    period: str
    period_start: datetime | None = None
    period_end: datetime | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class MilestoneResponse(BaseModel):
    id: str
    milestone_type: str
    scope_key: str = ""
    title: str
    description: str | None = None
    progress: float = 0.0
    target: float | None = None
    achieved: bool = False
    achieved_at: datetime | None = None
    lesson_id: str | None = None
    updated_at: datetime | None = None


class RecommendationResponse(BaseModel):
    id: str
    recommendation_type: str
    reason: str | None = None
    activity_id: str | None = None
    target_activity_id: str | None = None
    score: float = 0.0
    status: str = "active"
    rationale: dict[str, Any] | None = None
    created_at: datetime | None = None
