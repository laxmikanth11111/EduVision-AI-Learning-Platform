"""Interactive lesson player endpoints.

Returns the full read-only player payload; POST start creates/resumes
an active session. Simplified: tracks which topic index the user is on,
no quiz sessions, no bookmarks, no notes.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.dependencies import get_current_user
from app.database.unit_of_work import UnitOfWork, get_unit_of_work
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.player import (
    PlayerSessionResponse,
    PlayerStateResponse,
    SetPositionRequest,
    StartPlayerRequest,
)
from app.services.lesson_player_service import LessonPlayerService

player_router = APIRouter(prefix="/lessons/{lesson_id}/player", tags=["Lesson Player"])


@player_router.get(
    "",
    response_model=APIResponse[PlayerStateResponse],
)
async def get_player_state(
    lesson_id: str,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[PlayerStateResponse]:
    try:
        result = await LessonPlayerService(uow).get_state(lesson_id, owner_id=str(user.id))
    except (PermissionError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lesson {lesson_id} not found",
        )
    return APIResponse(data=PlayerStateResponse(**result))


@player_router.post(
    "/start",
    response_model=APIResponse[PlayerStateResponse],
)
async def start_player_session(
    lesson_id: str,
    request: StartPlayerRequest,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[PlayerStateResponse]:
    try:
        result = await LessonPlayerService(uow).start(
            lesson_id,
            owner_id=str(user.id),
            device_id=request.device_id,
            client_metadata=request.client_metadata,
            player_mode=request.player_mode,
        )
    except (PermissionError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lesson {lesson_id} not found",
        )
    return APIResponse(data=PlayerStateResponse(**result), message="Session started")


class AdvanceTopicRequest(BaseModel):
    session_id: str


@player_router.post(
    "/advance",
    response_model=APIResponse[PlayerSessionResponse],
)
async def advance_topic(
    lesson_id: str,
    request: AdvanceTopicRequest,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[PlayerSessionResponse]:
    service = LessonPlayerService(uow)
    try:
        state = await service.advance_topic(request.session_id, owner_id=str(user.id))
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    return APIResponse(data=PlayerSessionResponse(**state), message="Topic advanced")


class SetTopicRequest(BaseModel):
    session_id: str
    topic_index: int


@player_router.post(
    "/set-topic",
    response_model=APIResponse[PlayerSessionResponse],
)
async def set_topic(
    lesson_id: str,
    request: SetTopicRequest,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[PlayerSessionResponse]:
    service = LessonPlayerService(uow)
    try:
        state = await service.set_topic(request.session_id, request.topic_index, owner_id=str(user.id))
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    return APIResponse(data=PlayerSessionResponse(**state), message="Topic set")


@player_router.post(
    "/position",
    response_model=APIResponse[PlayerSessionResponse],
)
async def set_slide_position(
    lesson_id: str,
    request: SetPositionRequest,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[PlayerSessionResponse]:
    """Persist the learner's exact slide position for slide-accurate resume."""
    state = await LessonPlayerService(uow).set_position(
        request.session_id,
        request.slide_index,
        owner_id=str(user.id),
        player_mode=request.mode,
    )
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {request.session_id} not found",
        )
    return APIResponse(data=PlayerSessionResponse(**state), message="Position saved")


@player_router.get(
    "/checkpoint",
    response_model=APIResponse[dict[str, Any]],
)
async def get_checkpoint(
    lesson_id: str,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[dict[str, Any]]:
    """Return the assessment checkpoint bound to a lesson, if any."""
    try:
        result = await LessonPlayerService(uow).get_checkpoint(lesson_id, owner_id=str(user.id))
    except (PermissionError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lesson {lesson_id} not found",
        )
    return APIResponse(data=result)


@player_router.get(
    "/mastery",
    response_model=APIResponse[dict[str, Any]],
)
async def get_mastery_and_next_action(
    lesson_id: str,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[dict[str, Any]]:
    """Return the learner's mastery and a deterministic next learning action."""
    try:
        result = await LessonPlayerService(uow).get_mastery_and_next_action(
            lesson_id, owner_id=str(user.id)
        )
    except (PermissionError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lesson {lesson_id} not found",
        )
    return APIResponse(data=result)
