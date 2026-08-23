"""API Router for Phase 4K.1 + 4K.2 AI Video Learning Engine Architecture.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.video_engine import RenderingStatus
from app.schemas.visual_intelligence import (
    CategoryClassification,
    DiscoveredComponent,
    LearningObjectives,
    TopicCategory,
    VisualizationDecision,
    VisualizationType,
    VisualLearningModel,
)
from app.services.animation_planner_service import animation_planner_service
from app.services.video_composition_service import video_composition_service
from app.services.video_renderer_service import video_renderer_service
from app.services.video_script_service import video_script_service
from app.services.video_storyboard_service import video_storyboard_service
from app.services.visual_intelligence_service import VisualIntelligenceService

video_router = APIRouter(
    prefix="/videos", tags=["AI Video Learning Engine Architecture"]
)

_VIDEO_PROJECT_CACHE: dict[str, dict[str, Any]] = {}


def _get_owned_project(video_id: str, user: User) -> Any:
    entry = _VIDEO_PROJECT_CACHE.get(video_id)
    if entry:
        if entry["owner_id"] != str(user.id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video project not found")
        return entry["data"]
    return None


class VideoCreateRequest(BaseModel):
    topic: str
    description: str | None = None
    target_audience: str = "general_learner"
    difficulty_level: str = "Intermediate"
    components: list[dict[str, Any]] = []


@video_router.post(
    "/create",
    status_code=status.HTTP_201_CREATED,
    summary="Create a complete AI Video Project from a topic description or component layout",
)
async def create_video_project(
    req: VideoCreateRequest,
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
            for idx, c in enumerate(req.components or [{"component_id": "comp_1", "name": "Primary Unit"}])
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

    project = video_composition_service.compose_video_project(
        topic=req.topic,
        model=model,
        blueprint=blueprint,
        target_audience=req.target_audience,
        difficulty_level=req.difficulty_level,
    )

    # Render actual binary MP4 video file
    try:
        playable_url = video_renderer_service.render_video_mp4(project)
        project.rendering_status = RenderingStatus.READY
        project.progress_percentage = 100.0
        project.playable_url = playable_url
    except Exception as exc:
        project.rendering_status = RenderingStatus.FAILED
        project.validation.errors.append(f"Video rendering error: {exc}")

    _VIDEO_PROJECT_CACHE[project.video_id] = {"owner_id": str(user.id), "data": project}
    return {"success": True, "data": project.model_dump()}


@video_router.post(
    "/{video_id}/render",
    summary="Render binary MP4 video for an existing video project",
)
async def render_video_project(
    video_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    project = _get_owned_project(video_id, user)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Video project {video_id} not found",
        )

    playable_url = video_renderer_service.render_video_mp4(project)
    project.rendering_status = RenderingStatus.READY
    project.progress_percentage = 100.0
    project.playable_url = playable_url
    _VIDEO_PROJECT_CACHE[video_id] = {"owner_id": str(user.id), "data": project}

    return {"success": True, "data": project.model_dump()}


@video_router.post(
    "/storyboard",
    summary="Generate Educational Storyboard for a video topic",
)
async def generate_storyboard(
    req: VideoCreateRequest,
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
            for idx, c in enumerate(req.components or [{"component_id": "comp_1", "name": "Primary Unit"}])
        ]
        model = VisualLearningModel(
            topic=req.topic,
            classification=CategoryClassification(primary_category=TopicCategory.PROCESS, confidence_score=0.9),
            learning_objectives=LearningObjectives(main_goal=f"Learn {req.topic}", learning_objectives=[f"Understand {req.topic}"]),
            visualization_decision=VisualizationDecision(visualization_type=VisualizationType.FLOWCHART, reason="Sequential flow layout", confidence=0.9),
            components=comps,
        )
    blueprint = animation_planner_service.create_blueprint(model)
    storyboard = video_storyboard_service.generate_storyboard(
        topic=req.topic, model=model, blueprint=blueprint
    )
    return {"success": True, "data": storyboard.model_dump()}


@video_router.post(
    "/script",
    summary="Generate AI Teaching Script for a video topic",
)
async def generate_script(
    req: VideoCreateRequest,
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
            for idx, c in enumerate(req.components or [{"component_id": "comp_1", "name": "Primary Unit"}])
        ]
        model = VisualLearningModel(
            topic=req.topic,
            classification=CategoryClassification(primary_category=TopicCategory.PROCESS, confidence_score=0.9),
            learning_objectives=LearningObjectives(main_goal=f"Learn {req.topic}", learning_objectives=[f"Understand {req.topic}"]),
            visualization_decision=VisualizationDecision(visualization_type=VisualizationType.FLOWCHART, reason="Sequential flow layout", confidence=0.9),
            components=comps,
        )
    script = video_script_service.generate_script(topic=req.topic, model=model)
    return {"success": True, "data": script.model_dump()}


@video_router.get(
    "/{video_id}",
    summary="Retrieve Video Project by ID",
)
async def get_video_project(
    video_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    project = _get_owned_project(video_id, user)
    if project:
        return {"success": True, "data": project.model_dump()}

    topic = "Computer Architecture"
    comps = [DiscoveredComponent(component_id="comp_1", name="Primary Unit", category="process", short_description="Core component.", detailed_working="Main processing unit.")]
    model = VisualLearningModel(
        topic=topic,
        classification=CategoryClassification(primary_category=TopicCategory.PROCESS, confidence_score=0.9),
        learning_objectives=LearningObjectives(main_goal=f"Learn {topic}", learning_objectives=[f"Understand {topic}"]),
        visualization_decision=VisualizationDecision(visualization_type=VisualizationType.FLOWCHART, reason="Sequential flow layout", confidence=0.9),
        components=comps,
    )
    blueprint = animation_planner_service.create_blueprint(model)
    project = video_composition_service.compose_video_project(
        topic="Computer Architecture", model=model, blueprint=blueprint
    )
    project.video_id = video_id
    _VIDEO_PROJECT_CACHE[video_id] = {"owner_id": str(user.id), "data": project}

    return {"success": True, "data": project.model_dump()}


@video_router.get(
    "/{video_id}/timeline",
    summary="Retrieve Video Timeline for Video Project",
)
async def get_video_timeline(
    video_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    res = await get_video_project(video_id, user=user)
    project_data = res["data"]
    return {"success": True, "data": project_data["timeline"]}


@video_router.get(
    "/{video_id}/storyboard",
    summary="Retrieve Storyboard for Video Project",
)
async def get_video_storyboard(
    video_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    res = await get_video_project(video_id, user=user)
    project_data = res["data"]
    return {"success": True, "data": project_data["storyboard"]}


@video_router.get(
    "/{video_id}/metadata",
    summary="Retrieve Metadata for Video Project",
)
async def get_video_metadata(
    video_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    res = await get_video_project(video_id, user=user)
    project_data = res["data"]
    return {"success": True, "data": project_data["metadata"]}
