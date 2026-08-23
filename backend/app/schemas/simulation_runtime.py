"""Pydantic V2 Schemas for Phase 4I.5 Dynamic Simulation Engine & Interactive Learning Runtime.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ParameterType(str, Enum):
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    STRING = "string"
    SELECT = "select"


class PlaybackState(str, Enum):
    STOPPED = "stopped"
    PLAYING = "playing"
    PAUSED = "paused"
    COMPLETED = "completed"


class SimulationParameter(BaseModel):
    parameter_id: str
    label: str
    data_type: ParameterType
    default_value: Any
    current_value: Any | None = None
    min_value: float | None = None
    max_value: float | None = None
    step_size: float | None = None
    options: list[str] | None = None
    description: str | None = None


class SimulationStep(BaseModel):
    step_id: str
    step_number: int
    title: str
    description: str
    active_components: list[str] = Field(default_factory=list)
    state_delta: dict[str, Any] = Field(default_factory=dict)
    visual_highlights: list[str] = Field(default_factory=list)


class SimulationCheckpoint(BaseModel):
    checkpoint_id: str
    step_number: int
    title: str
    explanation: str
    hint: str
    expected_concept: str
    is_completed: bool = False


class SimulationDefinition(BaseModel):
    simulation_id: str
    topic: str
    category: str
    description: str
    parameters: list[SimulationParameter] = Field(default_factory=list)
    steps: list[SimulationStep] = Field(default_factory=list)
    checkpoints: list[SimulationCheckpoint] = Field(default_factory=list)
    learning_objectives: list[str] = Field(default_factory=list)


class SimulationState(BaseModel):
    session_id: str = ""
    simulation_id: str
    current_step_index: int = 0
    playback_state: PlaybackState = PlaybackState.STOPPED
    playback_speed: float = 1.0
    parameters: dict[str, Any] = Field(default_factory=dict)
    completed_checkpoints: list[str] = Field(default_factory=list)
    event_logs: list[dict[str, Any]] = Field(default_factory=list)
    elapsed_seconds: float = 0.0
