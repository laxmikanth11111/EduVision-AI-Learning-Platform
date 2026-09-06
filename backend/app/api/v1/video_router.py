"""API Router for Phase 4K.1 + 4K.2 AI Video Learning Engine Architecture.

Legacy ``/videos`` surface, refactored (P16) so projects are persisted as
learner-owned rows and renders are deferred to the async runtime instead of
blocking the request on FFmpeg. The response contract for ``/videos/create`` is
preserved (blueprint ``data`` with topic/timeline/storyboard/metadata/validation).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.dependencies import get_current_user
from app.database.unit_of_work import get_unit_of_work
from app.models.user import User
from app.schemas.video_engine import RenderingStatus
from app.services.animation_planner_service import animation_planner_service
from app.services.video_project_builder import build_visual_learning_model, compose_project
from app.services.video_project_service import VideoProjectService, record_to_dict
from app.services.video_script_service import video_script_service
from app.services.video_storyboard_service import video_storyboard_service

video_router = APIRouter(
    prefix="/videos", tags=["AI Video Learning Engine Architecture"]
)


class VideoCreateRequest(BaseModel):
    topic: str
    description: str | None = None
    target_audience: str = "general_learner"
    difficulty_level: str = "Intermediate"
    components: list[dict[str, Any]] = []


async def _blueprint_data(record: Any, project_data: dict[str, Any]) -> dict[str, Any]:
    data = dict(project_data)
    data.update(
        {
            "rendering_status": record.status,
            "progress_percentage": float(record.progress_percentage or 0.0),
            "playable_url": record.playable_url,
            "project_public_id": record.public_id,
        }
    )
    return data


async def _compose_and_persist(
    req: VideoCreateRequest,
    user: User,
    uow: Any,
) -> tuple[dict[str, Any], Any]:
    model = await build_visual_learning_model(
        topic=req.topic,
        description=req.description,
        components=req.components or [],
    )
    project = compose_project(
        topic=req.topic,
        model=model,
        target_audience=req.target_audience,
        difficulty_level=req.difficulty_level,
    )
    project.rendering_status = RenderingStatus.QUEUED
    project.playable_url = None
    project.progress_percentage = 0.0

    service = VideoProjectService(uow.session)
    record = await service.create(
        user_id=user.id,
        video_id=project.video_id,
        topic=req.topic,
        project_data=project.model_dump(mode="json"),
        dispatch_render=True,
    )
    return await _blueprint_data(record, project.model_dump(mode="json")), record


@video_router.post(
    "/create",
    status_code=status.HTTP_201_CREATED,
    summary="Create a complete AI Video Project from a topic description or component layout",
)
async def create_video_project(
    req: VideoCreateRequest,
    user: User = Depends(get_current_user),
    uow: Any = Depends(get_unit_of_work),
) -> dict[str, Any]:
    data, _ = await _compose_and_persist(req, user, uow)
    return {"success": True, "data": data}


@video_router.post(
    "/{video_id}/render",
    summary="Render binary MP4 video for an existing video project",
)
async def render_video_project(
    video_id: str,
    user: User = Depends(get_current_user),
    uow: Any = Depends(get_unit_of_work),
) -> dict[str, Any]:
    service = VideoProjectService(uow.session)
    record = await service.get_owned_by_video_id(user.id, video_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Video project {video_id} not found",
        )
    await service.request_render(user.id, record.public_id)
    return {"success": True, "data": record_to_dict(record)}


@video_router.post(
    "/storyboard",
    summary="Generate Educational Storyboard for a video topic",
)
async def generate_storyboard(
    req: VideoCreateRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    model = await build_visual_learning_model(
        topic=req.topic,
        description=req.description,
        components=req.components or [],
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
    model = await build_visual_learning_model(
        topic=req.topic,
        description=req.description,
        components=req.components or [],
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
    uow: Any = Depends(get_unit_of_work),
) -> dict[str, Any]:
    service = VideoProjectService(uow.session)
    record = await service.get_owned_by_video_id(user.id, video_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Video project {video_id} not found",
        )
    if not record.project_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Video project {video_id} has no stored blueprint",
        )
    return {"success": True, "data": record.project_data}


@video_router.get(
    "/{video_id}/timeline",
    summary="Retrieve Video Timeline for Video Project",
)
async def get_video_timeline(
    video_id: str,
    user: User = Depends(get_current_user),
    uow: Any = Depends(get_unit_of_work),
) -> dict[str, Any]:
    res = await get_video_project(video_id, user=user, uow=uow)
    project_data = res["data"]
    return {"success": True, "data": project_data["timeline"]}


@video_router.get(
    "/{video_id}/storyboard",
    summary="Retrieve Storyboard for Video Project",
)
async def get_video_storyboard(
    video_id: str,
    user: User = Depends(get_current_user),
    uow: Any = Depends(get_unit_of_work),
) -> dict[str, Any]:
    res = await get_video_project(video_id, user=user, uow=uow)
    project_data = res["data"]
    return {"success": True, "data": project_data["storyboard"]}


@video_router.get(
    "/{video_id}/metadata",
    summary="Retrieve Metadata for Video Project",
)
async def get_video_metadata(
    video_id: str,
    user: User = Depends(get_current_user),
    uow: Any = Depends(get_unit_of_work),
) -> dict[str, Any]:
    res = await get_video_project(video_id, user=user, uow=uow)
    project_data = res["data"]
    return {"success": True, "data": project_data["metadata"]}
