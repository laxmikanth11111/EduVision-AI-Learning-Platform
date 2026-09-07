"""C3 Visual Specification Generator — creates structured specs from topic/subtopic data.

Takes the topic outline structure (C2) and visual need decision, and produces a
complete VisualSpecification that a rendering engine can faithfully implement.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.core.logging import get_logger
from app.schemas.c3_visual_intelligence import (
    C3VisualType,
    VisualColumn,
    VisualEdge,
    VisualNode,
    VisualSpecification,
    VisualStep,
)
from app.schemas.topic_outline import OutlineTopic, Subtopic

logger = get_logger(__name__)


def generate_visual_specification(
    topic: OutlineTopic,
    subtopic: Subtopic | None = None,
    visual_type: C3VisualType | None = None,
    *,
    fallback_type: C3VisualType = C3VisualType.CONCEPT_MAP,
) -> VisualSpecification:
    """Generate a structured visual specification from topic/subtopic data.

    Creates an educational source-of-truth specification that the rendering
    engine must faithfully implement.
    """
    effective_type = visual_type or fallback_type
    target = subtopic or topic
    concepts = subtopic.concepts if subtopic else topic.concepts
    title = subtopic.title if subtopic else topic.title

    # Build the spec based on the visual type
    spec_builder = Callable[[str, Any, list[Any]], VisualSpecification]
    generators: dict[C3VisualType, spec_builder] = {
        C3VisualType.FLOWCHART: _spec_flowchart,
        C3VisualType.PROCESS_DIAGRAM: _spec_process_diagram,
        C3VisualType.COMPARISON: _spec_comparison,
        C3VisualType.HIERARCHY: _spec_hierarchy,
        C3VisualType.TIMELINE: _spec_timeline,
        C3VisualType.CYCLE: _spec_cycle,
        C3VisualType.CONCEPT_MAP: _spec_concept_map,
        C3VisualType.NETWORK_DIAGRAM: _spec_network_diagram,
        C3VisualType.SEQUENCE_DIAGRAM: _spec_sequence_diagram,
        C3VisualType.STEP_BY_STEP: _spec_step_by_step,
        C3VisualType.TABLE_VISUALIZATION: _spec_table,
        C3VisualType.ARCHITECTURE_DIAGRAM: _spec_architecture,
        C3VisualType.STATE_DIAGRAM: _spec_state_diagram,
        C3VisualType.FORMULA_VISUALIZATION: _spec_formula,
        C3VisualType.RELATIONSHIP_GRAPH: _spec_relationship_graph,
        C3VisualType.SYSTEM_DIAGRAM: _spec_architecture,
        C3VisualType.ANNOTATED_ILLUSTRATION: _spec_concept_map,
        C3VisualType.TECHNICAL_DIAGRAM: _spec_architecture,
        C3VisualType.CHART: _spec_table,
        C3VisualType.REAL_WORLD_SCENARIO: _spec_process_diagram,
    }

    generator = generators.get(effective_type, _spec_concept_map)
    spec = generator(title, target, concepts)

    # Add shared fields
    spec.learning_objective = _extract_learning_objective(target) or _extract_learning_objective(
        topic
    )
    spec.examples = [
        ex.content if hasattr(ex, "content") else str(ex)
        for ex in (target.examples if hasattr(target, "examples") else [])
    ][:3]

    return spec


def _spec_flowchart(
    title: str,
    target: Any,
    concepts: list[Any],
) -> VisualSpecification:
    """Generate a flowchart specification."""
    nodes: list[VisualNode] = []
    edges: list[VisualEdge] = []

    # Title node
    start_id = "start"
    nodes.append(
        VisualNode(
            id=start_id,
            label=title,
            node_type="start",
            style={"shape": "ellipse", "fill": "#1D9E75"},
        )
    )

    # Concept nodes as steps
    for i, concept in enumerate(concepts):
        node_id = f"step_{i}"
        name = concept.name if hasattr(concept, "name") else str(concept)
        desc = concept.description if hasattr(concept, "description") else ""
        nodes.append(
            VisualNode(
                id=node_id,
                label=name,
                description=desc,
                node_type="process",
                style={"shape": "rectangle", "fill": "#0E1A2B"},
            )
        )
        edges.append(
            VisualEdge(
                id=f"e_{i}",
                source_id=start_id if i == 0 else f"step_{i - 1}",
                target_id=node_id,
                label="",
            )
        )
        start_id = node_id

    # End node
    end_id = "end"
    nodes.append(
        VisualNode(
            id=end_id,
            label="Complete",
            node_type="end",
            style={"shape": "ellipse", "fill": "#D85A30"},
        )
    )
    if concepts:
        edges.append(
            VisualEdge(
                id="e_end",
                source_id=f"step_{len(concepts) - 1}",
                target_id=end_id,
            )
        )

    return VisualSpecification(
        visual_type=C3VisualType.FLOWCHART,
        title=title,
        purpose=f"Show the sequential flow of {title}",
        nodes=nodes,
        edges=edges,
        steps=[
            VisualStep(
                step_number=i + 1,
                title=c.name if hasattr(c, "name") else str(c),
                description=c.description if hasattr(c, "description") else "",
            )
            for i, c in enumerate(concepts)
        ],
    )


def _spec_process_diagram(
    title: str,
    target: Any,
    concepts: list[Any],
) -> VisualSpecification:
    """Generate a process diagram specification."""
    nodes: list[VisualNode] = []
    edges: list[VisualEdge] = []

    for i, concept in enumerate(concepts):
        node_id = f"stage_{i}"
        name = concept.name if hasattr(concept, "name") else str(concept)
        desc = concept.description if hasattr(concept, "description") else ""
        nodes.append(
            VisualNode(
                id=node_id,
                label=name,
                description=desc,
                node_type="stage",
                style={"shape": "rounded_rect", "fill": "#0E1A2B", "stroke": "#F2A623"},
            )
        )
        if i > 0:
            edges.append(
                VisualEdge(
                    id=f"e_{i}",
                    source_id=f"stage_{i - 1}",
                    target_id=node_id,
                    label="→",
                )
            )

    return VisualSpecification(
        visual_type=C3VisualType.PROCESS_DIAGRAM,
        title=title,
        purpose=f"Show the process stages of {title}",
        nodes=nodes,
        edges=edges,
    )


def _spec_comparison(
    title: str,
    target: Any,
    concepts: list[Any],
) -> VisualSpecification:
    """Generate a comparison specification."""
    columns: list[VisualColumn] = []

    # Group concepts into comparison columns if possible
    if len(concepts) >= 2:
        # Try to group by pairs
        for i in range(0, len(concepts), 2):
            group = concepts[i : i + 2]
            for concept in group:
                name = concept.name if hasattr(concept, "name") else str(concept)
                desc = concept.description if hasattr(concept, "description") else ""
                columns.append(
                    VisualColumn(
                        header=name,
                        items=[desc] if desc else [],
                    )
                )
    else:
        for concept in concepts:
            name = concept.name if hasattr(concept, "name") else str(concept)
            desc = concept.description if hasattr(concept, "description") else ""
            columns.append(
                VisualColumn(
                    header=name,
                    items=[desc] if desc else [],
                )
            )

    # Fallback if no concepts
    if not columns:
        columns = [VisualColumn(header="Items", items=["Item A", "Item B"])]

    return VisualSpecification(
        visual_type=C3VisualType.COMPARISON,
        title=title,
        purpose=f"Compare elements of {title}",
        columns=columns,
    )


def _spec_hierarchy(
    title: str,
    target: Any,
    concepts: list[Any],
) -> VisualSpecification:
    """Generate a hierarchy/tree specification."""
    nodes: list[VisualNode] = []
    edges: list[VisualEdge] = []

    # Root node
    root_id = "root"
    nodes.append(
        VisualNode(
            id=root_id,
            label=title,
            node_type="root",
            style={"shape": "rectangle", "fill": "#F2A623", "font_color": "#0E1A2B"},
        )
    )

    # Level 1 children
    for i, concept in enumerate(concepts):
        node_id = f"child_{i}"
        name = concept.name if hasattr(concept, "name") else str(concept)
        desc = concept.description if hasattr(concept, "description") else ""
        nodes.append(
            VisualNode(
                id=node_id,
                label=name,
                description=desc,
                node_type="child",
                style={"shape": "rectangle", "fill": "#0E1A2B"},
            )
        )
        edges.append(
            VisualEdge(
                id=f"e_{i}",
                source_id=root_id,
                target_id=node_id,
            )
        )

    return VisualSpecification(
        visual_type=C3VisualType.HIERARCHY,
        title=title,
        purpose=f"Show the hierarchical structure of {title}",
        nodes=nodes,
        edges=edges,
    )


def _spec_timeline(
    title: str,
    target: Any,
    concepts: list[Any],
) -> VisualSpecification:
    """Generate a timeline specification."""
    steps = [
        VisualStep(
            step_number=i + 1,
            title=c.name if hasattr(c, "name") else str(c),
            description=c.description if hasattr(c, "description") else "",
        )
        for i, c in enumerate(concepts)
    ]

    return VisualSpecification(
        visual_type=C3VisualType.TIMELINE,
        title=title,
        purpose=f"Show the chronological sequence of {title}",
        steps=steps,
    )


def _spec_cycle(
    title: str,
    target: Any,
    concepts: list[Any],
) -> VisualSpecification:
    """Generate a cycle/circular diagram specification."""
    nodes: list[VisualNode] = []
    edges: list[VisualEdge] = []
    import math

    n = len(concepts) or 1
    for i, concept in enumerate(concepts):
        node_id = f"phase_{i}"
        name = concept.name if hasattr(concept, "name") else str(concept)
        angle = 2 * math.pi * i / n
        nodes.append(
            VisualNode(
                id=node_id,
                label=name,
                node_type="phase",
                position={"x": 0.5 + 0.35 * math.cos(angle), "y": 0.5 + 0.35 * math.sin(angle)},
                style={"shape": "circle", "fill": "#0E1A2B"},
            )
        )

    for i in range(n):
        next_i = (i + 1) % n
        edges.append(
            VisualEdge(
                id=f"e_{i}",
                source_id=f"phase_{i}",
                target_id=f"phase_{next_i}",
            )
        )

    return VisualSpecification(
        visual_type=C3VisualType.CYCLE,
        title=title,
        purpose=f"Show the cyclical nature of {title}",
        nodes=nodes,
        edges=edges,
    )


def _spec_concept_map(
    title: str,
    target: Any,
    concepts: list[Any],
) -> VisualSpecification:
    """Generate a concept map / mind map specification."""
    nodes: list[VisualNode] = []
    edges: list[VisualEdge] = []

    # Central concept
    center_id = "center"
    nodes.append(
        VisualNode(
            id=center_id,
            label=title,
            node_type="center",
            style={"shape": "ellipse", "fill": "#F2A623", "font_color": "#0E1A2B"},
        )
    )

    import math

    n = len(concepts) or 1
    for i, concept in enumerate(concepts):
        node_id = f"concept_{i}"
        name = concept.name if hasattr(concept, "name") else str(concept)
        desc = concept.description if hasattr(concept, "description") else ""
        angle = 2 * math.pi * i / n
        nodes.append(
            VisualNode(
                id=node_id,
                label=name,
                description=desc,
                node_type="concept",
                position={"x": 0.5 + 0.35 * math.cos(angle), "y": 0.5 + 0.35 * math.sin(angle)},
                style={"shape": "rectangle", "fill": "#0E1A2B"},
            )
        )
        edges.append(
            VisualEdge(
                id=f"e_{i}",
                source_id=center_id,
                target_id=node_id,
                label="relates to",
            )
        )

    return VisualSpecification(
        visual_type=C3VisualType.CONCEPT_MAP,
        title=title,
        purpose=f"Map the key concepts of {title}",
        nodes=nodes,
        edges=edges,
    )


def _spec_network_diagram(
    title: str,
    target: Any,
    concepts: list[Any],
) -> VisualSpecification:
    """Generate a network diagram specification."""
    nodes: list[VisualNode] = []
    edges: list[VisualEdge] = []

    for i, concept in enumerate(concepts):
        node_id = f"node_{i}"
        name = concept.name if hasattr(concept, "name") else str(concept)
        desc = concept.description if hasattr(concept, "description") else ""
        nodes.append(
            VisualNode(
                id=node_id,
                label=name,
                description=desc,
                node_type="network_node",
                style={"shape": "circle", "fill": "#0E1A2B", "stroke": "#1D9E75"},
            )
        )

    # Connect consecutive nodes
    for i in range(len(concepts) - 1):
        edges.append(
            VisualEdge(
                id=f"e_{i}",
                source_id=f"node_{i}",
                target_id=f"node_{i + 1}",
            )
        )
    # Bidirectional last-to-first if 3+ nodes
    if len(concepts) >= 3:
        edges.append(
            VisualEdge(
                id="e_loop",
                source_id=f"node_{len(concepts) - 1}",
                target_id="node_0",
                is_bidirectional=True,
            )
        )

    return VisualSpecification(
        visual_type=C3VisualType.NETWORK_DIAGRAM,
        title=title,
        purpose=f"Show the network structure of {title}",
        nodes=nodes,
        edges=edges,
    )


def _spec_sequence_diagram(
    title: str,
    target: Any,
    concepts: list[Any],
) -> VisualSpecification:
    """Generate a sequence diagram specification."""
    steps = [
        VisualStep(
            step_number=i + 1,
            title=c.name if hasattr(c, "name") else str(c),
            description=c.description if hasattr(c, "description") else "",
        )
        for i, c in enumerate(concepts)
    ]

    return VisualSpecification(
        visual_type=C3VisualType.SEQUENCE_DIAGRAM,
        title=title,
        purpose=f"Show the sequential interactions of {title}",
        steps=steps,
    )


def _spec_step_by_step(
    title: str,
    target: Any,
    concepts: list[Any],
) -> VisualSpecification:
    """Generate a step-by-step specification."""
    steps = [
        VisualStep(
            step_number=i + 1,
            title=c.name if hasattr(c, "name") else str(c),
            description=c.description if hasattr(c, "description") else "",
        )
        for i, c in enumerate(concepts)
    ]

    return VisualSpecification(
        visual_type=C3VisualType.STEP_BY_STEP,
        title=title,
        purpose=f"Walk through {title} step by step",
        steps=steps,
    )


def _spec_table(
    title: str,
    target: Any,
    concepts: list[Any],
) -> VisualSpecification:
    """Generate a table visualization specification."""
    columns: list[VisualColumn] = [
        VisualColumn(
            header="Concept",
            items=[c.name if hasattr(c, "name") else str(c) for c in concepts],
        ),
        VisualColumn(
            header="Description",
            items=[c.description if hasattr(c, "description") else "" for c in concepts],
        ),
    ]

    return VisualSpecification(
        visual_type=C3VisualType.TABLE_VISUALIZATION,
        title=title,
        purpose=f"Organize {title} information in a structured table",
        columns=columns,
    )


def _spec_architecture(
    title: str,
    target: Any,
    concepts: list[Any],
) -> VisualSpecification:
    """Generate an architecture diagram specification."""
    nodes: list[VisualNode] = []
    edges: list[VisualEdge] = []

    # Layer-based layout
    for i, concept in enumerate(concepts):
        node_id = f"layer_{i}"
        name = concept.name if hasattr(concept, "name") else str(concept)
        desc = concept.description if hasattr(concept, "description") else ""
        nodes.append(
            VisualNode(
                id=node_id,
                label=name,
                description=desc,
                node_type="layer",
                position={"x": 0.5, "y": 0.15 + 0.7 * i / max(1, len(concepts) - 1)},
                style={"shape": "rectangle", "fill": "#0E1A2B", "stroke": "#F2A623"},
            )
        )
        if i > 0:
            edges.append(
                VisualEdge(
                    id=f"e_{i}",
                    source_id=f"layer_{i}",
                    target_id=f"layer_{i - 1}",
                    label="uses",
                )
            )

    return VisualSpecification(
        visual_type=C3VisualType.ARCHITECTURE_DIAGRAM,
        title=title,
        purpose=f"Show the architectural layers of {title}",
        nodes=nodes,
        edges=edges,
    )


def _spec_state_diagram(
    title: str,
    target: Any,
    concepts: list[Any],
) -> VisualSpecification:
    """Generate a state diagram specification."""
    nodes: list[VisualNode] = []
    edges: list[VisualEdge] = []

    for i, concept in enumerate(concepts):
        node_id = f"state_{i}"
        name = concept.name if hasattr(concept, "name") else str(concept)
        desc = concept.description if hasattr(concept, "description") else ""
        nodes.append(
            VisualNode(
                id=node_id,
                label=name,
                description=desc,
                node_type="state",
                style={"shape": "rounded_rect", "fill": "#0E1A2B"},
            )
        )
        if i > 0:
            edges.append(
                VisualEdge(
                    id=f"e_{i}",
                    source_id=f"state_{i - 1}",
                    target_id=node_id,
                    label="transition",
                )
            )

    return VisualSpecification(
        visual_type=C3VisualType.STATE_DIAGRAM,
        title=title,
        purpose=f"Show the state transitions of {title}",
        nodes=nodes,
        edges=edges,
    )


def _spec_formula(
    title: str,
    target: Any,
    concepts: list[Any],
) -> VisualSpecification:
    """Generate a formula visualization specification."""
    labels = [c.name if hasattr(c, "name") else str(c) for c in concepts]

    return VisualSpecification(
        visual_type=C3VisualType.FORMULA_VISUALIZATION,
        title=title,
        purpose=f"Visualize the mathematical relationships in {title}",
        labels=labels,
    )


def _spec_relationship_graph(
    title: str,
    target: Any,
    concepts: list[Any],
) -> VisualSpecification:
    """Generate a relationship graph specification."""
    nodes: list[VisualNode] = []
    edges: list[VisualEdge] = []

    import math

    n = len(concepts) or 1
    for i, concept in enumerate(concepts):
        node_id = f"rel_{i}"
        name = concept.name if hasattr(concept, "name") else str(concept)
        angle = 2 * math.pi * i / n
        nodes.append(
            VisualNode(
                id=node_id,
                label=name,
                node_type="entity",
                position={"x": 0.5 + 0.35 * math.cos(angle), "y": 0.5 + 0.35 * math.sin(angle)},
                style={"shape": "ellipse", "fill": "#1D9E75"},
            )
        )

    # Connect all to all (concept web)
    for i in range(n):
        for j in range(i + 1, n):
            edges.append(
                VisualEdge(
                    id=f"e_{i}_{j}",
                    source_id=f"rel_{i}",
                    target_id=f"rel_{j}",
                    label="related",
                    is_bidirectional=True,
                )
            )

    return VisualSpecification(
        visual_type=C3VisualType.RELATIONSHIP_GRAPH,
        title=title,
        purpose=f"Show the relationships between concepts in {title}",
        nodes=nodes,
        edges=edges,
    )


def _extract_learning_objective(target: Any) -> str:
    """Extract learning objective from target."""
    objectives = getattr(target, "learning_objectives", None)
    if objectives:
        return str(objectives[0])
    description = getattr(target, "description", None)
    if description:
        return str(description)
    return ""
