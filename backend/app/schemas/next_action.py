"""Structured learning recommendation schemas."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    REVIEW_CONCEPT = "review_concept"
    SIMPLIFY_EXPLANATION = "simplify_explanation"
    SHOW_VISUAL = "show_visual"
    TRY_SIMULATION = "try_simulation"
    ASK_TUTOR = "ask_tutor"
    TAKE_KNOWLEDGE_CHECK = "take_knowledge_check"
    REVIEW_PREREQUISITE = "review_prerequisite"
    MOVE_TO_NEXT_CONCEPT = "move_to_next_concept"


class ActivityType(str, Enum):
    QUIZ = "quiz"
    VISUAL = "visual"
    EXPLANATION = "explanation"
    SIMULATION = "simulation"
    TUTOR_CHAT = "tutor_chat"
    PREREQUISITE_REVIEW = "prerequisite_review"


class Priority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class NextAction(BaseModel):
    """A structured learning recommendation based on mastery state."""

    action_type: ActionType
    concept_id: str
    concept_name: str = ""
    reason: str
    activity_type: ActivityType
    priority: Priority = Priority.MEDIUM
    title: str
    description: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class LearningRecommendation(BaseModel):
    """A set of recommended next actions for a learner."""

    user_id: str
    concept_mastery: dict[str, float] = Field(default_factory=dict)
    weak_concepts: list[str] = Field(default_factory=list)
    developing_concepts: list[str] = Field(default_factory=list)
    mastered_concepts: list[str] = Field(default_factory=list)
    actions: list[NextAction] = Field(default_factory=list)
    summary: str = ""
