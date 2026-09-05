"""Learner Analytics router (P13) — "Know my trajectory".

Exposes the authenticated learner's own deterministic analytics under
``/me/analytics/*``. Read-only and learner-scoped: the user identity comes
exclusively from ``get_current_user``, never from the client, so no other
learner's rows can be requested or leaked. Each endpoint returns the
``APIResponse[T]`` envelope and increments the ``p13_analytics_*`` counters.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import get_current_user
from app.database.unit_of_work import UnitOfWork, get_unit_of_work
from app.models.user import User
from app.observability.metrics import metrics
from app.schemas.common import APIResponse
from app.schemas.learner_analytics import (
    AnalyticsOverview,
    ConceptsResponse,
    EffortResponse,
    TrendResponse,
)
from app.services.learner_analytics_service import LearnerAnalyticsService

analytics_router = APIRouter(prefix="/me/analytics", tags=["Learner Analytics"])


async def _build(
    endpoint: str,
    uow: UnitOfWork,
    user_id: Any,
    builder: Any,
) -> Any:
    """Run an analytics read, tracking p13 views/errors without learner PII."""
    try:
        payload = await builder(LearnerAnalyticsService(uow), user_id)
    except Exception:
        metrics.increment(
            "p13_analytics_errors_total",
            endpoint=endpoint,
            reason="build_failed",
        )
        raise
    metrics.increment("p13_analytics_views_total", endpoint=endpoint, outcome="ok")
    return payload


@analytics_router.get(
    "",
    response_model=APIResponse[AnalyticsOverview],
    summary="Get the learner's analytics overview (trajectory summary)",
)
@analytics_router.get(
    "/overview",
    response_model=APIResponse[AnalyticsOverview],
    include_in_schema=False,
)
async def get_analytics_overview(
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[AnalyticsOverview]:
    overview = await _build("overview", uow, user.id, lambda svc, uid: svc.get_overview(uid))
    return APIResponse(data=overview, message="Learner analytics overview")


@analytics_router.get(
    "/trend",
    response_model=APIResponse[TrendResponse],
    summary="Get the learner's accuracy trajectory (bounded window)",
)
async def get_analytics_trend(
    window: int | None = Query(default=None, ge=1, le=30),
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[TrendResponse]:
    trend = await _build(
        "trend", uow, user.id, lambda svc, uid: svc.get_trend(uid, window)
    )
    return APIResponse(data=trend, message="Learner accuracy trajectory")


@analytics_router.get(
    "/concepts",
    response_model=APIResponse[ConceptsResponse],
    summary="Get per-concept mastery trajectory (up/flat/down with deep-links)",
)
async def get_analytics_concepts(
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[ConceptsResponse]:
    concepts = await _build("concepts", uow, user.id, lambda svc, uid: svc.get_concepts(uid))
    return APIResponse(data=concepts, message="Concept mastery trajectories")


@analytics_router.get(
    "/effort",
    response_model=APIResponse[EffortResponse],
    summary="Get effort vs mastery gained per concept",
)
async def get_analytics_effort(
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[EffortResponse]:
    effort = await _build("effort", uow, user.id, lambda svc, uid: svc.get_effort(uid))
    return APIResponse(data=effort, message="Effort vs mastery")
