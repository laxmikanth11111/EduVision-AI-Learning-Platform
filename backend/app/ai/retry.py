"""Bounded, configurable retry support for AI provider calls.

Retry behavior:
- Only ``AIError`` instances flagged as ``retryable`` are retried.
- Authentication failures, invalid configuration, malformed prompts, filtered
  content and unparseable responses are never retried.
- Timeouts, temporary outages, 429 rate limits and 5xx responses are retried
  with exponential backoff plus configurable jitter.
"""

from __future__ import annotations

import random
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from pydantic import BaseModel, Field

from app.ai.config import AIProviderConfig
from app.ai.errors import AIError, AIRateLimitExceededError

T = TypeVar("T")


class RetryPolicy(BaseModel):
    """Retry policy resolved from configuration."""

    max_attempts: int = Field(default=4, ge=1)
    min_delay: float = Field(default=1.0, ge=0)
    max_delay: float = Field(default=30.0, ge=0)
    jitter: float = Field(default=0.1, ge=0)
    backoff_base: float = Field(default=2.0, gt=1)

    @classmethod
    def from_config(cls, config: AIProviderConfig) -> RetryPolicy:
        """Build a policy from ``AIProviderConfig``.

        ``retry_count`` is the number of retries *after* the initial attempt,
        so total attempts = retry_count + 1 (consistent with Celery semantics).
        """
        return cls(
            max_attempts=max(1, config.retry_count + 1),
            min_delay=config.retry_min_delay,
            max_delay=config.retry_max_delay,
            jitter=config.retry_jitter,
        )

    def backoff_delay(self, attempt_number: int, retry_after: float | None = None) -> float:
        """Compute the exponential backoff (with jitter) for an attempt.

        ``retry_after`` (from a 429 ``Retry-After`` header) wins when present.
        """
        if retry_after is not None and retry_after >= 0:
            return float(retry_after)

        exponential = min(
            self.max_delay,
            self.min_delay * (self.backoff_base ** (attempt_number - 1)),
        )
        if self.jitter:
            exponential = exponential + random.uniform(0, self.jitter)
        return round(exponential, 3)


def is_retryable(exc: BaseException) -> bool:
    """True when the exception is an AI error that should be retried."""
    return isinstance(exc, AIError) and exc.retryable


def retry_after_from(exc: BaseException) -> float | None:
    """Extract a provider-suggested retry delay, if any."""
    if isinstance(exc, AIRateLimitExceededError):
        return exc.retry_after
    return None


async def run_with_retry(
    policy: RetryPolicy,
    func: Callable[[], Awaitable[T]],
    *,
    on_retry: Callable[[int, AIError, float], Any] | None = None,
) -> tuple[T, int]:
    """Execute ``func`` under the retry policy.

    Returns ``(result, retry_count)`` where ``retry_count`` is the number of
    retries actually performed. Non-retryable AI errors propagate immediately;
    when the budget is exhausted a retryable error is re-raised as-is.
    """
    last_error: AIError | None = None
    retries_performed = 0

    for attempt_number in range(1, policy.max_attempts + 1):
        try:
            return await func(), retries_performed
        except AIError as exc:
            last_error = exc
            if not exc.retryable:
                raise
            if attempt_number == policy.max_attempts:
                raise
            retries_performed = attempt_number
            delay = policy.backoff_delay(
                attempt_number,
                retry_after=retry_after_from(exc),
            )
            if on_retry is not None:
                on_retry(retries_performed, exc, delay)
            await asyncio_sleep(delay)

    assert last_error is not None
    raise last_error


async def asyncio_sleep(delay: float) -> None:
    """Thin indirection over ``asyncio.sleep`` (patchable in tests)."""
    import asyncio

    await asyncio.sleep(delay)
