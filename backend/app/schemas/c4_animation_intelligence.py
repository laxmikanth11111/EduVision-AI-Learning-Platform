"""Pydantic V2 Schemas for Checkpoint C4 — Advanced Animation & Interactive
Visual Learning Engine.

C4 extends the Checkpoint C3 visual intelligence pipeline with a bounded,
deterministic animation specification language. Every animation is derived
from an underlying C3 visual specification plus C2 topic grounding and source
references, and must teach what a static image cannot: sequences, causes and
effects, state changes, progressive disclosure, and guided interaction.

Determinism guarantees:
- Every step carries an explicit bounded duration (never random).
- Scene and step order is strict (1..n), so the renderer output is identical
  for an identical specification.
- Step kinds are restricted per animation type by a fixed template registry.
- Object, scene, step, and total-duration counts are hard-bounded.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.schemas.c3_visual_intelligence import (
    C3VisualType,
    VisualEdge,
    VisualNode,
    VisualSourceProvenance,
)

# Convenience alias: animation provenance follows the same source-trust model
# as visuals (source-derived information vs. AI explanations vs. illustration).
AnimationSourceProvenance = VisualSourceProvenance

# ── Bounds (bounded scene/duration/object counts) ──────────────────────────

DEFAULT_STEP_DURATION_MS = 1200
MIN_STEP_DURATION_MS = 250
MAX_STEP_DURATION_MS = 4000
MIN_TOTAL_DURATION_MS = 1500
MAX_TOTAL_DURATION_MS = 45000
MAX_SCENES_PER_ANIMATION = 4
MAX_STEPS_PER_SCENE = 10
MAX_NODES = 40
MAX_EDGES = 60
MAX_INTERACTIONS = 4
MAX_ANIMATIONS_PER_PRESENTATION = 16


# ── Animation Lifecycle States ─────────────────────────────────────────────


class AnimationStatus(str, Enum):
    PLANNED = "planned"
    SPECIFYING = "specifying"
    GENERATING = "generating"
    VALIDATING = "validating"
    READY = "ready"
    FAILED = "failed"
    SUPERSEDED = "superseded"


# ── Animation Type Matrix ──────────────────────────────────────────────────


class C4AnimationType(str, Enum):
    """Bounded set of temporal animation templates.

    Each type exists because a static diagram cannot express its temporal and
    causal structure; the motion is load-bearing, never decorative.
    """

    PROCESS_SEQUENCE = "process_sequence"
    CAUSE_EFFECT_CHAIN = "cause_effect_chain"
    STATE_TRANSITION = "state_transition"
    COMPARISON_REVEAL = "comparison_reveal"
    HIERARCHY_ZOOM = "hierarchy_zoom"
    TIMELINE_PROGRESS = "timeline_progress"
    CYCLE_LOOP = "cycle_loop"
    NETWORK_FLOW = "network_flow"


class AnimationStepKind(str, Enum):
    """Motion primitives from which every animation is composed.

    Each primitive has a distinct educational job:
    - reveal: place a new element into the learner's working memory (build-up).
    - highlight: draw attention to an already visible element (focus).
    - traverse: move a token along an edge (flow / cause->effect / order).
    - transform: change an element's visible state (state transition).
    - annotate: show a caption/annotation (narration, no motion).
    - fade_out: dim or remove an element to reduce clutter (declutter).
    - pause: hold the scene for narration/reinforcement (idle hold).
    """

    REVEAL = "reveal"
    HIGHLIGHT = "highlight"
    TRAVERSE = "traverse"
    TRANSFORM = "transform"
    ANNOTATE = "annotate"
    FADE_OUT = "fade_out"
    PAUSE = "pause"


ALLOWED_STEP_KINDS_BY_ANIMATION_TYPE: dict[str, frozenset[AnimationStepKind]] = {
    C4AnimationType.PROCESS_SEQUENCE.value: frozenset(
        {
            AnimationStepKind.REVEAL,
            AnimationStepKind.HIGHLIGHT,
            AnimationStepKind.ANNOTATE,
            AnimationStepKind.FADE_OUT,
            AnimationStepKind.PAUSE,
        }
    ),
    C4AnimationType.CAUSE_EFFECT_CHAIN.value: frozenset(
        {
            AnimationStepKind.REVEAL,
            AnimationStepKind.TRAVERSE,
            AnimationStepKind.HIGHLIGHT,
            AnimationStepKind.TRANSFORM,
            AnimationStepKind.ANNOTATE,
            AnimationStepKind.PAUSE,
        }
    ),
    C4AnimationType.STATE_TRANSITION.value: frozenset(
        {
            AnimationStepKind.REVEAL,
            AnimationStepKind.TRANSFORM,
            AnimationStepKind.HIGHLIGHT,
            AnimationStepKind.ANNOTATE,
            AnimationStepKind.PAUSE,
        }
    ),
    C4AnimationType.COMPARISON_REVEAL.value: frozenset(
        {
            AnimationStepKind.REVEAL,
            AnimationStepKind.HIGHLIGHT,
            AnimationStepKind.ANNOTATE,
            AnimationStepKind.PAUSE,
        }
    ),
    C4AnimationType.HIERARCHY_ZOOM.value: frozenset(
        {
            AnimationStepKind.REVEAL,
            AnimationStepKind.HIGHLIGHT,
            AnimationStepKind.ANNOTATE,
            AnimationStepKind.PAUSE,
        }
    ),
    C4AnimationType.TIMELINE_PROGRESS.value: frozenset(
        {
            AnimationStepKind.REVEAL,
            AnimationStepKind.HIGHLIGHT,
            AnimationStepKind.TRAVERSE,
            AnimationStepKind.ANNOTATE,
            AnimationStepKind.PAUSE,
        }
    ),
    C4AnimationType.CYCLE_LOOP.value: frozenset(
        {
            AnimationStepKind.REVEAL,
            AnimationStepKind.TRAVERSE,
            AnimationStepKind.HIGHLIGHT,
            AnimationStepKind.ANNOTATE,
            AnimationStepKind.PAUSE,
        }
    ),
    C4AnimationType.NETWORK_FLOW.value: frozenset(
        {
            AnimationStepKind.REVEAL,
            AnimationStepKind.TRAVERSE,
            AnimationStepKind.HIGHLIGHT,
            AnimationStepKind.TRANSFORM,
            AnimationStepKind.ANNOTATE,
            AnimationStepKind.PAUSE,
        }
    ),
}


def allowed_step_kinds(animation_type: C4AnimationType | str) -> frozenset[AnimationStepKind]:
    """Return the fixed step-kind template allowed for an animation type.

    Every animation of a given type must be composed exclusively of these
    kinds; this registry is the deterministic contract the renderer relies on.
    """
    key = animation_type.value if isinstance(animation_type, Enum) else animation_type
    return ALLOWED_STEP_KINDS_BY_ANIMATION_TYPE.get(key, frozenset())


# ── Animation Step / Scene ─────────────────────────────────────────────────


class AnimationStep(BaseModel):
    """A single time-boxed step within a scene.

    The step is the atomic unit of the animation. Its duration is explicit and
    bounded, its affected objects reference the specification's node/edge ids,
    and its caption states what the learner should notice when it plays.
    """

    step_index: int = Field(ge=1)
    kind: AnimationStepKind
    node_ids: list[str] = Field(default_factory=list)
    edge_ids: list[str] = Field(default_factory=list)
    caption: str = ""
    educational_role: str = ""
    duration_ms: int | None = Field(default=None, ge=1)
    transform_note: str = ""


class AnimationScene(BaseModel):
    """A building act of the animation: an ordered set of steps over a fixed
    view of the scene graph."""

    scene_index: int = Field(ge=1)
    title: str = ""
    purpose: str = ""
    caption: str = ""
    steps: list[AnimationStep] = Field(default_factory=list)
    initial_node_ids: list[str] = Field(default_factory=list)


class AnimationInteractionKind(str, Enum):
    SELF_CHECK = "self_check"
    PAUSE_REFLECT = "pause_reflect"
    CLICK_REVEAL = "click_reveal"


class AnimationInteraction(BaseModel):
    """A guided interaction anchored to a step.

    Interactions convert passive viewing into active learning; they always
    carry an explicit prompt, answer, and a small guide hint.
    """

    interaction_index: int = Field(ge=1)
    kind: AnimationInteractionKind
    anchor_step_index: int = Field(ge=1)
    # Omitted by legacy packages, whose interactions target the final scene.
    anchor_scene_index: int | None = Field(default=None, ge=1)
    prompt: str
    answer: str = ""
    guide_hint: str = ""


# ── Animation Specification ────────────────────────────────────────────────


class AnimationSpecification(BaseModel):
    """Complete structured specification for a deterministic educational
    animation.

    The specification is the educational source of truth: it fully describes
    the temporal behaviour, captions, durations, and interactions. The
    renderer must reproduce it faithfully and deterministically.
    """

    animation_type: C4AnimationType
    title: str = ""
    purpose: str = ""
    learning_objective: str = ""
    base_visual_type: C3VisualType | None = None
    source_visual_id: str | None = None
    nodes: list[VisualNode] = Field(default_factory=list)
    edges: list[VisualEdge] = Field(default_factory=list)
    scenes: list[AnimationScene] = Field(default_factory=list)
    interactions: list[AnimationInteraction] = Field(default_factory=list)
    pedagogical_rationale: str = ""
    concept_ids: list[str] = Field(default_factory=list)
    source_references: list[dict[str, Any]] = Field(default_factory=list)
    provenance: AnimationSourceProvenance = AnimationSourceProvenance.AI_EXPLAINED
    total_duration_ms: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _normalize_and_validate(self) -> AnimationSpecification:
        node_ids = {n.id for n in self.nodes}
        edge_ids = {e.id for e in self.edges}

        if len(node_ids) != len(self.nodes) or len(edge_ids) != len(self.edges):
            raise ValueError("node and edge identities must be unique")
        if node_ids & edge_ids:
            raise ValueError("node and edge identities must not overlap")
        for edge in self.edges:
            if edge.source_id not in node_ids or edge.target_id not in node_ids:
                raise ValueError(f"edge {edge.id} references unknown node")

        if not self.scenes:
            raise ValueError("specification must contain at least one scene")
        if len(self.scenes) > MAX_SCENES_PER_ANIMATION:
            raise ValueError(
                f"scene count {len(self.scenes)} exceeds max {MAX_SCENES_PER_ANIMATION}"
            )
        if len(self.nodes) > MAX_NODES:
            raise ValueError(f"node count {len(self.nodes)} exceeds max {MAX_NODES}")
        if len(self.edges) > MAX_EDGES:
            raise ValueError(f"edge count {len(self.edges)} exceeds max {MAX_EDGES}")
        if len(self.interactions) > MAX_INTERACTIONS:
            raise ValueError(
                f"interaction count {len(self.interactions)} exceeds max {MAX_INTERACTIONS}"
            )

        allowed = allowed_step_kinds(self.animation_type)
        total_duration = 0
        scene_sequence = [s.scene_index for s in self.scenes]
        if scene_sequence != list(range(1, len(self.scenes) + 1)):
            raise ValueError("scene indices must be sequential starting at 1")

        anchored_steps: set[tuple[int, int]] = set()
        for scene in self.scenes:
            if any(n not in node_ids for n in scene.initial_node_ids):
                raise ValueError(f"scene {scene.scene_index} references unknown initial node")
            if not scene.steps:
                raise ValueError(f"scene {scene.scene_index} must contain at least one step")
            if len(scene.steps) > MAX_STEPS_PER_SCENE:
                raise ValueError(
                    f"scene {scene.scene_index} has {len(scene.steps)} steps, "
                    f"max is {MAX_STEPS_PER_SCENE}"
                )
            indices = [s.step_index for s in scene.steps]
            if indices != list(range(1, len(scene.steps) + 1)):
                raise ValueError(
                    f"scene {scene.scene_index} step indices must be sequential starting at 1"
                )
            for step in scene.steps:
                if step.kind not in allowed:
                    raise ValueError(
                        f"step kind '{step.kind.value}' not allowed for "
                        f"animation type '{self.animation_type.value}'"
                    )
                missing_nodes = [n for n in step.node_ids if n not in node_ids]
                if missing_nodes:
                    raise ValueError(
                        f"step {step.step_index} references unknown node(s): {missing_nodes}"
                    )
                missing_edges = [e for e in step.edge_ids if e not in edge_ids]
                if missing_edges:
                    raise ValueError(
                        f"step {step.step_index} references unknown edge(s): {missing_edges}"
                    )
                if (
                    step.kind in (AnimationStepKind.REVEAL, AnimationStepKind.HIGHLIGHT)
                    and not step.node_ids
                    and not step.edge_ids
                ):
                    raise ValueError(
                        f"step {step.step_index} of kind '{step.kind.value}' "
                        "must target at least one node or edge"
                    )
                if step.kind == AnimationStepKind.TRAVERSE and not step.edge_ids:
                    raise ValueError(
                        f"step {step.step_index} of kind 'traverse' must target an edge"
                    )
                duration = (
                    DEFAULT_STEP_DURATION_MS if step.duration_ms is None else step.duration_ms
                )
                if duration < MIN_STEP_DURATION_MS or duration > MAX_STEP_DURATION_MS:
                    raise ValueError(
                        f"step {step.step_index} duration {duration}ms out of bounds "
                        f"[{MIN_STEP_DURATION_MS}, {MAX_STEP_DURATION_MS}]"
                    )
                step.duration_ms = duration
                if step.kind != AnimationStepKind.PAUSE:
                    anchored_steps.add((scene.scene_index, step.step_index))
                total_duration += duration

        if total_duration > MAX_TOTAL_DURATION_MS:
            raise ValueError(
                f"total duration {total_duration}ms exceeds max {MAX_TOTAL_DURATION_MS}"
            )

        interaction_ids = [i.interaction_index for i in self.interactions]
        if len(set(interaction_ids)) != len(interaction_ids):
            raise ValueError("interaction identities must be unique")
        for interaction in self.interactions:
            scene_index = interaction.anchor_scene_index or len(self.scenes)
            if (scene_index, interaction.anchor_step_index) not in anchored_steps:
                raise ValueError(
                    f"interaction {interaction.interaction_index} anchors step "
                    f"{interaction.anchor_step_index} which has no non-pause step"
                )

        if total_duration < MIN_TOTAL_DURATION_MS:
            raise ValueError(f"total duration {total_duration}ms below min {MIN_TOTAL_DURATION_MS}")
        self.total_duration_ms = total_duration
        return self


# ── Animation Need Decision ────────────────────────────────────────────────


class AnimationNeedDecision(BaseModel):
    """Determines whether an animation genuinely advances understanding beyond
    a static visual."""

    animation_needed: bool
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)
    suggested_type: C4AnimationType | None = None
    base_visual_type: C3VisualType | None = None
    skip_reason: str | None = None


# ── Topic / Presentation Animation Plans ───────────────────────────────────


class TopicAnimationPlan(BaseModel):
    """A plan for generating an animation for a topic/subtopic."""

    topic_id: str
    topic_title: str
    subtopic_id: str | None = None
    subtopic_title: str | None = None
    animation_needed: bool
    animation_type: C4AnimationType | None = None
    base_visual_type: C3VisualType | None = None
    specification: AnimationSpecification | None = None
    source_references: list[dict[str, Any]] = Field(default_factory=list)
    concept_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    provenance: AnimationSourceProvenance = AnimationSourceProvenance.AI_EXPLAINED
    status: AnimationStatus = AnimationStatus.PLANNED
    error_message: str | None = None


class PresentationAnimationPlan(BaseModel):
    """Complete animation generation plan for an entire presentation."""

    presentation_id: str
    total_topics: int
    animations_planned: int
    animations_skipped: int
    topic_plans: list[TopicAnimationPlan] = Field(default_factory=list)
    generation_metadata: dict[str, Any] = Field(default_factory=dict)


# ── Animation Asset ────────────────────────────────────────────────────────


class AnimationAsset(BaseModel):
    """A generated animation asset ready for the player."""

    id: str
    animation_type: C4AnimationType
    title: str
    status: AnimationStatus
    asset_format: str = "html"
    package_content: str | None = None
    specification: AnimationSpecification | None = None
    pedagogical_rationale: str = ""
    explanation: dict[str, Any] = Field(default_factory=dict)
    provenance: AnimationSourceProvenance
    source_references: list[dict[str, Any]] = Field(default_factory=list)
    concept_ids: list[str] = Field(default_factory=list)
    presentation_id: str | None = None
    topic_id: str | None = None
    subtopic_id: str | None = None
    version: int = 1
    fingerprint: str = ""
    created_at: str | None = None
    generation_duration_ms: int | None = None


# ── Generation Request / Response ──────────────────────────────────────────


class AnimationGenerationRequest(BaseModel):
    """Request to generate animations for a presentation.

    Mirrors the C3 contract: ``topic_id`` is a title used as a resume hint
    only; generation is presentation-scoped and fully deterministic.
    """

    presentation_id: str
    topic_id: str
    force_regenerate: bool = False


class AnimationGenerationResponse(BaseModel):
    """Response from animation generation."""

    success: bool
    animation_id: str | None = None
    status: AnimationStatus
    message: str = ""
    package_url: str | None = None


# ── Fingerprint Utility ────────────────────────────────────────────────────


def compute_animation_fingerprint(
    presentation_id: str,
    topic_id: str,
    subtopic_id: str | None,
    concept_ids: list[str],
    spec_version: str = "1",
) -> str:
    """Compute a deterministic fingerprint for animation deduplication."""
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
