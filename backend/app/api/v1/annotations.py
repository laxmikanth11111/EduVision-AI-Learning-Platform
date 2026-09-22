"""Per-slide annotation layer endpoints (teaching continuity).

All routes are lesson-owner-scoped: the shared lesson ownership helper (also
used by every player route) is invoked first so a non-owner gets 403 without
any information leak, then layer reads are further filtered by the
authenticated user id.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.core.dependencies import get_current_user
from app.database.unit_of_work import UnitOfWork, get_unit_of_work
from app.models.user import User
from app.schemas.annotations import (
    AnnotationListResponse,
    AnnotationSaveResponse,
)
from app.schemas.common import APIResponse
from app.services.lesson_player_service import LessonPlayerService
from app.services.presentation_annotation_service import (
    PresentationAnnotationService,
    parse_annotations,
)
from shared.constants import AnnotationLayerMode

annotations_router = APIRouter(
    prefix="/lessons/{lesson_id}/annotations", tags=["Lesson Annotations"]
)


class SaveAnnotationLayerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[dict[str, Any]] = Field(default_factory=list)


async def _owned_lesson(lesson_id: str, user_id: str, uow: UnitOfWork):
    """Load a lesson, asserting the caller owns its presentation."""
    try:
        return await LessonPlayerService(uow)._assert_lesson_ownership(lesson_id, user_id)
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@annotations_router.get(
    "",
    response_model=APIResponse[AnnotationListResponse],
)
async def list_annotations(
    lesson_id: str,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[AnnotationListResponse]:
    lesson = await _owned_lesson(lesson_id, str(user.id), uow)
    layers = await PresentationAnnotationService(uow).list_for_lesson(
        user_id=str(user.id),
        lesson_id=lesson.id,
    )
    return APIResponse(data=AnnotationListResponse(layers=layers))


@annotations_router.put(
    "/{player_mode}/{slide_index}",
    response_model=APIResponse[AnnotationSaveResponse],
)
async def save_annotation_layer(
    lesson_id: str,
    player_mode: str,
    slide_index: int,
    request: SaveAnnotationLayerRequest,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[AnnotationSaveResponse]:
    if player_mode not in AnnotationLayerMode.as_set():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"invalid annotation layer mode: {player_mode!r}",
        )
    if slide_index < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="slide_index must be >= 0",
        )
    try:
        items = parse_annotations(request.items)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    lesson = await _owned_lesson(lesson_id, str(user.id), uow)
    saved = await PresentationAnnotationService(uow).replace(
        user_id=str(user.id),
        lesson_id=lesson.id,
        player_mode=player_mode,
        slide_index=slide_index,
        items=items,
    )
    return APIResponse(
        data=AnnotationSaveResponse(
            player_mode=saved["player_mode"],
            slide_index=saved["slide_index"],
            item_count=saved["item_count"],
        ),
        message="Annotation layer saved",
    )
