"""Unit Tests for Phase 4I.3 Visual Persistence & Graph Validation Layer.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.visual_intelligence import (
    CategoryClassification,
    ComponentRelationship,
    DiscoveredComponent,
    InputDescriptor,
    OutputDescriptor,
    RelationshipType,
    TopicCategory,
    VisualEdgeSchema,
    VisualizationDecision,
    VisualizationType,
    VisualLearningModel,
    VisualNodeSchema,
)
from app.services.visual_persistence_service import (
    VisualGraphValidationError,
    VisualPersistenceService,
)


@pytest.fixture
def mock_visual_model() -> VisualLearningModel:
    comp1 = DiscoveredComponent(
        component_id="comp_cpu",
        name="CPU Processor",
        category="core",
        short_description="Executes program instructions",
        detailed_working="Fetches, decodes, and executes opcodes.",
        inputs=[InputDescriptor(name="Instructions", type="binary")],
        outputs=[OutputDescriptor(name="Results", type="data")],
        real_world_analogy="Restaurant kitchen head chef",
    )
    comp2 = DiscoveredComponent(
        component_id="comp_ram",
        name="System RAM",
        category="memory",
        short_description="Primary random access memory",
        detailed_working="Holds active programs and data.",
        inputs=[InputDescriptor(name="Address", type="pointer")],
        outputs=[OutputDescriptor(name="Word", type="data")],
        real_world_analogy="Chef prep table",
    )

    node1 = VisualNodeSchema(
        node_id="comp_cpu",
        label="CPU Processor",
        category="core",
        position={"x": 400.0, "y": 200.0},  # type: ignore
    )
    node2 = VisualNodeSchema(
        node_id="comp_ram",
        label="System RAM",
        category="memory",
        position={"x": 100.0, "y": 200.0},  # type: ignore
    )

    edge1 = VisualEdgeSchema(
        edge_id="edge_ram_cpu",
        source_node_id="comp_ram",
        target_node_id="comp_cpu",
        label="Fetches Instructions",
        relationship_type=RelationshipType.DATA_FLOW,
    )

    rel1 = ComponentRelationship(
        source_id="comp_ram",
        target_id="comp_cpu",
        relationship_type=RelationshipType.DATA_FLOW,
        description="RAM provides instructions to CPU",
    )

    return VisualLearningModel(
        topic="Von Neumann Computer Architecture",
        classification=CategoryClassification(
            primary_category=TopicCategory.SYSTEM_ARCHITECTURE,
            confidence_score=0.95,
        ),
        learning_objectives={  # type: ignore
            "main_goal": "Understand von Neumann system interactions",
            "learning_objectives": ["Identify CPU and RAM roles"],
            "important_ideas": ["Fetch-Execute cycle"],
            "prerequisites": ["Basic binary representation"],
            "expected_outcomes": ["Explain instruction fetch cycle"],
        },
        visualization_decision=VisualizationDecision(
            visualization_type=VisualizationType.BLOCK_DIAGRAM,
            reason="Block diagram clarifies hardware module boundaries.",
            confidence=0.95,
        ),
        components=[comp1, comp2],
        relationships=[rel1],
        visual_nodes=[node1, node2],
        visual_edges=[edge1],
        examples=["Personal Computer Motherboard Layout"],
        future_simulation_candidates=["CPU Instruction Fetch Simulator"],
        quiz_focus_areas=["CPU ALU Function", "RAM Addressing"],
    )


@pytest.mark.asyncio
async def test_save_and_load_visual_learning_model(
    db_session: AsyncSession,
    mock_visual_model: VisualLearningModel,
):
    """Verify that VisualPersistenceService correctly saves and loads graph entities."""
    service = VisualPersistenceService(db_session)

    canvas = await service.save_visual_model(
        mock_visual_model,
        user_id=None,
    )
    assert canvas.id is not None
    assert canvas.public_id.startswith("canvas_")
    assert canvas.title == "Von Neumann Computer Architecture"

    loaded_model = await service.load_visual_model(canvas.id)
    assert loaded_model.topic == mock_visual_model.topic
    assert loaded_model.classification.primary_category == TopicCategory.SYSTEM_ARCHITECTURE
    assert len(loaded_model.components) == 2
    assert len(loaded_model.visual_nodes) == 2
    assert len(loaded_model.visual_edges) == 1
    assert loaded_model.visual_edges[0].source_node_id == "comp_ram"



def test_graph_validation_broken_edges(mock_visual_model: VisualLearningModel):
    """Verify graph validation catches broken edges pointing to non-existent nodes."""
    service = VisualPersistenceService(None)  # type: ignore

    # Introduce a broken edge pointing to a ghost node
    mock_visual_model.visual_edges.append(
        VisualEdgeSchema(
            edge_id="edge_broken",
            source_node_id="comp_cpu",
            target_node_id="non_existent_node",
            relationship_type=RelationshipType.SEQUENTIAL_FLOW,
        )
    )

    with pytest.raises(VisualGraphValidationError) as exc_info:
        service.validate_graph_integrity(mock_visual_model)

    assert "broken edges" in str(exc_info.value)
