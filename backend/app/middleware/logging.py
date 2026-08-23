from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.logging import get_logger
from app.observability.metrics import metrics

logger = get_logger(__name__)

SLOW_REQUEST_MS = 1000


def _get_route_path(request: Request) -> str:
    """Return the route template path (e.g. /api/v1/presentations/{id}) to keep
    label cardinality bounded. Falls back to the raw URL path when routing info
    is not yet available (e.g. before middleware completes)."""
    route = request.scope.get("route")
    if route is not None:
        return getattr(route, "path", request.url.path)
    return request.url.path


class LoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        start = time.monotonic()
        response = await call_next(request)
        elapsed = time.monotonic() - start
        duration_ms = round(elapsed * 1000, 2)

        route_path = _get_route_path(request)

        log_data = {
            "method": request.method,
            "path": request.url.path,
            "route": route_path,
            "query": str(request.url.query) if request.url.query else None,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            "request_id": getattr(request.state, "request_id", None),
            "client_host": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent"),
        }

        metrics.increment(
            "http_requests_total",
            method=request.method,
            path=route_path,
            status=str(response.status_code),
        )
        metrics.increment("http_requests_duration_seconds_sum", value=elapsed)
        metrics.increment("http_requests_duration_seconds_count")

        if response.status_code >= 500:
            logger.error("request_failed", **log_data)
        elif duration_ms > SLOW_REQUEST_MS:
            logger.warning("request_slow", **log_data)
        else:
            logger.info("request_completed", **log_data)

        return response
