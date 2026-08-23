from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from tenacity import (
    AsyncRetrying,
    before_sleep_log,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from tenacity.stop import stop_never

from app.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


def default_retry(
    attempts: int = 3,
    min_wait: float = 1.0,
    max_wait: float = 30.0,
    exceptions: tuple[type[Exception], ...] = (ConnectionError, TimeoutError, OSError),
) -> AsyncRetrying:
    return AsyncRetrying(
        stop=stop_after_attempt(attempts),
        wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
        retry=retry_if_exception_type(exceptions),
        before_sleep=before_sleep_log(logger, __import__("logging").WARNING),
        reraise=True,
    )


async def retry_async(
    func: Callable[..., Awaitable[T]],
    *args: Any,
    attempts: int = 3,
    min_wait: float = 1.0,
    max_wait: float = 30.0,
    exceptions: tuple[type[Exception], ...] = (ConnectionError, TimeoutError, OSError),
    **kwargs: Any,
) -> T:
    async for attempt in default_retry(attempts, min_wait, max_wait, exceptions):
        with attempt:
            return await func(*args, **kwargs)
    raise RuntimeError("Unreachable")


async def retry_async_forever(
    func: Callable[..., Awaitable[T]],
    *args: Any,
    min_wait: float = 1.0,
    max_wait: float = 60.0,
    **kwargs: Any,
) -> T:
    retryer = AsyncRetrying(
        stop=stop_never,
        wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
        before_sleep=before_sleep_log(logger, __import__("logging").WARNING),
        reraise=True,
    )
    async for attempt in retryer:
        with attempt:
            return await func(*args, **kwargs)
    raise RuntimeError("Unreachable")
