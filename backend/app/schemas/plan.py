"""P11 personalised study-plan / goal / learning-path API schemas.

These models wrap the existing 0011 ``learning_paths``, ``learning_goals`` and
``study_plans`` tables and the shared enum vocabulary, exposing deterministic,
learner-scoped views for the dashboard's Today / Goals / Learning Path panels.
Requests reuse the (previously orphaned) ``personalization`` request models;
every progress value is derived server-side, never client-submitted.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class PlanItem(BaseModel):
    """A single actionable item on the learner's plan.

    ``deep_link`` is an existing validated frontend destination
    (``/frontend/player.html?lesson=...`` or ``/frontend/tutor.html?concept=...``),
    mirroring the P10 actionability contract: every item is a real, clickable CTA.
    """

    item_key: str
    item_type: str = "lesson"  # review | practice | lesson
    title: str = ""
    reason: str = ""
    priority: str = "medium"  # high | medium | low
    status: str = "pending"  # pending | completed | skipped
    deep_link: str = ""
    schedule_id: str | None = None
    concept_id: str | None = None
    concept_name: str = ""
    lesson_id: str | None = None
    due_at: datetime | None = None


class TodayPlanResponse(BaseModel):
    """The learner's deterministic plan for a single day."""

    plan_id: str | None = None
    date: date
    items: list[PlanItem] = Field(default_factory=list)
    completed_items: int = 0
    total_items: int = 0
    summary: str = ""


class PlanItemCompleteResponse(BaseModel):
    """Result of completing one plan item (routes through existing flows)."""

    plan_id: str
    item_key: str
    status: str = "completed"
    routed_review: bool = False
    next_due_at: datetime | None = None
    next_interval_days: int | None = None
    message: str = ""


class GoalsResponse(BaseModel):
    """The learner's active goals with derived progress."""

    goals: list[LearningGoalView] = Field(default_factory=list)


class LearningGoalView(BaseModel):
    """A single goal with its server-derived progress."""

    id: str
    path_id: str | None = None
    goal_type: str
    title: str
    description: str | None = None
    target_value: float | None = None
    current_value: float = 0.0
    unit: str | None = None
    status: str = "active"
    target_date: date | None = None
    progress_percent: float = 0.0
    achieved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class GoalCreateResponse(BaseModel):
    """A created goal (progress re-derived from live state)."""

    goal: LearningGoalView


class GoalCompleteResponse(BaseModel):
    """Result of completing a goal (only when the target is met)."""

    id: str
    status: str = "achieved"
    current_value: float = 0.0
    target_value: float | None = None
    progress_percent: float = 0.0
    achieved_at: datetime | None = None


class PathLesson(BaseModel):
    """A single lesson in the learner's ordered learning path."""

    lesson_id: str
    title: str = ""
    status: str = "not_started"  # not_started | in_progress | completed
    completion_percentage: float = 0.0
    mastery_score: float | None = None
    deep_link: str = ""


class LearningPathView(BaseModel):
    """The learner's single active learning path with position/progress."""

    id: str
    title: str = ""
    status: str = "active"
    position: int = 0
    lesson_count: int = 0
    progress_percent: float = 0.0
    current_lesson: PathLesson | None = None
    sequence: list[PathLesson] = Field(default_factory=list)


class LearningPathCreateResponse(BaseModel):
    """A learning path created/activated for the learner."""

    path: LearningPathView
