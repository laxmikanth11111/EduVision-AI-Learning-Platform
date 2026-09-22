from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR

from app.core.error_codes import ErrorCode
from app.core.exceptions import EduVisionError
from app.core.logging import get_logger

logger = get_logger(__name__)

SENSITIVE_HEADERS = {"authorization", "cookie", "x-api-key", "proxy-authorization"}


def setup_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(EduVisionError)
    async def eduvision_exception_handler(request: Request, exc: EduVisionError) -> JSONResponse:
        return _build_error_response(
            request=request,
            status_code=exc.status_code,
            code=exc.code.value,
            message=exc.message,
            details=exc.details,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        field_errors = []
        for error in exc.errors():
            field_errors.append(
                {
                    "field": " -> ".join(str(loc) for loc in error.get("loc", [])),
                    "message": error.get("msg", ""),
                    "type": error.get("type", ""),
                }
            )
        return _build_error_response(
            request=request,
            status_code=422,
            code=ErrorCode.VALIDATION_ERROR.value,
            message="Request validation failed",
            details={"errors": field_errors},
        )

    @app.exception_handler(PydanticValidationError)
    async def pydantic_validation_handler(request: Request, exc: PydanticValidationError) -> JSONResponse:
        return _build_error_response(
            request=request,
            status_code=422,
            code=ErrorCode.VALIDATION_ERROR.value,
            message="Data validation failed",
            details={"errors": exc.errors(include_input=False)},
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return _build_http_error_response(request, exc)

    @app.exception_handler(StarletteHTTPException)
    async def starlette_http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        return _build_http_error_response(request, exc)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        logger.error(
            "unhandled_exception",
            error=str(exc),
            error_type=type(exc).__name__,
            path=str(request.url.path),
            method=request.method,
            request_id=request_id,
        )
        return _build_error_response(
            request=request,
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            code=ErrorCode.INTERNAL_ERROR.value,
            message="An unexpected error occurred",
        )


def _build_http_error_response(
    request: Request,
    exc: HTTPException | StarletteHTTPException,
) -> JSONResponse:
    code_map = {
        400: ErrorCode.BAD_REQUEST,
        401: ErrorCode.UNAUTHORIZED,
        403: ErrorCode.FORBIDDEN,
        404: ErrorCode.NOT_FOUND,
        405: ErrorCode.METHOD_NOT_ALLOWED,
        409: ErrorCode.CONFLICT,
        413: ErrorCode.REQUEST_TOO_LARGE,
        415: ErrorCode.UNSUPPORTED_MEDIA_TYPE,
        422: ErrorCode.VALIDATION_ERROR,
        429: ErrorCode.RATE_LIMITED,
        500: ErrorCode.INTERNAL_ERROR,
        503: ErrorCode.SERVICE_UNAVAILABLE,
    }
    code = code_map.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
    headers = getattr(exc, "headers", None)
    return _build_error_response(
        request=request,
        status_code=exc.status_code,
        code=code.value,
        message=str(exc.detail),
        headers=headers,
    )


def _build_error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
                "request_id": request_id,
            },
        },
        headers=headers,
    )


class ExceptionLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        try:
            return await call_next(request)
        except Exception as exc:
            if not isinstance(exc, EduVisionError):
                logger.error(
                    "unhandled_middleware_exception",
                    error=str(exc),
                    error_type=type(exc).__name__,
                    path=str(request.url.path),
                    method=request.method,
                    request_id=getattr(request.state, "request_id", None),
                    client_host=request.client.host if request.client else None,
                )
            raise
