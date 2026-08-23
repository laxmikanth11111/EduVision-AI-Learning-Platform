"""Pydantic V2 Schemas for Educational Memory Service.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ConceptMasteryRecord(BaseModel):
    concept_id: str
    concept_name: str
    first_learned_at: float
    last_reviewed_at: float
    mastery_score: float = 0.0  # 0.0 to 100.0
    review_count: int = 1
    trend: str = "stable"  # "improving", "stable", "regressing"
    confidence_score: float = 0.5


class LearningPreference(BaseModel):
    preferred_visualization_type: str | None = None
    preferred_explanation_style: str = "concise"
    preferred_difficulty: str = "Intermediate"
    preferred_simulation_speed: float = 1.0


class TimelineMilestone(BaseModel):
    milestone_id: str
    title: str
    timestamp: float
    category: str  # "course_started", "lesson_completed", "concept_mastered", "quiz_passed", "simulation_completed"
    details: dict[str, Any] = Field(default_factory=dict)


class LearnerProfile(BaseModel):
    user_id: str
    learning_pace: str = "moderate"  # "fast", "moderate", "thorough"
    total_study_minutes: float = 0.0
    average_mastery: float = 0.0
    streak_days: int = 1


StudentProfile = LearnerProfile  # backward compat alias


class EducationalMemory(BaseModel):
    user_id: str
    profile: LearnerProfile
    completed_courses: list[str] = Field(default_factory=list)
    completed_lessons: list[str] = Field(default_factory=list)
    completed_topics: list[str] = Field(default_factory=list)

    # Concept Tracking
    mastered_concepts: list[str] = Field(default_factory=list)
    developing_concepts: list[str] = Field(default_factory=list)
    weak_concepts: list[str] = Field(default_factory=list)
    concept_records: dict[str, ConceptMasteryRecord] = Field(default_factory=dict)

    # Preferences & Recommendations
    preferences: LearningPreference = Field(default_factory=LearningPreference)
    revision_queue: list[str] = Field(default_factory=list)
    milestones: list[TimelineMilestone] = Field(default_factory=list)

    created_at: float = 0.0
    updated_at: float = 0.0
