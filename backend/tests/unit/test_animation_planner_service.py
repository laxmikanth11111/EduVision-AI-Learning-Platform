"""Unit Tests for Phase 4J.1 + 4J.2 AI Animation Engine Architecture & Planner.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.visual_intelligence import (
    CategoryClassification,
    DiscoveredComponent,
    LearningObjectives,
    TopicCategory,
    VisualizationDecision,
    VisualizationType,
    VisualLearningModel,
)
from app.services.animation_classification_service import animation_classification_service
from app.services.animation_planner_service import animation_planner_service


def _make_model(topic: str, components: list[DiscoveredComponent]) -> VisualLearningModel:
    return VisualLearningModel(
        topic=topic,
        classification=CategoryClassification(primary_category=TopicCategory.PROCESS, confidence_score=0.9),
        learning_objectives=LearningObjectives(main_goal=f"Learn {topic}", learning_objectives=[f"Understand {topic}"]),
        visualization_decision=VisualizationDecision(visualization_type=VisualizationType.FLOWCHART, reason="Sequential flow layout", confidence=0.9),
        components=components,
    )


def test_animation_layout_classification():
    """Verify layout classification engine selects optimal animation style and focus order."""
    class_flow = animation_classification_service.classify_layout("flowchart", ["n1", "n2"])
    assert class_flow.recommended_style.value == "flow_along_edge"

    class_tree = animation_classification_service.classify_layout("hierarchy", ["root", "c1"])
    assert class_tree.recommended_style.value == "node_expansion"

    class_net = animation_classification_service.classify_layout("network_graph", ["n1"])
    assert class_net.recommended_style.value == "focus_zoom"


def test_animation_planner_blueprint_creation():
    """Verify planner service constructs valid AnimationBlueprint, scenes, timeline, and narration cues."""
    model = _make_model(
        topic="Instruction Pipeline",
        components=[
            DiscoveredComponent(
                component_id="c_fetch",
                name="Fetch Stage",
                short_description="Fetches instruction opcode",
                detailed_working="Loads byte from memory",
            ),
            DiscoveredComponent(
                component_id="c_decode",
                name="Decode Stage",
                short_description="Decodes instruction opcode",
                detailed_working="Determines ALU control flags",
            ),
            DiscoveredComponent(
                component_id="c_exec",
                name="Execute Stage",
                short_description="Executes arithmetic operation",
                detailed_working="Computes ALU result",
            ),
        ],
    )

    blueprint = animation_planner_service.create_blueprint(model)
    assert blueprint.topic == "Instruction Pipeline"
    assert len(blueprint.timeline.scenes) == 4  # Intro + 3 components
    assert blueprint.timeline.total_events >= 7
    assert blueprint.validation.is_valid is True
    assert blueprint.validation.coverage_score == 100.0


@pytest.mark.asyncio
async def test_animation_api_endpoints(
    client: AsyncClient,
    db_session: AsyncSession,
):
    # 1. Plan Blueprint Endpoint
    plan_res = await client.post(
        "/api/v1/animations/plan",
        json={
            "topic": "Neural Network Forward Pass",
            "layout_category": "network_graph",
            "components": [
                {
                    "component_id": "c_in",
                    "name": "Input Layer",
                    "short_description": "Input neuron array",
                    "detailed_working": "Passes vector features",
                },
                {
                    "component_id": "c_out",
                    "name": "Output Layer",
                    "short_description": "Output neuron array",
                    "detailed_working": "Computes loss probability",
                },
            ],
        },
    )
    assert plan_res.status_code == 201
    bp_data = plan_res.json()["data"]
    blueprint_id = bp_data["blueprint_id"]

    # 2. Get Blueprint Endpoint
    bp_res = await client.get(f"/api/v1/animations/{blueprint_id}")
    assert bp_res.status_code == 200
    assert bp_res.json()["data"]["blueprint_id"] == blueprint_id

    # 3. Get Scenes Endpoint
    scenes_res = await client.get(f"/api/v1/animations/{blueprint_id}/scenes")
    assert scenes_res.status_code == 200
    assert len(scenes_res.json()["data"]) >= 2

    # 4. Get Timeline Endpoint
    time_res = await client.get(f"/api/v1/animations/{blueprint_id}/timeline")
    assert time_res.status_code == 200
    assert time_res.json()["data"]["total_duration_ms"] > 0

    # 5. Get Metadata Endpoint
    meta_res = await client.get(f"/api/v1/animations/{blueprint_id}/metadata")
    assert meta_res.status_code == 200
    assert meta_res.json()["data"]["scenes_count"] >= 2
