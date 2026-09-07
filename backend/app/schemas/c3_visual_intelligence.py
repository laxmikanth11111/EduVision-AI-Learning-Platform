"""Pydantic V2 Schemas for Checkpoint C3 — Topic-Level Visual Intelligence Engine.

Extends the Phase 4I visual intelligence system with topic/subtopic-driven visual
planning, structured specifications, source grounding, provenance tracking, and
visual lifecycle management.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

# ── Visual Lifecycle States ────────────────────────────────────────────────


class VisualStatus(str, Enum):
    PLANNED = "planned"
    SPECIFYING = "specifying"
    GENERATING = "generating"
    VALIDATING = "validating"
    READY = "ready"
    FAILED = "failed"
    SUPERSEDED = "superseded"


class VisualSourceProvenance(str, Enum):
    SOURCE_DERIVED = "source_derived"
    AI_EXPLAINED = "ai_explained"
    AI_ILLUSTRATIVE = "ai_illustrative"


# ── Extended Visual Type Matrix ────────────────────────────────────────────


class C3VisualType(str, Enum):
    CONCEPT_MAP = "concept_map"
    FLOWCHART = "flowchart"
    PROCESS_DIAGRAM = "process_diagram"
    ARCHITECTURE_DIAGRAM = "architecture_diagram"
    COMPARISON = "comparison"
    TIMELINE = "timeline"
    HIERARCHY = "hierarchy"
    CYCLE = "cycle"
    RELATIONSHIP_GRAPH = "relationship_graph"
    NETWORK_DIAGRAM = "network_diagram"
    ANNOTATED_ILLUSTRATION = "annotated_illustration"
    TECHNICAL_DIAGRAM = "technical_diagram"
    TABLE_VISUALIZATION = "table_visualization"
    CHART = "chart"
    SEQUENCE_DIAGRAM = "sequence_diagram"
    STATE_DIAGRAM = "state_diagram"
    SYSTEM_DIAGRAM = "system_diagram"
    FORMULA_VISUALIZATION = "formula_visualization"
    STEP_BY_STEP = "step_by_step"
    REAL_WORLD_SCENARIO = "real_world_scenario"


# ── Visual Need Decision ───────────────────────────────────────────────────


class VisualNeedDecision(BaseModel):
    """Determines whether a visual would genuinely help a learner understand the concept."""

    visual_needed: bool
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)
    suggested_type: C3VisualType | None = None
    skip_reason: str | None = None


# ── Visual Specification ──────────────────────────────────────────────────


class VisualNode(BaseModel):
    """A single node in a visual diagram specification."""

    id: str
    label: str
    description: str = ""
    node_type: str = "default"
    style: dict[str, Any] = Field(default_factory=dict)
    position: dict[str, float] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class VisualEdge(BaseModel):
    """A directed or bidirectional edge in a visual diagram."""

    id: str
    source_id: str
    target_id: str
    label: str = ""
    edge_type: str = "flow"
    is_bidirectional: bool = False
    style: dict[str, Any] = Field(default_factory=dict)


class VisualStep(BaseModel):
    """A numbered step in process/sequence diagrams."""

    step_number: int
    title: str
    description: str = ""
    node_id: str | None = None


class VisualColumn(BaseModel):
    """A column in a comparison/table visualization."""

    header: str
    items: list[str] = Field(default_factory=list)
    style: dict[str, Any] = Field(default_factory=dict)


class VisualSpecification(BaseModel):
    """Complete structured specification for generating a visual.

    This is the educational source of truth. The generated image/SVG/HTML
    must faithfully represent this specification.
    """

    visual_type: C3VisualType
    title: str
    purpose: str
    learning_objective: str = ""
    nodes: list[VisualNode] = Field(default_factory=list)
    edges: list[VisualEdge] = Field(default_factory=list)
    steps: list[VisualStep] = Field(default_factory=list)
    columns: list[VisualColumn] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    relationships: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    generation_instructions: dict[str, Any] = Field(default_factory=dict)
    validation_rules: list[str] = Field(default_factory=list)


# ── Visual Explanation ────────────────────────────────────────────────────


class VisualExplanation(BaseModel):
    """Student-friendly explanation associated with a generated visual."""

    what_you_see: str = ""
    how_to_read: str = ""
    key_takeaway: str = ""
    real_world_example: str = ""
    common_mistake: str = ""


# ── Topic-Level Visual Plan ───────────────────────────────────────────────


class TopicVisualPlan(BaseModel):
    """A plan for generating one or more visuals for a topic/subtopic."""

    topic_id: str
    topic_title: str
    subtopic_id: str | None = None
    subtopic_title: str | None = None
    visual_needed: bool
    visual_type: C3VisualType | None = None
    specification: VisualSpecification | None = None
    explanation: VisualExplanation | None = None
    source_references: list[dict[str, Any]] = Field(default_factory=list)
    concept_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    provenance: VisualSourceProvenance = VisualSourceProvenance.AI_EXPLAINED
    status: VisualStatus = VisualStatus.PLANNED
    error_message: str | None = None


# ── Presentation-Level Visual Plan ─────────────────────────────────────────


class PresentationVisualPlan(BaseModel):
    """Complete visual generation plan for an entire presentation."""

    presentation_id: str
    total_topics: int
    total_subtopics: int
    visuals_planned: int
    visuals_skipped: int
    topic_plans: list[TopicVisualPlan] = Field(default_factory=list)
    generation_metadata: dict[str, Any] = Field(default_factory=dict)


# ── Visual Asset ──────────────────────────────────────────────────────────


class VisualAsset(BaseModel):
    """A generated visual asset ready for consumption."""

    id: str
    visual_type: C3VisualType
    title: str
    status: VisualStatus
    asset_format: str = "svg"
    asset_url: str | None = None
    asset_key: str | None = None
    asset_content: str | None = None
    specification: VisualSpecification
    explanation: VisualExplanation | None = None
    provenance: VisualSourceProvenance
    source_references: list[dict[str, Any]] = Field(default_factory=list)
    concept_ids: list[str] = Field(default_factory=list)
    presentation_id: str | None = None
    topic_id: str | None = None
    subtopic_id: str | None = None
    version: int = 1
    fingerprint: str = ""
    created_at: str | None = None
    generation_duration_ms: int | None = None
    provider: str | None = None
    model: str | None = None


# ── Visual Generation Request / Response ──────────────────────────────────


class VisualGenerationRequest(BaseModel):
    """Request to generate visual assets for a presentation.

    Contract (single source of truth):
    - ``topic_id`` / ``subtopic_id`` are topic/subtopic TITLES as they appear in
      the C2 outline (matching ``TopicVisualAsset.topic_id`` /
      ``TopicVisualAsset.subtopic_id``), used as client resume hints only.
    - Generation is presentation-scoped: the deterministic planner covers every
      visual-worthy topic/subtopic of the outline regardless of the hint.
    - When a C2 outline exists and ``topic_id`` is supplied, the API rejects a
      title that is not present in the outline instead of silently generating
      nothing for it.
    """

    presentation_id: str
    topic_id: str
    subtopic_id: str | None = None
    force_regenerate: bool = False


class VisualGenerationResponse(BaseModel):
    """Response from visual generation."""

    success: bool
    visual_id: str | None = None
    status: VisualStatus
    message: str = ""
    asset_url: str | None = None


# ── Visual Fallback Content ───────────────────────────────────────────────


class VisualFallbackContent(BaseModel):
    """Fallback content when visual generation fails or is unnecessary."""

    text_explanation: str
    structured_data: dict[str, Any] = Field(default_factory=dict)
    key_points: list[str] = Field(default_factory=list)
    source_references: list[dict[str, Any]] = Field(default_factory=list)


# ── Provider Configuration ────────────────────────────────────────────────


class VisualProviderConfig(BaseModel):
    """Configuration for visual generation providers."""

    provider: str = "deterministic_svg"
    enabled: bool = True
    timeout_seconds: int = 30
    max_retries: int = 2
    fallback_provider: str = "text_only"
    settings: dict[str, Any] = Field(default_factory=dict)


# ── Fingerprint Utility ───────────────────────────────────────────────────


def compute_visual_fingerprint(
    presentation_id: str,
    topic_id: str,
    subtopic_id: str | None,
    concept_ids: list[str],
    spec_version: str = "1",
) -> str:
    """Compute a deterministic fingerprint for deduplication."""
    import hashlib

    parts = [
        presentation_id,
        topic_id,
        subtopic_id or "",
        ",".join(sorted(concept_ids)),
        spec_version,
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
