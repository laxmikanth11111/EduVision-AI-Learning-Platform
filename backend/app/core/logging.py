from __future__ import annotations

import logging
import re
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog

from app.core.config import settings

SENSITIVE_FIELDS = {
    "password",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "api_key_id",
    "secret_key",
    "auth",
    "authorization",
    "cookie",
    "jwt",
    "credential",
    "credit_card",
    "ssn",
    "pin",
    "cvv",
}

SENSITIVE_PATTERN = re.compile(
    "|".join(f"(?P<{f}>{f})" for f in SENSITIVE_FIELDS),
    re.IGNORECASE,
)


def _mask_sensitive_fields(
    logger: logging.Logger,
    method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    for key, value in list(event_dict.items()):
        if isinstance(key, str) and SENSITIVE_PATTERN.search(key):
            event_dict[key] = "***MASKED***"
        if isinstance(value, str) and SENSITIVE_PATTERN.search(key):
            event_dict[key] = "***MASKED***"
        if isinstance(value, dict):
            event_dict[key] = _mask_sensitive_fields(logger, method_name, value)
    return event_dict


def _add_request_context(
    logger: logging.Logger,
    method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    from app.middleware.request_id import get_current_request_id

    request_id = get_current_request_id()
    if request_id:
        event_dict["request_id"] = request_id
    return event_dict


def setup_logging() -> None:
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.DEBUG)

    renderer: Any
    if settings.LOG_FORMAT == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    processors: list[Any] = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        _add_request_context,
    ]

    if settings.LOG_MASK_SENSITIVE:
        processors.append(_mask_sensitive_fields)

    processors.append(renderer)

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)
    root_logger.addHandler(handler)

    for logger_name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True

    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.DEBUG if settings.DATABASE_ECHO else logging.WARNING
    )
    logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name or __name__)
    return logger
