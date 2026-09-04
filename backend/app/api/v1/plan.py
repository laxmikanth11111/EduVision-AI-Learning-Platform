"""Personalised Today Plan router (P11).

Learner-scoped Today plan endpoints: the learner is resolved from the auth
context (``get_current_user``), never from the client, and the day defaults to
the current UTC date unless explicitly requested.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Body, Depends, Query

from app.core.dependencies import get_current_user
from app.database.unit_of_work import UnitOfWork, get_unit_of_work
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.plan import PlanItemCompleteResponse, TodayPlanResponse
from app.services.study_plan_service import StudyPlanService

plan_router = APIRouter(prefix="/me/plan", tags=["Personalised Plan"])


@plan_router.get(
    "/today",
    response_model=APIResponse[TodayPlanResponse],
    summary="Get the learner's deterministic Today plan",
)
async def get_today_plan(
    day: date | None = Query(default=None, description="Override the plan day (ISO date)"),
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[TodayPlanResponse]:
    service = StudyPlanService(uow)
    plan = await service.get_today(user.id, on_date=day)
    return APIResponse(data=plan, message="Today's plan")


@plan_router.post(
    "/today/items/{item_key}/complete",
    response_model=APIResponse[PlanItemCompleteResponse],
    summary="Complete a Today-plan item (review items route through P10)",
)
async def complete_today_item(
    item_key: str,
    day: date | None = Body(default=None, description="Plan day (ISO date)"),
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[PlanItemCompleteResponse]:
    service = StudyPlanService(uow)
    result = await service.complete_item(user.id, item_key, on_date=day)
    return APIResponse(data=result, message="Plan item completed")
