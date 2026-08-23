"""Pydantic V2 Schemas for AI Director Engine (Educational Orchestration Brain).
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DirectorAction(str, Enum):
    CONTINUE = "continue"
    PAUSE_AUTOMATICALLY = "pause_automatically"
    REPLAY_SCENE = "replay_scene"
    SKIP_MASTERED = "skip_mastered"
    SLOW_PLAYBACK = "slow_playback"
    SPEED_UP = "speed_up"
    INSERT_EXPLANATION = "insert_explanation"
    INSERT_EXAMPLE = "insert_example"
    RECOMMEND_SIMULATION = "recommend_simulation"
    TRIGGER_QUIZ = "trigger_quiz"
    SUGGEST_AI_TUTOR = "suggest_ai_tutor"
    RECOMMEND_REVISION = "recommend_revision"
    ADVANCE_TOPIC = "advance_topic"


class InterventionPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class OrchestrationMode(str, Enum):
    AUTONOMOUS = "autonomous"
    GUIDED = "guided"
    MANUAL = "manual"


class LessonDirectorState(BaseModel):
    session_id: str
    topic: str
    current_step_title: str = "Introductory Stage"
    mastery_percentage: float = 50.0
    quiz_score: float | None = None
    completed_checkpoints: list[str] = Field(default_factory=list)
    active_component_id: str | None = "comp_fetch"
    engagement_score: float = 0.85
    orchestration_mode: OrchestrationMode = OrchestrationMode.GUIDED
    last_evaluated_at: float = 0.0


class DirectorDecision(BaseModel):
    decision_id: str
    action: DirectorAction
    title: str
    description: str
    reasoning: str
    confidence_score: float = 0.9
    priority: InterventionPriority = InterventionPriority.MEDIUM
    metadata: dict[str, Any] = Field(default_factory=dict)


class DirectorRecommendation(BaseModel):
    recommendation_id: str
    session_id: str
    action: DirectorAction
    title: str
    description: str
    reasoning: str
    priority: InterventionPriority = InterventionPriority.MEDIUM
    suggested_speed_multiplier: float = 1.0
    target_scene_index: int | None = None
    created_at: float = 0.0


class SceneAdjustment(BaseModel):
    scene_id: str
    original_duration_ms: float
    adjusted_duration_ms: float
    action: DirectorAction
    reason: str


class PlaybackAdjustment(BaseModel):
    playback_speed: float = 1.0
    auto_pause_timestamp_ms: float | None = None
    skip_to_scene_index: int | None = None
    reason: str = ""


class LearningIntervention(BaseModel):
    intervention_id: str
    session_id: str
    trigger_event: str
    action: DirectorAction
    message: str
    suggested_action_title: str
    priority: InterventionPriority = InterventionPriority.MEDIUM
    is_dismissed: bool = False
    created_at: float = 0.0


class LessonPlanUpdate(BaseModel):
    updated_plan_id: str
    removed_scenes: list[str] = Field(default_factory=list)
    added_scenes: list[str] = Field(default_factory=list)
    reordered_scenes: list[str] = Field(default_factory=list)
    reason: str = ""


class AdaptivePath(BaseModel):
    path_id: str
    current_milestone: str
    recommended_next_topics: list[str] = Field(default_factory=list)
    estimated_completion_minutes: float = 15.0


class EngagementSnapshot(BaseModel):
    attention_level: float = 0.85
    interaction_frequency: int = 5
    pause_count: int = 1
    speed_change_count: int = 0
    tutor_query_count: int = 0


class DirectorMetrics(BaseModel):
    total_evaluations: int = 0
    total_interventions: int = 0
    accepted_recommendations_count: int = 0
    average_mastery_gain: float = 0.0


class DirectorEvaluationReport(BaseModel):
    session_id: str
    is_valid: bool = True
    state: LessonDirectorState
    decisions: list[DirectorDecision] = Field(default_factory=list)
    recommendations: list[DirectorRecommendation] = Field(default_factory=list)
    playback_adjustment: PlaybackAdjustment
    adaptive_path: AdaptivePath
    metrics: DirectorMetrics
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
