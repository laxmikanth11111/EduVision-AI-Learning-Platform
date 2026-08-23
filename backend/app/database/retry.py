from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any, TypeVar

from sqlalchemy.exc import DBAPIError

from app.core.config import settings
from app.core.logging import get_logger

T = TypeVar("T")

logger = get_logger(__name__)

TRANSIENT_PG_CODES = frozenset({"40001", "40P01"})

RETRYABLE_EXCEPTIONS = (DBAPIError,)


def is_transient_pg_error(exc: Exception) -> bool:
    if not isinstance(exc, DBAPIError):
        return False
    orig = getattr(exc, "orig", None)
    target = orig if orig is not None else exc
    pgcode = getattr(target, "pgcode", None) or getattr(target, "sqlstate", None)
    if pgcode is None and hasattr(target, "code"):
        pgcode = getattr(target, "code", None)
    return str(pgcode) in TRANSIENT_PG_CODES if pgcode is not None else False


async def retry_on_db_failure(
    func: Callable[..., Awaitable[T]],
    *args: Any,
    max_retries: int | None = None,
    base_delay: float = 0.1,
    max_delay: float = 2.0,
    jitter: float = 0.1,
    **kwargs: Any,
) -> T:
    _max_retries = max_retries if max_retries is not None else settings.DATABASE_RETRY_ATTEMPTS
    _base_delay = base_delay
    _max_delay = max_delay
    _jitter = jitter

    last_exception: Exception | None = None

    for attempt in range(_max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except RETRYABLE_EXCEPTIONS as exc:
            if not is_transient_pg_error(exc):
                raise
            last_exception = exc
            if attempt < _max_retries:
                delay = min(_base_delay * (2**attempt) + random.uniform(0, _jitter), _max_delay)
                logger.warning(
                    "transaction_retry",
                    attempt=attempt + 1,
                    max_retries=_max_retries,
                    delay_ms=round(delay * 1000),
                    error=str(exc),
                    pgcode=getattr(getattr(exc, "orig", None), "pgcode", "unknown"),
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    "transaction_retry_exhausted",
                    attempts=_max_retries + 1,
                    error=str(exc),
                )
                raise

    if last_exception is not None:
        raise last_exception
    raise RuntimeError("Exhausted retry loop without exception")  # pragma: no cover


def db_retry(
    max_retries: int | None = None,
    base_delay: float = 0.1,
    max_delay: float = 2.0,
    jitter: float = 0.1,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Coroutine[Any, Any, T]]]:
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Coroutine[Any, Any, T]]:
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            return await retry_on_db_failure(
                func,
                *args,
                max_retries=max_retries,
                base_delay=base_delay,
                max_delay=max_delay,
                jitter=jitter,
                **kwargs,
            )
        return wrapper
    return decorator
