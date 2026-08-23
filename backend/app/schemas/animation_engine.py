"""Pydantic V2 Schemas for Phase 4J.1 + 4J.2 AI Animation Engine Architecture.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AnimationStyle(str, Enum):
    PROGRESSIVE_REVEAL = "progressive_reveal"
    FLOW_ALONG_EDGE = "flow_along_edge"
    FOCUS_ZOOM = "focus_zoom"
    SEQUENTIAL_STEP = "sequential_step"
    NODE_EXPANSION = "node_expansion"


class TransitionType(str, Enum):
    FADE = "fade"
    SLIDE = "slide"
    GROW = "grow"
    SHRINK = "shrink"
    GLOW = "glow"
    FOCUS_SHIFT = "focus_shift"


class AnimationEvent(BaseModel):
    event_id: str
    timestamp_ms: float
    duration_ms: float
    event_type: str  # "reveal_component", "flow_signal", "highlight_node", "focus_camera", "pause_point"
    target_id: str
    motion_definition: dict[str, Any] = Field(default_factory=dict)
    narration_cue: dict[str, Any] | None = None
    interaction_trigger: dict[str, Any] | None = None


class AnimationScene(BaseModel):
    scene_id: str
    scene_index: int
    title: str
    learning_objective: str
    duration_ms: float
    events: list[AnimationEvent] = Field(default_factory=list)
    transition: TransitionType = TransitionType.FADE
    camera_focus_target: str | None = None
    checkpoints: list[str] = Field(default_factory=list)


class AnimationTimeline(BaseModel):
    timeline_id: str
    total_duration_ms: float
    scenes: list[AnimationScene] = Field(default_factory=list)
    total_events: int = 0
    estimated_minutes: float = 1.0
    bookmarks: list[dict[str, Any]] = Field(default_factory=list)


class LayoutAnimationClassification(BaseModel):
    layout_category: str
    recommended_style: AnimationStyle
    educational_objective: str
    focus_order: list[str] = Field(default_factory=list)
    motion_priority: str = "sequential"
    replay_behavior: str = "loop_scene"


class ValidationReport(BaseModel):
    is_valid: bool
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    coverage_score: float = 100.0


class AnimationBlueprint(BaseModel):
    blueprint_id: str
    visual_model_id: str
    topic: str
    classification: LayoutAnimationClassification
    timeline: AnimationTimeline
    validation: ValidationReport
    created_at: float = 0.0
