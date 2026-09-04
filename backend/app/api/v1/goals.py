"""Measurable learning-goals router (P11).

Learner-scoped goal endpoints. Progress is always derived server-side from
live state; ``GoalProgressRequest`` is deliberately NOT exposed here so the
client can never author its own ``current_value``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import get_current_user
from app.database.unit_of_work import UnitOfWork, get_unit_of_work
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.personalization import GoalCreateRequest
from app.schemas.plan import (
    GoalCompleteResponse,
    GoalCreateResponse,
    GoalsResponse,
)
from app.services.learning_goal_service import LearningGoalService

goals_router = APIRouter(prefix="/me/goals", tags=["Learning Goals"])


@goals_router.get(
    "",
    response_model=APIResponse[GoalsResponse],
    summary="List the learner's goals with derived progress",
)
async def list_goals(
    status: str | None = Query(default=None, description="Filter by goal status"),
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[GoalsResponse]:
    service = LearningGoalService(uow)
    goals = await service.list_goals(user.id, status=status)
    return APIResponse(data=GoalsResponse(goals=goals), message="Learning goals")


@goals_router.post(
    "",
    response_model=APIResponse[GoalCreateResponse],
    summary="Create a learner goal (progress is server-derived)",
)
async def create_goal(
    body: GoalCreateRequest,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[GoalCreateResponse]:
    service = LearningGoalService(uow)
    goal = await service.create_goal(
        user.id,
        goal_type=body.goal_type.value if hasattr(body.goal_type, "value") else str(body.goal_type),
        title=body.title,
        description=body.description,
        target_value=body.target_value,
        unit=body.unit,
        target_date=body.target_date,
        path_id=body.path_id,
    )
    return APIResponse(data=GoalCreateResponse(goal=goal), message="Goal created")


@goals_router.get(
    "/{goal_id}",
    response_model=APIResponse[GoalCreateResponse],
    summary="Get a single goal with derived progress",
)
async def get_goal(
    goal_id: str,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[GoalCreateResponse]:
    service = LearningGoalService(uow)
    goal = await service.get_goal(user.id, goal_id)
    return APIResponse(data=GoalCreateResponse(goal=goal), message="Learning goal")


@goals_router.post(
    "/{goal_id}/complete",
    response_model=APIResponse[GoalCompleteResponse],
    summary="Mark a goal achieved (only succeeds when the target is met)",
)
async def complete_goal(
    goal_id: str,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[GoalCompleteResponse]:
    service = LearningGoalService(uow)
    result = await service.complete_goal(user.id, goal_id)
    return APIResponse(data=result, message="Goal completed")
