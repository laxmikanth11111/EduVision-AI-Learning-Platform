"""Pydantic V2 Schemas for AI Learning Insights Engine.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class InsightCategory(str, Enum):
    STRENGTH = "strength"
    WEAKNESS = "weakness"
    IMPROVEMENT = "improvement"
    MISCONCEPTION = "misconception"
    PREDICTION = "prediction"
    REVISION = "revision"


class PriorityLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class LearningInsight(BaseModel):
    insight_id: str
    title: str
    explanation: str
    category: InsightCategory
    reason: str
    confidence_score: float = 0.85
    metric_context: dict[str, Any] = Field(default_factory=dict)


class ActionableRecommendation(BaseModel):
    recommendation_id: str
    title: str
    action_type: str  # "replay_simulation", "review_explanation", "inspect_component", "ask_tutor", "take_quiz"
    priority: PriorityLevel
    reason: str
    expected_benefit: str
    estimated_minutes: int = 5
    action_target_id: str | None = None


class AnalyticsNarrativeSummary(BaseModel):
    user_id: str
    period: str  # "weekly", "monthly", "session"
    headline: str
    narrative_body: str
    strengths_summary: list[str] = Field(default_factory=list)
    focus_areas: list[str] = Field(default_factory=list)


class PredictiveInsight(BaseModel):
    concept_id: str
    concept_name: str
    readiness_score: float  # 0.0 to 100.0
    probability_of_mastery: float  # 0.0 to 1.0
    future_weakness_risk: str  # "high", "moderate", "low"
    recommended_review_days: int = 3


class CreatorInsight(BaseModel):
    topic: str
    most_skipped_component: str | None = None
    misconception_pattern: str | None = None
    average_mastery_percentage: float = 0.0
    recommended_curriculum_change: str | None = None
    high_risk_learners_count: int = 0


TeacherClassroomInsight = CreatorInsight  # backward compat alias
