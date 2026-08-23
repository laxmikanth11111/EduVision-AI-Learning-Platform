"""Prometheus-format metrics endpoint.

Exposes the in-process counter/gauge registry as text/plain (Prometheus
exposition format) so an external scraper can aggregate it. The registry is
deliberately dependency-free; see ``app.observability.metrics``.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from app.observability.metrics import init_default_metrics, render_metrics

metrics_router = APIRouter(tags=["Metrics"])

init_default_metrics()


@metrics_router.get(
    "/metrics",
    response_class=PlainTextResponse,
    summary="Prometheus text-format metrics",
    include_in_schema=False,
)
async def get_metrics() -> PlainTextResponse:
    return PlainTextResponse(content=render_metrics())
