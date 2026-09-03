"""Learner Progress Dashboard router.

Exposes the authenticated learner's own progress view. Read-only and
learner-scoped: the user is resolved from the auth context (``get_current_user``),
never from the client, so no other learner's data can be requested.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.dependencies import get_current_user
from app.database.unit_of_work import UnitOfWork, get_unit_of_work
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.learner_progress import LearnerProgressResponse
from app.services.learner_progress_service import LearnerProgressService

learner_progress_router = APIRouter(prefix="/me/progress", tags=["Learner Progress"])


@learner_progress_router.get(
    "",
    response_model=APIResponse[LearnerProgressResponse],
    summary="Get the current learner's progress dashboard",
)
async def get_learner_progress(
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[LearnerProgressResponse]:
    service = LearnerProgressService(uow)
    progress = await service.get_progress(user.id)
    return APIResponse(data=progress, message="Learner progress")
