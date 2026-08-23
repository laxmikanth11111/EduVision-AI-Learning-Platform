"""Pydantic V2 Schemas for Phase 4I Visual Intelligence Engine.

Defines normalized data structures for topic classification, learning objectives,
component discovery, graph relationships, visualization decision matrix, and the
frontend-independent VisualLearningModel.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TopicCategory(str, Enum):
    PROCESS = "Process"
    WORKFLOW = "Workflow"
    ALGORITHM = "Algorithm"
    SYSTEM_ARCHITECTURE = "System Architecture"
    TIMELINE = "Timeline"
    COMPARISON = "Comparison"
    HIERARCHY = "Hierarchy"
    MIND_MAP = "Mind Map"
    NETWORK = "Network"
    LIFECYCLE = "Lifecycle"
    CAUSE_AND_EFFECT = "Cause & Effect"
    PROGRAMMING_CONCEPT = "Programming Concept"
    MATHEMATICAL_CONCEPT = "Mathematical Concept"
    SCIENTIFIC_CYCLE = "Scientific Cycle"
    BIOLOGY = "Biology"
    CHEMISTRY = "Chemistry"
    PHYSICS = "Physics"
    ECONOMICS = "Economics"
    BUSINESS_PROCESS = "Business Process"
    DECISION_TREE = "Decision Tree"
    DATA_FLOW = "Data Flow"
    CONCEPT_RELATIONSHIP = "Concept Relationship"


class VisualizationType(str, Enum):
    FLOWCHART = "Flowchart"
    TIMELINE = "Timeline"
    BLOCK_DIAGRAM = "Block Diagram"
    MIND_MAP = "Mind Map"
    COMPARISON_LAYOUT = "Comparison Layout"
    DECISION_TREE = "Decision Tree"
    NETWORK_GRAPH = "Network Graph"
    HIERARCHY = "Hierarchy"
    SCIENTIFIC_CYCLE = "Scientific Cycle"
    ALGORITHM_STEPS = "Algorithm Steps"


class RelationshipType(str, Enum):
    PARENT_CHILD = "parent_child"
    SEQUENTIAL_FLOW = "sequential_flow"
    BIDIRECTIONAL = "bidirectional"
    DEPENDENCY = "dependency"
    DATA_FLOW = "data_flow"
    COMMUNICATION = "communication"
    CAUSE_EFFECT = "cause_effect"


class DifficultyLevel(str, Enum):
    BEGINNER = "Beginner"
    INTERMEDIATE = "Intermediate"
    ADVANCED = "Advanced"


class CategoryClassification(BaseModel):
    primary_category: TopicCategory
    secondary_category: TopicCategory | None = None
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    reasoning_metadata: dict[str, Any] = Field(default_factory=dict)


class LearningObjectives(BaseModel):
    main_goal: str
    learning_objectives: list[str] = Field(default_factory=list)
    important_ideas: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    expected_outcomes: list[str] = Field(default_factory=list)


class InputDescriptor(BaseModel):
    name: str
    type: str = "data"
    source: str | None = None


class OutputDescriptor(BaseModel):
    name: str
    type: str = "result"
    destination: str | None = None


class DiscoveredComponent(BaseModel):
    component_id: str
    name: str
    category: str = "core"
    short_description: str
    detailed_working: str
    inputs: list[InputDescriptor] = Field(default_factory=list)
    outputs: list[OutputDescriptor] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    real_world_analogy: str | None = None
    importance_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    difficulty_level: DifficultyLevel = DifficultyLevel.INTERMEDIATE


class ComponentRelationship(BaseModel):
    source_id: str
    target_id: str
    relationship_type: RelationshipType
    description: str
    is_bidirectional: bool = False


class VisualizationDecision(BaseModel):
    visualization_type: VisualizationType
    reason: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    fallback_type: VisualizationType = VisualizationType.BLOCK_DIAGRAM


class Position(BaseModel):
    x: float
    y: float


class Dimensions(BaseModel):
    width: float = 160.0
    height: float = 90.0


class VisualNodeSchema(BaseModel):
    node_id: str
    label: str
    category: str = "core"
    position: Position
    dimensions: Dimensions = Field(default_factory=Dimensions)
    style: dict[str, Any] = Field(default_factory=dict)
    importance_weight: float = 0.5


class VisualEdgeSchema(BaseModel):
    edge_id: str
    source_node_id: str
    target_node_id: str
    label: str | None = None
    relationship_type: RelationshipType
    is_bidirectional: bool = False
    style: dict[str, Any] = Field(default_factory=dict)


class LayoutSuggestion(BaseModel):
    canvas_dimensions: Dimensions = Field(default_factory=lambda: Dimensions(width=1200.0, height=800.0))
    node_spacing: float = 180.0
    layout_direction: str = "horizontal"  # horizontal, vertical, radial, grid


class VisualLearningModel(BaseModel):
    topic: str
    classification: CategoryClassification
    learning_objectives: LearningObjectives
    visualization_decision: VisualizationDecision
    components: list[DiscoveredComponent] = Field(default_factory=list)
    relationships: list[ComponentRelationship] = Field(default_factory=list)
    visual_nodes: list[VisualNodeSchema] = Field(default_factory=list)
    visual_edges: list[VisualEdgeSchema] = Field(default_factory=list)
    suggested_layout: LayoutSuggestion = Field(default_factory=LayoutSuggestion)
    examples: list[str] = Field(default_factory=list)
    future_simulation_candidates: list[str] = Field(default_factory=list)
    quiz_focus_areas: list[str] = Field(default_factory=list)


class VisualValidationError(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class VisualValidationResult(BaseModel):
    is_valid: bool
    errors: list[VisualValidationError] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
