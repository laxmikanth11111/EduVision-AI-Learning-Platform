from __future__ import annotations

import re

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from app.core.config import settings
from app.core.error_codes import ErrorCode
from app.core.logging import get_logger

logger = get_logger(__name__)


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: ASGIApp,
        default_max_bytes: int | None = None,
        endpoint_overrides: dict[str, int] | None = None,
    ) -> None:
        super().__init__(app)
        self._default_max_bytes = default_max_bytes or settings.REQUEST_SIZE_LIMIT_DEFAULT
        self._endpoint_overrides: dict[re.Pattern[str], int] = {}
        if endpoint_overrides:
            for pattern, limit in endpoint_overrides.items():
                self._endpoint_overrides[re.compile(pattern)] = limit

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        if not settings.REQUEST_SIZE_LIMIT_ENABLED:
            return await call_next(request)

        max_bytes = self._resolve_max_bytes(request)
        request_id = getattr(request.state, "request_id", None)

        content_length_str = request.headers.get("content-length")
        if content_length_str is not None:
            try:
                content_length = int(content_length_str)
                if content_length < 0:
                    raise ValueError("Content-Length cannot be negative")
            except (ValueError, TypeError):
                logger.warning(
                    "request_size_limit_invalid_content_length",
                    path=str(request.url.path),
                    method=request.method,
                    content_length=content_length_str,
                )
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "error": {
                            "code": "INVALID_HEADER",
                            "message": "Invalid Content-Length header",
                            "details": {"content_length": content_length_str},
                            "request_id": request_id,
                        },
                    },
                )

            if content_length > max_bytes:
                logger.warning(
                    "request_size_limit_exceeded",
                    path=str(request.url.path),
                    method=request.method,
                    content_length=content_length,
                    max_bytes=max_bytes,
                    client_host=request.client.host if request.client else "unknown",
                )
                return JSONResponse(
                    status_code=413,
                    content={
                        "success": False,
                        "error": {
                            "code": ErrorCode.REQUEST_TOO_LARGE.value,
                            "message": f"Request body too large. Maximum allowed: {self._format_bytes(max_bytes)}",
                            "details": {
                                "content_length": content_length,
                                "max_allowed": max_bytes,
                            },
                            "request_id": request_id,
                        },
                    },
                    headers={"X-Request-Max-Size": str(max_bytes)},
                )

        request.state.request_max_bytes = max_bytes
        return await call_next(request)

    def _resolve_max_bytes(self, request: Request) -> int:
        path = str(request.url.path)
        for pattern, limit in self._endpoint_overrides.items():
            if pattern.search(path):
                return limit
        return self._default_max_bytes

    @staticmethod
    def _format_bytes(size: int) -> str:
        value: float = size
        for unit in ("B", "KB", "MB", "GB"):
            if value < 1024:
                return f"{value:.1f} {unit}"
            value /= 1024
        return f"{value:.1f} TB"
