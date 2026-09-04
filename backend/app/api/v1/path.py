"""Personalised learning-path router (P11).

Learner-scoped learning-path endpoints. ``GET`` auto-creates/reconciles the
single active path from live learner state; ``POST`` creates a new active path
(archiving the prior one). Ordering is deterministic — never AI-ranked.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.dependencies import get_current_user
from app.database.unit_of_work import UnitOfWork, get_unit_of_work
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.personalization import LearningPathCreateRequest
from app.schemas.plan import LearningPathCreateResponse, LearningPathView
from app.services.learning_path_service import LearningPathService

path_router = APIRouter(prefix="/me/path", tags=["Learning Path"])


@path_router.get(
    "",
    response_model=APIResponse[LearningPathView],
    summary="Get the learner's active learning path (auto-created)",
)
async def get_learning_path(
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[LearningPathView]:
    service = LearningPathService(uow)
    view = await service.get_path(user.id)
    return APIResponse(data=view, message="Learning path")


@path_router.post(
    "",
    response_model=APIResponse[LearningPathCreateResponse],
    summary="Create a new active learning path (archives the prior one)",
)
async def create_learning_path(
    body: LearningPathCreateRequest,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[LearningPathCreateResponse]:
    service = LearningPathService(uow)
    view = await service.create_path(user.id, title=body.title, description=body.description)
    return APIResponse(
        data=LearningPathCreateResponse(path=view),
        message="Learning path created",
    )
