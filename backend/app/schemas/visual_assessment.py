"""Pydantic V2 Schemas for Phase 4I.6 Adaptive Interactive Visual Assessment Engine.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class VisualQuestionType(str, Enum):
    MULTIPLE_CHOICE = "multiple_choice"
    MULTI_SELECT = "multi_select"
    TRUE_FALSE = "true_false"
    DRAG_DROP = "drag_drop"
    ARRANGE_STEPS = "arrange_steps"
    SEQUENCE_ORDERING = "sequence_ordering"
    MATCH_RELATIONSHIPS = "match_relationships"
    LABEL_DIAGRAM = "label_diagram"
    HOTSPOT = "hotspot"
    FILL_MISSING_NODE = "fill_missing_node"
    COMPLETE_FLOW = "complete_flow"
    SIMULATION_CHECKPOINT = "simulation_checkpoint"


class AssessmentDifficulty(str, Enum):
    BEGINNER = "Beginner"
    INTERMEDIATE = "Intermediate"
    ADVANCED = "Advanced"


class VisualOption(BaseModel):
    option_id: str
    text: str
    is_correct: bool = False
    explanation: str | None = None
    target_node_id: str | None = None


class VisualQuestion(BaseModel):
    question_id: str
    type: VisualQuestionType
    prompt: str
    target_component_id: str | None = None
    options: list[VisualOption] = Field(default_factory=list)
    correct_answer: Any
    explanation: str
    difficulty: AssessmentDifficulty = AssessmentDifficulty.INTERMEDIATE
    related_component_id: str | None = None
    learning_objective: str | None = None


class VisualAssessmentBundle(BaseModel):
    assessment_id: str
    canvas_id: str | None = None
    topic: str
    difficulty: AssessmentDifficulty = AssessmentDifficulty.INTERMEDIATE
    questions: list[VisualQuestion] = Field(default_factory=list)
    adaptive_reasoning: str | None = None


class AnswerSubmissionRequest(BaseModel):
    assessment_id: str
    question_id: str
    user_answer: Any
    time_taken_seconds: float = 0.0


class AnswerEvaluationResult(BaseModel):
    question_id: str
    is_correct: bool
    score: float
    user_answer: Any
    correct_answer: Any
    explanation: str
    related_component_id: str | None = None
    suggested_review: str | None = None
    next_difficulty: AssessmentDifficulty
