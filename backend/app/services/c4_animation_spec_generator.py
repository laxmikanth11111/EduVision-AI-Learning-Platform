"""C4 Animation Specification Generator — derives a bounded, deterministic
animation specification from a C3 visual specification plus topic grounding.

The generator rebuilds the scene graph from the C3 specification (nodes/edges/
steps/columns ordered exactly as produced) and constructs educational scenes
whose steps are drawn exclusively from the fixed step-kind templates allowed
for the chosen animation type. No randomness is used: identical inputs yield
byte-identical specifications.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.schemas.c3_visual_intelligence import (
    C3VisualType,
    VisualColumn,
    VisualEdge,
    VisualNode,
    VisualStep,
)
from app.schemas.c4_animation_intelligence import (
    MAX_SCENES_PER_ANIMATION,
    MAX_STEPS_PER_SCENE,
    AnimationInteraction,
    AnimationInteractionKind,
    AnimationScene,
    AnimationSourceProvenance,
    AnimationSpecification,
    AnimationStep,
    AnimationStepKind,
    C4AnimationType,
)

logger = get_logger(__name__)

# Bounds used by the builders to keep every generated specification valid.
_MAX_ANIMATION_NODES = 14
_MAX_ANIMATION_EDGES = 18
_MAX_TRAVERSE_STEPS = 12
_ROW_REVEAL_LIMIT = 3
_COMPARISON_ITEM_LIMIT = 3

# Deterministic per-kind durations in milliseconds.
_STEP_DURATION: dict[AnimationStepKind, int] = {
    AnimationStepKind.REVEAL: 1200,
    AnimationStepKind.HIGHLIGHT: 900,
    AnimationStepKind.TRAVERSE: 1600,
    AnimationStepKind.TRANSFORM: 1400,
    AnimationStepKind.ANNOTATE: 1100,
    AnimationStepKind.FADE_OUT: 800,
    AnimationStepKind.PAUSE: 1200,
}


# ── Helpers to rebuild the scene graph from the C3 specification ──────────


def _nodes_from(base_spec: dict[str, Any]) -> list[VisualNode]:
    out: list[VisualNode] = []
    seen: set[str] = set()
    for i, raw in enumerate(base_spec.get("nodes") or []):
        node_id = str(raw.get("id") or f"n_{i}")
        if node_id in seen:
            continue
        seen.add(node_id)
        out.append(
            VisualNode(
                id=node_id,
                label=str(raw.get("label") or node_id)[:120],
                description=str(raw.get("description") or "")[:400],
                node_type=str(raw.get("node_type") or "default"),
                style=dict(raw.get("style") or {}),
            )
        )
        if len(out) >= _MAX_ANIMATION_NODES:
            break
    return out


def _edges_from(base_spec: dict[str, Any], node_ids: set[str]) -> list[VisualEdge]:
    out: list[VisualEdge] = []
    for i, raw in enumerate(base_spec.get("edges") or []):
        edge_id = str(raw.get("id") or f"e_{i}")
        source_id = str(raw.get("source_id") or "")
        target_id = str(raw.get("target_id") or "")
        if source_id not in node_ids or target_id not in node_ids:
            continue
        if any(e.id == edge_id for e in out):
            continue
        out.append(
            VisualEdge(
                id=edge_id,
                source_id=source_id,
                target_id=target_id,
                label=str(raw.get("label") or "")[:120],
                edge_type=str(raw.get("edge_type") or "flow"),
                is_bidirectional=bool(raw.get("is_bidirectional", False)),
            )
        )
        if len(out) >= _MAX_ANIMATION_EDGES:
            break
    return out


def _columns_from(base_spec: dict[str, Any]) -> list[VisualColumn]:
    out: list[VisualColumn] = []
    for i, raw in enumerate(base_spec.get("columns") or []):
        out.append(
            VisualColumn(
                header=str(raw.get("header") or f"Column {i + 1}")[:120],
                items=[str(x)[:200] for x in (raw.get("items") or [])],
            )
        )
    return out


def _steps_from(base_spec: dict[str, Any]) -> list[VisualStep]:
    return [
        VisualStep(
            step_number=int(s.get("step_number") or i + 1),
            title=str(s.get("title") or "Step")[:120],
            description=str(s.get("description") or "")[:400],
        )
        for i, s in enumerate(base_spec.get("steps") or [])
    ]


def _derive_nodes(base_spec: dict[str, Any]) -> list[VisualNode]:
    """Derive the animation scene graph from a C3 base specification.

    Priority: explicit nodes, then ordered steps (timeline/sequence bases), then
    labels. The derived nodes are the canonical ids the animation steps target.
    """
    nodes = _nodes_from(base_spec)
    if nodes:
        return nodes
    steps = _steps_from(base_spec)
    if steps:
        return [
            VisualNode(
                id=f"milestone_{i}",
                label=s.title,
                description=s.description,
                node_type="milestone",
            )
            for i, s in enumerate(steps)
        ][:_MAX_ANIMATION_NODES]
    labels = base_spec.get("labels") or []
    return [VisualNode(id=f"item_{i}", label=str(label)[:120]) for i, label in enumerate(labels)][
        :_MAX_ANIMATION_NODES
    ]


def _step(
    kind: AnimationStepKind,
    index: int,
    node_ids: list[str] | None = None,
    edge_ids: list[str] | None = None,
    caption: str = "",
    role: str = "",
    transform_note: str = "",
    duration_ms: int | None = None,
) -> AnimationStep:
    return AnimationStep(
        step_index=index,
        kind=kind,
        node_ids=node_ids or [],
        edge_ids=edge_ids or [],
        caption=caption[:400],
        educational_role=role[:300],
        duration_ms=duration_ms or _STEP_DURATION[kind],
        transform_note=transform_note[:200],
    )


def _chunk_steps(steps: list[AnimationStep]) -> list[list[AnimationStep]]:
    """Split steps into sequential scenes honouring the per-scene cap.

    Indexes are renumbered so every scene's steps start at 1.
    """
    chunks: list[list[AnimationStep]] = []
    for step in steps:
        if not chunks or len(chunks[-1]) >= MAX_STEPS_PER_SCENE:
            chunks.append([])
        chunks[-1].append(step)
    for chunk in chunks:
        for index, step in enumerate(chunk, start=1):
            step.step_index = index
    return chunks


# ── Type-specific scene builders ──────────────────────────────────────────


def _build_process_sequence(
    nodes: list[VisualNode], edges: list[VisualEdge]
) -> list[AnimationScene]:
    ordered = nodes
    reveal_steps: list[AnimationStep] = []
    for i, node in enumerate(ordered):
        prev = "The process begins" if i == 0 else f"After: {ordered[i - 1].label}"
        reveal_steps.append(
            _step(
                AnimationStepKind.REVEAL,
                i + 1,
                node_ids=[node.id],
                caption=f"Step {i + 1}: {node.label}",
                role="Build the sequence in learner memory one stage at a time",
                transform_note=prev,
            )
        )

    walk_steps: list[AnimationStep] = []
    for i, node in enumerate(ordered):
        caption = node.description or f"{node.label} completes this stage of the sequence"
        walk_steps.append(
            _step(
                AnimationStepKind.HIGHLIGHT,
                i + 1,
                node_ids=[node.id],
                caption=caption,
                role="Re-walk the finished sequence to reinforce the order and why each stage matters",
            )
        )

    scenes: list[AnimationScene] = []
    offset = 0
    for chunk in _chunk_steps(reveal_steps):
        scenes.append(
            AnimationScene(
                scene_index=len(scenes) + 1,
                title="The sequence step by step",
                purpose="Reveal each stage in order so the learner sees how the sequence builds",
                caption=f"{len(ordered)} ordered stages",
                steps=chunk,
            )
        )
        offset += len(chunk)
    for chunk in _chunk_steps(walk_steps):
        scenes.append(
            AnimationScene(
                scene_index=len(scenes) + 1,
                title="Walk through the completed sequence",
                purpose="Highlight every stage in order to cement the ordering",
                caption="Order and dependencies between stages",
                steps=chunk,
            )
        )
    return scenes[:MAX_SCENES_PER_ANIMATION]


def _build_cause_effect_chain(
    nodes: list[VisualNode], edges: list[VisualEdge]
) -> list[AnimationScene]:
    reveal_steps = [
        _step(
            AnimationStepKind.REVEAL,
            i + 1,
            node_ids=[node.id],
            caption=f"Element in the system: {node.label}",
            role="Place the whole system before showing how an effect moves through it",
        )
        for i, node in enumerate(nodes)
    ]

    chain_steps: list[AnimationStep] = []
    for i, edge in enumerate(edges[:_MAX_TRAVERSE_STEPS]):
        target_label = next((n.label for n in nodes if n.id == edge.target_id), edge.target_id)
        chain_steps.append(
            _step(
                AnimationStepKind.TRAVERSE,
                i * 2 + 1,
                edge_ids=[edge.id],
                caption=f"The effect travels from {edge.source_id} to {edge.target_id}",
                role="Show the propagation path of the cause along the connection",
            )
        )
        chain_steps.append(
            _step(
                AnimationStepKind.HIGHLIGHT,
                i * 2 + 2,
                node_ids=[edge.target_id],
                caption=f"{target_label} is now affected in turn",
                role="Show that the destination responds to what propagated",
            )
        )

    scenes: list[AnimationScene] = []
    for chunk in _chunk_steps(reveal_steps):
        scenes.append(
            AnimationScene(
                scene_index=len(scenes) + 1,
                title="The full system",
                purpose="Show every component before the effect begins",
                caption="Components and connections",
                steps=chunk,
            )
        )
    for chunk in _chunk_steps(chain_steps):
        scenes.append(
            AnimationScene(
                scene_index=len(scenes) + 1,
                title="The effect propagates",
                purpose="Trace the cause->effect chain along each connection",
                caption="Cause leads to effect, which becomes the next cause",
                steps=chunk,
            )
        )
    return scenes[:MAX_SCENES_PER_ANIMATION]


def _build_state_transition(
    nodes: list[VisualNode], edges: list[VisualEdge]
) -> list[AnimationScene]:
    reveal_steps = [
        _step(
            AnimationStepKind.REVEAL,
            i + 1,
            node_ids=[node.id],
            caption=f"State: {node.label}",
            role="Introduce every reachable state before any transition",
        )
        for i, node in enumerate(nodes)
    ]

    transition_steps: list[AnimationStep] = []
    for i, edge in enumerate(edges[:_MAX_TRAVERSE_STEPS]):
        target_label = next((n.label for n in nodes if n.id == edge.target_id), edge.target_id)
        source_label = next((n.label for n in nodes if n.id == edge.source_id), edge.source_id)
        transition_steps.append(
            _step(
                AnimationStepKind.TRANSFORM,
                i * 2 + 1,
                node_ids=[edge.target_id],
                caption=f"The system enters state '{target_label}'",
                role="Show a state becoming active as the system moves",
                transform_note=f"from {source_label} to {target_label}",
            )
        )
        transition_steps.append(
            _step(
                AnimationStepKind.HIGHLIGHT,
                i * 2 + 2,
                node_ids=[edge.source_id],
                caption=f"'{source_label}' has been left behind",
                role="Make explicit that leaving one state enables the next",
            )
        )

    scenes: list[AnimationScene] = []
    for chunk in _chunk_steps(reveal_steps):
        scenes.append(
            AnimationScene(
                scene_index=len(scenes) + 1,
                title="All states of the system",
                purpose="Show the full set of states the system can occupy",
                caption="State set",
                steps=chunk,
            )
        )
    for chunk in _chunk_steps(transition_steps):
        scenes.append(
            AnimationScene(
                scene_index=len(scenes) + 1,
                title="Transitions in action",
                purpose="Walk each transition and name which state becomes active",
                caption="Each arrow is a legal change of state",
                steps=chunk,
            )
        )
    return scenes[:MAX_SCENES_PER_ANIMATION]


def _build_comparison_reveal(columns: list[VisualColumn]) -> list[AnimationScene]:
    if len(columns) < 2:
        raise ValueError("comparison animation requires at least two columns in the base visual")
    a, b = columns[0], columns[1]

    header_steps = [
        _step(
            AnimationStepKind.REVEAL,
            1,
            node_ids=["col_a"],
            caption=f"Side by side: {a.header}",
            role="Introduce the first entity being compared",
        ),
        _step(
            AnimationStepKind.REVEAL,
            2,
            node_ids=["col_b"],
            caption=f"Side by side: {b.header}",
            role="Introduce the second entity being compared",
        ),
    ]

    row_steps: list[AnimationStep] = []
    common = max(len(a.items), len(b.items))
    for row in range(min(common, _ROW_REVEAL_LIMIT)):
        ia = a.items[row] if row < len(a.items) else ""
        ib = b.items[row] if row < len(b.items) else ""
        idx = len(row_steps) + 1
        row_steps.append(
            _step(
                AnimationStepKind.HIGHLIGHT,
                idx,
                node_ids=["col_a"],
                caption=ia if ia else f"({a.header}: no further row)",
                role="Reveal one dimension of the first entity",
            )
        )
        row_steps.append(
            _step(
                AnimationStepKind.HIGHLIGHT,
                idx + 1,
                node_ids=["col_b"],
                caption=ib if ib else f"({b.header}: no further row)",
                role="Reveal the matching dimension of the second entity so the difference is visible side by side",
            )
        )

    scenes = [
        AnimationScene(
            scene_index=1,
            title="Two entities side by side",
            purpose="Place both columns before comparing any detail",
            caption=f"{a.header} vs {b.header}",
            steps=header_steps,
        ),
        AnimationScene(
            scene_index=2,
            title="Compare dimension by dimension",
            purpose="Reveal each pair of rows so similarities and differences surface one at a time",
            caption="Row-by-row comparison",
            steps=row_steps,
        ),
    ]
    return scenes


def _build_hierarchy_zoom(nodes: list[VisualNode], edges: list[VisualEdge]) -> list[AnimationScene]:
    if not nodes:
        return [_build_empty_scene()]
    root_id = nodes[0].id
    levels: list[list[VisualNode]] = []
    seen: set[str] = set()

    def remaining(node_id: str) -> tuple[str, ...]:
        order: list[str] = []
        for edge in edges:
            if edge.source_id == node_id and edge.target_id not in seen:
                order.append(edge.target_id)
        return tuple(order)

    current = [nodes[0]]
    while current:
        level = [n for n in current if n.id not in seen]
        if not level:
            break
        seen.update(n.id for n in level)
        levels.append(level)
        nxt: list[VisualNode] = []
        for node in level:
            for child_id in remaining(node.id):
                child = next((n for n in nodes if n.id == child_id), None)
                if child is not None:
                    nxt.append(child)
        current = nxt

    scenes: list[AnimationScene] = []
    for level_idx, level in enumerate(levels[:MAX_SCENES_PER_ANIMATION]):
        steps = [
            _step(
                AnimationStepKind.REVEAL,
                i + 1,
                node_ids=[node.id],
                caption=(
                    f"Level {level_idx + 1}: {node.label}"
                    if level_idx == 0 or node.id == root_id
                    else f"{node.label} (child of {_parent_label(edges, node.id, nodes)})"
                ),
                role="Progressively disclose one hierarchy level at a time",
            )
            for i, node in enumerate(level)
        ]
        scenes.append(
            AnimationScene(
                scene_index=len(scenes) + 1,
                title=f"Level {level_idx + 1}" if level_idx else "Root",
                purpose="Reveal the tree level by level so the grouping stays legible",
                caption=(
                    "The top of the classification"
                    if level_idx == 0
                    else f"{len(level)} children at depth {level_idx}"
                ),
                steps=steps,
            )
        )
    return scenes


def _build_timeline_progress(nodes: list[VisualNode]) -> list[AnimationScene]:
    reveal_steps = [
        _step(
            AnimationStepKind.REVEAL,
            i + 1,
            node_ids=[node.id],
            caption=f"Milestone {i + 1}: {node.label}",
            role="Place every milestone on the timeline in chronological order",
        )
        for i, node in enumerate(nodes)
    ]
    scenes: list[AnimationScene] = []
    for chunk in _chunk_steps(reveal_steps):
        scenes.append(
            AnimationScene(
                scene_index=len(scenes) + 1,
                title="The timeline",
                purpose="Reveal how the content evolves chronologically",
                caption=f"{len(nodes)} milestones in order",
                steps=chunk,
            )
        )
    return scenes[:MAX_SCENES_PER_ANIMATION]


def _build_cycle_loop(nodes: list[VisualNode], edges: list[VisualEdge]) -> list[AnimationScene]:
    reveal_steps = [
        _step(
            AnimationStepKind.REVEAL,
            i + 1,
            node_ids=[node.id],
            caption=f"Phase {i + 1}: {node.label}",
            role="Introduce every phase of the repeating cycle",
        )
        for i, node in enumerate(nodes)
    ]

    loop_steps: list[AnimationStep] = []
    for i, edge in enumerate(edges[:_MAX_TRAVERSE_STEPS]):
        loop_steps.append(
            _step(
                AnimationStepKind.TRAVERSE,
                i + 1,
                edge_ids=[edge.id],
                caption=f"The cycle advances from {edge.source_id} to {edge.target_id}",
                role="Trace the flow that makes the cycle repeat",
            )
        )
    if loop_steps:
        loop_steps.append(
            _step(
                AnimationStepKind.ANNOTATE,
                len(loop_steps) + 1,
                caption="Completing the last phase returns to the first — the cycle repeats",
                role="State explicitly that the loop feeds back into itself",
            )
        )

    scenes: list[AnimationScene] = []
    for chunk in _chunk_steps(reveal_steps):
        scenes.append(
            AnimationScene(
                scene_index=len(scenes) + 1,
                title="The phases",
                purpose="Show every phase of the cycle before it turns",
                caption="Phases of the cycle",
                steps=chunk,
            )
        )
    for chunk in _chunk_steps(loop_steps):
        scenes.append(
            AnimationScene(
                scene_index=len(scenes) + 1,
                title="The cycle turns",
                purpose="Follow the loop as it feeds back to its start",
                caption="Feed-back makes the process circular",
                steps=chunk,
            )
        )
    return scenes[:MAX_SCENES_PER_ANIMATION]


def _build_network_flow(nodes: list[VisualNode], edges: list[VisualEdge]) -> list[AnimationScene]:
    reveal_steps = [
        _step(
            AnimationStepKind.REVEAL,
            i + 1,
            node_ids=[node.id],
            caption=f"Network element: {node.label}",
            role="Place each element of the network before traffic moves",
        )
        for i, node in enumerate(nodes)
    ]

    flow_steps: list[AnimationStep] = []
    for i, edge in enumerate(edges[:_MAX_TRAVERSE_STEPS]):
        target_label = next((n.label for n in nodes if n.id == edge.target_id), edge.target_id)
        flow_steps.append(
            _step(
                AnimationStepKind.TRAVERSE,
                i * 2 + 1,
                edge_ids=[edge.id],
                caption=f"Traffic flows from {edge.source_id} to {edge.target_id}",
                role="Show where data moves across the network",
            )
        )
        flow_steps.append(
            _step(
                AnimationStepKind.HIGHLIGHT,
                i * 2 + 2,
                node_ids=[edge.target_id],
                caption=f"{target_label} receives the traffic",
                role="Show the receiving side of each connection",
            )
        )

    scenes: list[AnimationScene] = []
    for chunk in _chunk_steps(reveal_steps):
        scenes.append(
            AnimationScene(
                scene_index=len(scenes) + 1,
                title="The full network",
                purpose="Show every element and connection before the flow begins",
                caption="Elements of the network",
                steps=chunk,
            )
        )
    for chunk in _chunk_steps(flow_steps):
        scenes.append(
            AnimationScene(
                scene_index=len(scenes) + 1,
                title="Traffic in motion",
                purpose="Follow packets along each connection to see how data reaches its destination",
                caption="Flows across the network",
                steps=chunk,
            )
        )
    return scenes[:MAX_SCENES_PER_ANIMATION]


def _build_empty_scene() -> AnimationScene:
    return AnimationScene(
        scene_index=1,
        title="Overview",
        purpose="Placeholder scene for an empty base specification",
        caption="No elements to animate",
        steps=[
            _step(
                AnimationStepKind.ANNOTATE,
                1,
                caption="This topic did not yield animatable elements.",
                role="Graceful empty state",
            )
        ],
    )


def _parent_label(edges: list[VisualEdge], node_id: str, nodes: list[VisualNode]) -> str:
    for edge in edges:
        if edge.target_id == node_id:
            parent = next((n for n in nodes if n.id == edge.source_id), None)
            if parent is not None:
                return parent.label
    return "the parent"


# ── Public generator ───────────────────────────────────────────────────────


def generate_animation_specification(
    base_spec: dict[str, Any],
    animation_type: C4AnimationType,
    topic_title: str,
    *,
    purpose: str = "",
    learning_objective: str = "",
    source_visual_id: str | None = None,
    base_visual_type: C3VisualType | None = None,
    source_references: list[dict[str, Any]] | None = None,
    concept_ids: list[str] | None = None,
    provenance: AnimationSourceProvenance = AnimationSourceProvenance.AI_EXPLAINED,
) -> AnimationSpecification:
    """Generate a complete, bounded AnimationSpecification from a C3 base
    specification. The result always validates against the C4 schema (or
    raises ValueError for unsupported/anomalous inputs that the pipeline
    records as a failed generation)."""
    if not base_spec:
        raise ValueError("cannot animate an empty base specification")

    columns = _columns_from(base_spec)

    if animation_type == C4AnimationType.COMPARISON_REVEAL:
        if len(columns) < 2:
            raise ValueError(
                "comparison animation requires at least two columns in the base visual"
            )
        a, b = columns[0], columns[1]
        nodes = [
            VisualNode(id="col_a", label=a.header[:120], description=" | ".join(a.items)[:400]),
            VisualNode(id="col_b", label=b.header[:120], description=" | ".join(b.items)[:400]),
        ]
        edges: list[VisualEdge] = []
        scenes = _build_comparison_reveal(columns)
    else:
        nodes = _derive_nodes(base_spec)
        node_ids = {n.id for n in nodes}
        edges = _edges_from(base_spec, node_ids)
        if animation_type == C4AnimationType.PROCESS_SEQUENCE:
            if not nodes:
                raise ValueError("process sequence requires at least one stage in the base visual")
            scenes = _build_process_sequence(nodes, edges)
        elif animation_type == C4AnimationType.CAUSE_EFFECT_CHAIN:
            if not nodes:
                raise ValueError(
                    "cause-effect chain requires at least one element in the base visual"
                )
            scenes = _build_cause_effect_chain(nodes, edges)
        elif animation_type == C4AnimationType.STATE_TRANSITION:
            if not nodes:
                raise ValueError("state transition requires at least one state in the base visual")
            scenes = _build_state_transition(nodes, edges)
        elif animation_type == C4AnimationType.HIERARCHY_ZOOM:
            scenes = _build_hierarchy_zoom(nodes, edges)
        elif animation_type == C4AnimationType.TIMELINE_PROGRESS:
            if not nodes:
                raise ValueError(
                    "timeline progress requires at least one milestone in the base visual"
                )
            scenes = _build_timeline_progress(nodes)
        elif animation_type == C4AnimationType.CYCLE_LOOP:
            if not nodes:
                raise ValueError("cycle loop requires at least one phase in the base visual")
            scenes = _build_cycle_loop(nodes, edges)
        elif animation_type == C4AnimationType.NETWORK_FLOW:
            if not nodes:
                raise ValueError("network flow requires at least one element in the base visual")
            scenes = _build_network_flow(nodes, edges)
        else:
            raise ValueError(f"unsupported animation type: {animation_type.value}")

    if not scenes:
        scenes = [_build_empty_scene()]

    interactions = _build_interactions(animation_type, scenes, topic_title, nodes)
    type_base = str(base_visual_type.value) if base_visual_type else "visual"
    spec = AnimationSpecification(
        animation_type=animation_type,
        title=f"Learn: {topic_title[:400]}",
        purpose=purpose or _default_purpose(animation_type, topic_title),
        learning_objective=learning_objective,
        base_visual_type=base_visual_type,
        source_visual_id=source_visual_id,
        nodes=nodes,
        edges=edges,
        scenes=scenes,
        interactions=interactions,
        pedagogical_rationale=_default_purpose(animation_type, topic_title),
        concept_ids=concept_ids or [],
        source_references=source_references or [],
        provenance=provenance,
    )
    spec = AnimationSpecification.model_validate(spec.model_dump())
    logger.info(
        "Generated C4 animation spec type=%s scenes=%d nodes=%d duration_ms=%d base=%s",
        animation_type.value,
        len(spec.scenes),
        len(spec.nodes),
        spec.total_duration_ms,
        type_base,
    )
    return spec


def _build_interactions(
    animation_type: C4AnimationType,
    scenes: list[AnimationScene],
    topic_title: str,
    nodes: list[VisualNode],
) -> list[AnimationInteraction]:
    """Add one self-check interaction anchored at the last visible step when a
    sensible anchor exists and the spec stays within interaction bounds."""
    anchors = [
        (scene.scene_index, step)
        for scene in scenes
        for step in scene.steps
        if step.kind != AnimationStepKind.PAUSE
    ]
    if not anchors:
        return []
    scene_index, anchor = anchors[-1]
    # Ask about information actually represented; sequence alone does not prove
    # a causal dependency, and the first node need not have a predecessor.
    target = next(
        (node for node in nodes if node.id in anchor.node_ids),
        nodes[-1] if nodes else None,
    )
    label = target.label if target else topic_title
    answer = (target.description if target else "") or anchor.caption
    if not answer:
        return []
    return [
        AnimationInteraction(
            interaction_index=1,
            kind=AnimationInteractionKind.SELF_CHECK,
            anchor_scene_index=scene_index,
            anchor_step_index=anchor.step_index,
            prompt=f"Explain what '{label}' represents in this diagram in your own words.",
            answer=answer,
            guide_hint="Use the labels and explanation shown, then compare your answer.",
        )
    ]


def _default_purpose(animation_type: C4AnimationType, topic_title: str) -> str:
    purposes = {
        C4AnimationType.PROCESS_SEQUENCE: (
            "Show the order and pacing of the steps, which a static diagram cannot convey."
        ),
        C4AnimationType.CAUSE_EFFECT_CHAIN: (
            "Show how a cause propagates into effects, which a static diagram can only label."
        ),
        C4AnimationType.STATE_TRANSITION: (
            "Show the system moving between states, making each transition a visible event."
        ),
        C4AnimationType.COMPARISON_REVEAL: (
            "Reveal differences side by side one dimension at a time."
        ),
        C4AnimationType.HIERARCHY_ZOOM: (
            "Disclose the tree level by level so grouping stays legible."
        ),
        C4AnimationType.TIMELINE_PROGRESS: (
            "Show how the topic evolves chronologically milestone by milestone."
        ),
        C4AnimationType.CYCLE_LOOP: ("Show the cycle turning and feeding back into itself."),
        C4AnimationType.NETWORK_FLOW: (
            "Follow traffic across the network so flow becomes visible movement."
        ),
    }
    return purposes.get(animation_type, "Animate what a static diagram cannot express.")


def build_animation_explanation(
    animation_type: C4AnimationType,
    animation_spec: AnimationSpecification,
    topic_title: str,
) -> dict[str, str]:
    """Return the student-facing explanation panel content for an animation."""
    type_titles = {
        C4AnimationType.PROCESS_SEQUENCE: "Sequence animation",
        C4AnimationType.CAUSE_EFFECT_CHAIN: "Cause-and-effect chain",
        C4AnimationType.STATE_TRANSITION: "State transition",
        C4AnimationType.COMPARISON_REVEAL: "Side-by-side comparison",
        C4AnimationType.HIERARCHY_ZOOM: "Hierarchy drill-down",
        C4AnimationType.TIMELINE_PROGRESS: "Timeline progress",
        C4AnimationType.CYCLE_LOOP: "Cycle",
        C4AnimationType.NETWORK_FLOW: "Network flow",
    }
    return {
        "what_you_see": (
            f"This {type_titles.get(animation_type, 'animation')} shows '{topic_title}' "
            f"in {len(animation_spec.scenes)} scenes and "
            f"{animation_spec.total_duration_ms // 1000} seconds of guided motion."
        ),
        "how_to_read": (
            "Watch each highlighted element in order, read the caption, then use the "
            "controls to replay, pause, or step forward one motion at a time."
        ),
        "key_takeaway": (
            animation_spec.purpose
            or "The motion shows the order, cause, or state change that a static image cannot."
        ),
        "motion_justification": animation_spec.pedagogical_rationale,
    }
