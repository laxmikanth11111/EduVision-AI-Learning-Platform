"""Unit Tests for Phase 4K.1 + 4K.2 AI Video Learning Engine Architecture.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.animation_planner_service import animation_planner_service
from app.services.video_asset_manager_service import video_asset_manager_service
from app.services.video_composition_service import video_composition_service
from app.services.video_script_service import video_script_service
from app.services.video_storyboard_service import video_storyboard_service
from app.services.video_subtitle_service import video_subtitle_service
from app.services.video_validation_service import video_validation_service


def create_stub_model():
    from app.schemas.visual_intelligence import (
        CategoryClassification,
        DiscoveredComponent,
        LearningObjectives,
        TopicCategory,
        VisualizationDecision,
        VisualizationType,
        VisualLearningModel,
    )
    return VisualLearningModel(
        topic="CPU Cache Architecture",
        classification=CategoryClassification(
            primary_category=TopicCategory.PROCESS, confidence_score=0.95
        ),
        learning_objectives=LearningObjectives(
            main_goal="Understand Cache Memory Hierarchy",
            learning_objectives=["Understand L1 vs L2 Cache"],
        ),
        visualization_decision=VisualizationDecision(
            visualization_type=VisualizationType.FLOWCHART,
            reason="Hierarchical flow",
            confidence=0.9,
        ),
        components=[
            DiscoveredComponent(
                component_id="comp_l1",
                name="L1 Cache Unit",
                category="memory",
                short_description="Ultra fast local cache",
                detailed_working="Stores hot lines for immediate access",
            )
        ],
    )


def test_video_asset_manager():
    model = create_stub_model()
    blueprint = animation_planner_service.create_blueprint(model)
    manifest = video_asset_manager_service.build_asset_manifest(
        topic="CPU Cache Architecture", model=model, blueprint=blueprint
    )
    assert manifest.total_assets > 0
    assert len(manifest.assets) == manifest.total_assets
    assert any(a.asset_type.value == "visual_canvas" for a in manifest.assets)


def test_video_storyboard_service():
    model = create_stub_model()
    blueprint = animation_planner_service.create_blueprint(model)
    storyboard = video_storyboard_service.generate_storyboard(
        topic="CPU Cache Architecture", model=model, blueprint=blueprint
    )
    assert storyboard.total_scenes >= 5
    assert storyboard.scenes[0].scene_type.value == "explanation_slide"
    assert storyboard.scenes[1].scene_type.value == "animated_visual"


def test_video_script_service():
    model = create_stub_model()
    script = video_script_service.generate_script(topic="CPU Cache Architecture", model=model)
    assert len(script.sections) >= 4
    assert script.word_count > 50
    assert script.estimated_total_spoken_minutes > 0.0


def test_video_subtitle_service():
    model = create_stub_model()
    storyboard = video_storyboard_service.generate_storyboard("CPU Cache Architecture", model=model)
    subtrack = video_subtitle_service.generate_subtitles(storyboard.scenes)
    assert len(subtrack.entries) > 0
    assert subtrack.entries[0].start_ms >= 0.0


def test_video_composition_engine():
    model = create_stub_model()
    blueprint = animation_planner_service.create_blueprint(model)
    project = video_composition_service.compose_video_project(
        topic="CPU Cache Architecture", model=model, blueprint=blueprint
    )
    assert project.topic == "CPU Cache Architecture"
    assert project.timeline.total_duration_ms > 10000.0
    assert project.validation.is_valid is True
    assert project.validation.completeness_score >= 80.0


@pytest.mark.asyncio
async def test_video_router_endpoints(
    client: AsyncClient,
    db_session: AsyncSession,
):
    # 1. Create Video Project
    create_res = await client.post(
        "/api/v1/videos/create",
        json={
            "topic": "CPU Cache Architecture",
            "target_audience": "undergraduate",
            "difficulty_level": "Intermediate",
        },
    )
    assert create_res.status_code == 201
    data = create_res.json()["data"]
    vid_id = data["video_id"]
    assert data["topic"] == "CPU Cache Architecture"

    # 2. Get Video Project
    get_res = await client.get(f"/api/v1/videos/{vid_id}")
    assert get_res.status_code == 200
    assert get_res.json()["data"]["video_id"] == vid_id

    # 3. Get Timeline
    time_res = await client.get(f"/api/v1/videos/{vid_id}/timeline")
    assert time_res.status_code == 200
    assert time_res.json()["data"]["total_duration_ms"] > 0

    # 4. Generate Storyboard Endpoint
    sb_res = await client.post(
        "/api/v1/videos/storyboard",
        json={"topic": "Pipeline Hazards"},
    )
    assert sb_res.status_code == 200
    assert sb_res.json()["data"]["total_scenes"] >= 5

    # 5. Generate Script Endpoint
    script_res = await client.post(
        "/api/v1/videos/script",
        json={"topic": "Pipeline Hazards"},
    )
    assert script_res.status_code == 200
    assert script_res.json()["data"]["word_count"] > 0
