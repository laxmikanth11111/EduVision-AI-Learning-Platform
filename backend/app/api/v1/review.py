"""Adaptive Review Engine router (P10).

Learner-scoped review scheduling endpoints. The learner is resolved from the
auth context (``get_current_user``), never from the client, and every schedule
is resolved against the owning user with ownership 404-equalized.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import get_current_user
from app.database.unit_of_work import UnitOfWork, get_unit_of_work
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.review import ReviewCompleteResponse, ReviewQueueResponse
from app.services.review_schedule_service import ReviewScheduleService

review_router = APIRouter(prefix="/me/review", tags=["Adaptive Review"])

_MAX_LIMIT = 100


@review_router.get(
    "",
    response_model=APIResponse[ReviewQueueResponse],
    summary="Get the learner's bounded review queue",
)
async def get_review_queue(
    limit: int = Query(default=10, ge=1, le=_MAX_LIMIT),
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[ReviewQueueResponse]:
    service = ReviewScheduleService(uow)
    queue = await service.list_due(user.id, limit=limit)
    return APIResponse(data=queue, message="Review queue")


@review_router.post(
    "/{schedule_id}/complete",
    response_model=APIResponse[ReviewCompleteResponse],
    summary="Mark a review item complete and advance its interval",
)
async def complete_review(
    schedule_id: str,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[ReviewCompleteResponse]:
    service = ReviewScheduleService(uow)
    result = await service.complete(user.id, schedule_id)
    return APIResponse(data=result, message="Review completed")


@review_router.post(
    "/{schedule_id}/skip",
    response_model=APIResponse[ReviewCompleteResponse],
    summary="Postpone a due review item",
)
async def skip_review(
    schedule_id: str,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[ReviewCompleteResponse]:
    service = ReviewScheduleService(uow)
    result = await service.skip(user.id, schedule_id)
    return APIResponse(data=result, message="Review skipped")
