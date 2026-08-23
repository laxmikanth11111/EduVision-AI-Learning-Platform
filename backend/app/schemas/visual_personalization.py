"""Pydantic V2 Schemas for Phase 4L Personalized Visual Learning Engine.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LearningStyleProfile(BaseModel):
    style_name: str = "visual_interactive"  # visual_interactive, step_by_step, deep_dive, summary_first
    visual_preference_score: float = 0.85
    interactive_preference_score: float = 0.80
    reading_preference_score: float = 0.50


class CognitivePreference(BaseModel):
    detail_level: str = "medium"  # high, medium, low
    analogy_preference: bool = True
    example_density: str = "medium"  # high, medium, low


class EngagementProfile(BaseModel):
    attention_span_minutes: float = 15.0
    average_session_duration_minutes: float = 25.0
    completion_rate: float = 0.88
    streak_days: int = 4


class DifficultyProfile(BaseModel):
    current_recommended_difficulty: str = "Intermediate"  # Beginner, Intermediate, Advanced, Expert
    challenge_mode_enabled: bool = False


class AttentionProfile(BaseModel):
    optimal_video_length_seconds: float = 300.0
    break_frequency_minutes: float = 15.0
    focus_index: float = 0.82


class PersonalizedLearningProfile(BaseModel):
    user_id: str
    preferred_learning_speed: float = 1.0
    preferred_explanation_style: str = "Visual Analogy"
    preferred_visuals: list[str] = Field(default_factory=lambda: ["interactive_diagram", "flow_animation"])
    preferred_interaction_frequency: str = "moderate"
    strong_concepts: list[str] = Field(default_factory=list)
    weak_concepts: list[str] = Field(default_factory=list)
    confidence_trends: list[float] = Field(default_factory=lambda: [0.65, 0.72, 0.80])
    learning_consistency: float = 0.85
    revision_frequency: str = "weekly"
    engagement_score: float = 0.85
    last_updated_at: float = 0.0


class RecommendationHistory(BaseModel):
    user_id: str
    past_recommendations: list[str] = Field(default_factory=list)
    accepted_count: int = 0
    rejected_count: int = 0


class PersonalizationSnapshot(BaseModel):
    profile: PersonalizedLearningProfile
    learning_style: LearningStyleProfile
    cognitive_pref: CognitivePreference
    difficulty_pref: DifficultyProfile
    attention_pref: AttentionProfile
    tutor_tone: str = "encouraging"  # encouraging, socratic, rigorous, concise
    next_recommended_lessons: list[str] = Field(default_factory=list)


class MilestoneProgress(BaseModel):
    title: str
    status: str  # completed, in_progress, upcoming
    progress_percentage: float


class PersonalizedDashboardData(BaseModel):
    user_id: str
    road_map: list[MilestoneProgress] = Field(default_factory=list)
    mastery_progress: float = 75.0
    weekly_goals: list[str] = Field(default_factory=list)
    recommended_next_lessons: list[str] = Field(default_factory=list)
    revision_reminders: list[str] = Field(default_factory=list)
    learning_streaks: int = 4
    engagement_summaries: dict[str, Any] = Field(default_factory=dict)
    achievement_milestones: list[str] = Field(default_factory=list)


class PersonalizationEvaluationReport(BaseModel):
    user_id: str
    is_valid: bool = True
    snapshot: PersonalizationSnapshot
    dashboard: PersonalizedDashboardData
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
