"""Learner Progress Dashboard schemas.

Compose already-persisted learner intelligence (educational memory, concept
mastery, deterministic recommendations, quiz attempts, learning sessions) into
a single learner-scoped progress view. All data is deterministic and read-only.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ConceptMasterySummary(BaseModel):
    """A single concept's mastery status for the dashboard."""

    concept_id: str
    concept_name: str
    mastery_score: float = Field(ge=0.0, le=100.0)
    status: str
    review_count: int = 0
    trend: str = "stable"


class RecommendationAction(BaseModel):
    """A deterministic next-best action for the learner."""

    action_type: str
    concept_id: str
    concept_name: str = ""
    title: str
    description: str = ""
    reason: str = ""
    activity_type: str = ""
    priority: str = "medium"
    lesson_id: str | None = None


class LessonProgressItem(BaseModel):
    """A lesson the learner has engaged with, for progress + resume."""

    lesson_id: str
    title: str = ""
    completion_percentage: float = 0.0
    status: str = "in_progress"
    last_activity_at: datetime | None = None
    resume_slide: int = 0
    resume_link: str = ""


class RecentAttempt(BaseModel):
    """A recent quiz attempt in the learner's assessment history."""

    attempt_id: str
    quiz_id: str = ""
    lesson_id: str | None = None
    title: str = ""
    score: float | None = None
    max_score: float | None = None
    percent_score: float | None = None
    passed: bool | None = None
    completed_at: datetime | None = None


class TrendPoint(BaseModel):
    """A single deterministic performance/trend point."""

    label: str
    value: float | None = None
    source: str = "quiz_attempt"


class Summary(BaseModel):
    """Top-level progress summary answered in one glance."""

    lessons_completed: int = 0
    lessons_in_progress: int = 0
    average_mastery: float = 0.0
    mastered_concepts: int = 0
    developing_concepts: int = 0
    weak_concepts: int = 0
    attempts_total: int = 0


class LearnerProgressResponse(BaseModel):
    """Aggregate learner progress shown on the dashboard."""

    model_config = ConfigDict(from_attributes=True)

    summary: Summary
    lesson_progress: list[LessonProgressItem] = Field(default_factory=list)
    concept_mastery: list[ConceptMasterySummary] = Field(default_factory=list)
    weak_concepts: list[dict[str, Any]] = Field(default_factory=list)
    strong_concepts: list[dict[str, Any]] = Field(default_factory=list)
    recommendations: list[RecommendationAction] = Field(default_factory=list)
    recommendations_summary: str = ""
    recent_attempts: list[RecentAttempt] = Field(default_factory=list)
    trend: list[TrendPoint] = Field(default_factory=list)
