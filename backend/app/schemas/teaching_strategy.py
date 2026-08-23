"""Pydantic V2 Schemas for AI Teaching Strategy Engine.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class PedagogicalAction(str, Enum):
    CONTINUE = "continue"
    REVIEW = "review"
    REPEAT_SIMULATION = "repeat_simulation"
    REPLAY_VISUAL = "replay_visual"
    INSPECT_COMPONENT = "inspect_component"
    ASK_TUTOR = "ask_tutor"
    EASIER_QUIZ = "easier_quiz"
    HARDER_QUIZ = "harder_quiz"
    ADVANCE_TOPIC = "advance_topic"
    REVISION = "revision"


class RecommendationItem(BaseModel):
    recommendation_id: str
    action: PedagogicalAction
    title: str
    description: str
    priority_score: float = 1.0
    target_component_id: str | None = None
    target_simulation_step: int | None = None
    reasoning: str | None = None


class MasteryAnalysis(BaseModel):
    mastery_percentage: float
    confidence_score: float
    readiness_level: str  # "Needs Review", "Developing", "Proficient", "Mastered"
    quiz_accuracy: float = 0.0
    simulation_progress: float = 0.0
    visual_exploration_depth: float = 0.0
    checkpoint_completion_rate: float = 0.0


class TeachingStrategy(BaseModel):
    strategy_id: str
    session_id: str
    topic: str
    current_action: PedagogicalAction
    recommended_difficulty: str
    recommendations: list[RecommendationItem] = Field(default_factory=list)
    mastery_analysis: MasteryAnalysis
    next_step: str
    action_queue: list[str] = Field(default_factory=list)
    confidence_score: float = 0.85
