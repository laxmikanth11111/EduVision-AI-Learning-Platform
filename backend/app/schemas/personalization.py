"""API schemas for the personalised learning engine (Phase 4D.5)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from shared.constants import LearningGoalType

# ── Request models ───────────────────────────────────────────────────────────


class LearningPathCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=500, default="Personalised Learning Path")
    description: str | None = Field(default=None, max_length=4000)


class LearningPathPositionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_position: int = Field(ge=0, le=100000)
    progress_percent: float | None = Field(default=None, ge=0, le=100)


class GoalCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal_type: LearningGoalType
    title: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=4000)
    target_value: float | None = Field(default=None, gt=0)
    unit: str | None = Field(default=None, max_length=20)
    target_date: date | None = None
    path_id: str | None = Field(default=None, max_length=40)


class GoalProgressRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_value: float = Field(ge=0)


class StudyPlanGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    days: int | None = Field(default=None, ge=1, le=90)
    start_date: date | None = None
    timezone: str = Field(default="UTC", max_length=64)
    path_id: str | None = Field(default=None, max_length=40)


class StudyPlanItemCompleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day_key: str = Field(min_length=1, max_length=40)
    item_key: str = Field(min_length=1, max_length=40)


class ReviewScheduleGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    window_days: int | None = Field(default=None, ge=1, le=90)


class PersonalizationGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    days: int | None = Field(default=None, ge=1, le=90)
    timezone: str = Field(default="UTC", max_length=64)


# ── Response models ──────────────────────────────────────────────────────────


class LearningPathResponse(BaseModel):
    id: str
    title: str
    description: str | None = None
    status: str
    sequence: list[dict[str, Any]] | None = None
    config: dict[str, Any] | None = None
    current_position: int = 0
    progress_percent: float = 0.0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    context_version: str = "1"
    created_at: datetime
    updated_at: datetime


class LearningGoalResponse(BaseModel):
    id: str
    path_id: str | None = None
    goal_type: str
    title: str
    description: str | None = None
    target_value: float | None = None
    current_value: float = 0.0
    unit: str | None = None
    status: str
    target_date: date | None = None
    achieved_at: datetime | None = None
    progress_percent: float = 0.0
    created_at: datetime
    updated_at: datetime


class StudyPlanResponse(BaseModel):
    id: str
    path_id: str | None = None
    status: str
    title: str | None = None
    start_date: date
    end_date: date
    timezone: str = "UTC"
    days: list[dict[str, Any]] | None = None
    days_count: int = 0
    completed_items: int = 0
    total_items: int = 0
    progress_percent: float = 0.0
    completed_at: datetime | None = None
    generated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ReviewScheduleResponse(BaseModel):
    id: str
    lesson_id: str | None = None
    topic: str
    status: str
    scheduled_date: date
    interval_days: int = 1
    mastery_at_schedule: float = 0.0
    due_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class PersonalizationOverviewResponse(BaseModel):
    active_path: str | None = None
    path_progress: float | None = None
    active_study_plan: str | None = None
    study_plan_progress: float | None = None
    active_goals: int = 0
    due_reviews: int = 0
