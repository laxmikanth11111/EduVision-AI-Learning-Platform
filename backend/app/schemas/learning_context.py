"""Pydantic V2 Schemas for Centralized Learning Context Engine.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class LearningState(str, Enum):
    NOT_STARTED = "not_started"
    READING_EXPLANATION = "reading_explanation"
    EXPLORING_VISUAL = "exploring_visual"
    INSPECTING_COMPONENT = "inspecting_component"
    RUNNING_SIMULATION = "running_simulation"
    REVIEWING_EXAMPLE = "reviewing_example"
    TAKING_ASSESSMENT = "taking_assessment"
    REVIEWING_FEEDBACK = "reviewing_feedback"
    TALKING_WITH_AI_TUTOR = "talking_with_ai_tutor"
    COMPLETED = "completed"


class ContextEvent(BaseModel):
    event_id: str
    event_type: str
    timestamp: float
    state: LearningState
    step_name: str | None = None
    component_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class LearningContext(BaseModel):
    session_id: str
    user_id: str | None = None
    course_id: str | None = None
    lesson_id: str | None = None
    topic: str
    active_state: LearningState = LearningState.NOT_STARTED

    # Visual Workspace State
    canvas_id: str | None = None
    visualization_type: str | None = None
    selected_component_id: str | None = None
    explored_components: list[str] = Field(default_factory=list)
    skipped_components: list[str] = Field(default_factory=list)

    # Simulation Runtime State
    simulation_id: str | None = None
    current_simulation_step: int = 0
    simulation_parameters: dict[str, Any] = Field(default_factory=dict)
    completed_checkpoints: list[str] = Field(default_factory=list)

    # Visual Assessment State
    assessment_id: str | None = None
    quiz_score: float | None = None
    weak_concepts: list[str] = Field(default_factory=list)
    strong_concepts: list[str] = Field(default_factory=list)

    # AI Tutor & Progress Context
    current_difficulty: str = "Intermediate"
    recommended_next_action: str | None = None
    progress_percentage: float = 0.0

    # Event Timeline & Timestamps
    created_at: float = 0.0
    updated_at: float = 0.0
    timeline: list[ContextEvent] = Field(default_factory=list)
