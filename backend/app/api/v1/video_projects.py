"""P16 async learner-owned video project runtime.

``/api/v1/video-projects`` — a persistent ``video_projects`` row is created
synchronously, rendering is dispatched to the inline executor or the Celery
``eduvision.videos.render_project`` task, and ownership/absence collapse to the
same 404 so rows never leak across users.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.dependencies import get_current_user
from app.database.unit_of_work import get_unit_of_work
from app.models.user import User
from app.schemas.video_projects import (
    VideoProjectCreateRequest,
    VideoProjectRenderRequest,
)
from app.services.video_project_builder import build_visual_learning_model, compose_project
from app.services.video_project_service import VideoProjectService, record_to_dict

video_projects_router = APIRouter(
    prefix="/video-projects",
    tags=["Video Projects (P16 async runtime)"],
)


@video_projects_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create a learner-owned video project and queue its render (async)",
)
async def create_video_project(
    req: VideoProjectCreateRequest,
    user: User = Depends(get_current_user),
    uow: Any = Depends(get_unit_of_work),
) -> dict[str, Any]:
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
    service = VideoProjectService(uow.session)
    record = await service.create(
        user_id=user.id,
        video_id=project.video_id,
        topic=req.topic,
        project_data=project.model_dump(mode="json"),
        dispatch_render=True,
    )
    return {"success": True, "data": record_to_dict(record)}


@video_projects_router.get(
    "",
    summary="List the calling user's video projects (newest first)",
)
async def list_video_projects(
    user: User = Depends(get_current_user),
    uow: Any = Depends(get_unit_of_work),
) -> dict[str, Any]:
    service = VideoProjectService(uow.session)
    records = await service.list_owned(user.id)
    return {
        "success": True,
        "data": [record_to_dict(r) for r in records],
        "meta": {"count": len(records)},
    }


@video_projects_router.get(
    "/{public_id}",
    summary="Retrieve a single owned video project by public id",
)
async def get_video_project(
    public_id: str,
    user: User = Depends(get_current_user),
    uow: Any = Depends(get_unit_of_work),
) -> dict[str, Any]:
    service = VideoProjectService(uow.session)
    record = await service.get_owned(user.id, public_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video project not found",
        )
    return {"success": True, "data": record_to_dict(record)}


@video_projects_router.post(
    "/{public_id}/render",
    summary="Queue an explicit render for an owned video project",
)
async def request_render(
    public_id: str,
    req: VideoProjectRenderRequest | None = None,
    user: User = Depends(get_current_user),
    uow: Any = Depends(get_unit_of_work),
) -> dict[str, Any]:
    service = VideoProjectService(uow.session)
    record = await service.request_render(
        user.id,
        public_id,
        force=bool(req and req.force),
    )
    return {"success": True, "data": record_to_dict(record)}
