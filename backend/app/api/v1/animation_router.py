"""API Router for Phase 4J.1 + 4J.2 AI Animation Engine.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.dependencies import get_current_user
from app.models.user import User
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
from app.services.visual_intelligence_service import VisualIntelligenceService

animation_router = APIRouter(
    prefix="/animations", tags=["AI Animation Engine Architecture & Planner"]
)

_BLUEPRINT_CACHE: dict[str, dict[str, Any]] = {}


def _assert_blueprint_owner(blueprint_id: str, user: User) -> None:
    entry = _BLUEPRINT_CACHE.get(blueprint_id)
    if entry and entry["owner_id"] != str(user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blueprint not found")


class AnimationPlanRequest(BaseModel):
    topic: str
    description: str | None = None
    layout_category: str = "flowchart"
    components: list[dict[str, Any]] = []


@animation_router.post(
    "/plan",
    status_code=status.HTTP_201_CREATED,
    summary="Generate a structured Animation Blueprint from a topic description or component layout",
)
async def plan_animation_blueprint(
    req: AnimationPlanRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    if req.description:
        intel_service = VisualIntelligenceService()
        model = await intel_service.generate_visual_learning_model(req.description, title=req.topic)
    else:
        comps = [
            DiscoveredComponent(
                component_id=c.get("component_id", f"comp_{idx}"),
                name=c.get("name", f"Component {idx}"),
                category=c.get("category", "process"),
                short_description=c.get("short_description", "Visual node element."),
                detailed_working=c.get("detailed_working", "Executes signal processing."),
            )
            for idx, c in enumerate(req.components or [{"component_id": "comp_1", "name": "Start Node"}])
        ]
        model = VisualLearningModel(
            topic=req.topic,
            classification=CategoryClassification(
                primary_category=TopicCategory.PROCESS,
                confidence_score=0.9,
            ),
            learning_objectives=LearningObjectives(
                main_goal=f"Learn {req.topic}",
                learning_objectives=[f"Understand {req.topic}"],
            ),
            visualization_decision=VisualizationDecision(
                visualization_type=VisualizationType.FLOWCHART,
                reason="Sequential flow layout",
                confidence=0.9,
            ),
            components=comps,
        )

    blueprint = animation_planner_service.create_blueprint(model)
    _BLUEPRINT_CACHE[blueprint.blueprint_id] = {"owner_id": str(user.id), "data": blueprint}
    return {"success": True, "data": blueprint.model_dump()}


@animation_router.post(
    "/classify",
    summary="Classify animation strategy for layout category",
)
async def classify_animation_layout(
    layout_category: str = "flowchart",
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    classification = animation_classification_service.classify_layout(layout_category)
    return {"success": True, "data": classification.model_dump()}


@animation_router.get(
    "/{blueprint_id}",
    summary="Retrieve animation blueprint by ID",
)
async def get_animation_blueprint(
    blueprint_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    entry = _BLUEPRINT_CACHE.get(blueprint_id)
    if entry:
        if entry["owner_id"] != str(user.id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blueprint not found")
        return {"success": True, "data": entry["data"].model_dump()}

    model = VisualLearningModel(
        topic="Visual Learning Architecture",
        classification=CategoryClassification(
            primary_category=TopicCategory.PROCESS, confidence_score=0.9,
        ),
        learning_objectives=LearningObjectives(
            main_goal="Learn Visual Learning Architecture",
            learning_objectives=["Understand Visual Learning Architecture"],
        ),
        visualization_decision=VisualizationDecision(
            visualization_type=VisualizationType.FLOWCHART,
            reason="Sequential flow layout", confidence=0.9,
        ),
        components=[
            DiscoveredComponent(
                component_id="comp_cpu", name="CPU Execution Engine",
                short_description="Central processing unit", detailed_working="Executes instructions",
            ),
            DiscoveredComponent(
                component_id="comp_ram", name="RAM Main Memory",
                short_description="Main random access memory", detailed_working="Stores data and variables",
            ),
        ],
    )
    bp = animation_planner_service.create_blueprint(model)
    bp.blueprint_id = blueprint_id
    _BLUEPRINT_CACHE[blueprint_id] = {"owner_id": str(user.id), "data": bp}
    return {"success": True, "data": bp.model_dump()}


@animation_router.get(
    "/{blueprint_id}/scenes",
    summary="Retrieve scenes list for animation blueprint",
)
async def get_animation_scenes(
    blueprint_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    res = await get_animation_blueprint(blueprint_id, user=user)
    return {"success": True, "data": res["data"]["timeline"]["scenes"]}


@animation_router.get(
    "/{blueprint_id}/timeline",
    summary="Retrieve timeline engine timeline metadata for blueprint",
)
async def get_animation_timeline(
    blueprint_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    res = await get_animation_blueprint(blueprint_id, user=user)
    return {"success": True, "data": res["data"]["timeline"]}


@animation_router.get(
    "/{blueprint_id}/blueprint",
    summary="Export full animation blueprint JSON",
)
async def export_animation_blueprint(
    blueprint_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return await get_animation_blueprint(blueprint_id, user=user)


@animation_router.get(
    "/{blueprint_id}/metadata",
    summary="Retrieve blueprint metadata, validation status, and duration estimates",
)
async def get_animation_metadata(
    blueprint_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    res = await get_animation_blueprint(blueprint_id, user=user)
    bp_data = res["data"]
    return {
        "success": True,
        "data": {
            "blueprint_id": bp_data["blueprint_id"],
            "topic": bp_data["topic"],
            "total_duration_ms": bp_data["timeline"]["total_duration_ms"],
            "scenes_count": len(bp_data["timeline"]["scenes"]),
            "total_events": bp_data["timeline"]["total_events"],
            "validation": bp_data["validation"],
        },
    }
