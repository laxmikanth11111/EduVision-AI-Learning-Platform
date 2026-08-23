from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.ai.config import AIProviderConfig
from app.ai.errors import (
    AIError,
    AIInvalidConfigurationError,
    AIProviderUnavailableError,
    AIRateLimitExceededError,
)
from app.ai.retry import RetryPolicy, is_retryable, retry_after_from, run_with_retry

_config = AIProviderConfig(provider="local", retry_count=2)


class TestRetryPolicy:
    def test_from_config_maps_retry_count(self) -> None:
        policy = RetryPolicy.from_config(_config)
        assert policy.max_attempts == 3
        assert policy.min_delay == 1.0

    def test_backoff_capped_at_max(self) -> None:
        policy = RetryPolicy(min_delay=1.0, max_delay=4.0, jitter=0)
        assert policy.backoff_delay(1) == 1.0
        assert policy.backoff_delay(2) == 2.0
        assert policy.backoff_delay(3) == 4.0
        assert policy.backoff_delay(10) == 4.0

    def test_retry_after_header_wins(self) -> None:
        policy = RetryPolicy(min_delay=1.0, max_delay=30.0, jitter=0)
        assert policy.backoff_delay(1, retry_after=12.5) == 12.5


class TestHelpers:
    def test_is_retryable(self) -> None:
        assert is_retryable(AIProviderUnavailableError()) is True
        assert is_retryable(AIRateLimitExceededError()) is True
        assert is_retryable(AIInvalidConfigurationError()) is False
        assert is_retryable(ValueError("x")) is False

    def test_retry_after_from(self) -> None:
        assert retry_after_from(AIRateLimitExceededError(retry_after=3.0)) == 3.0
        assert retry_after_from(AIProviderUnavailableError()) is None


class TestRunWithRetry:
    async def test_success_on_first_attempt(self) -> None:
        calls = 0

        async def func() -> str:
            nonlocal calls
            calls += 1
            return "ok"

        result, retries = await run_with_retry(_policy(), func)
        assert result == "ok"
        assert retries == 0
        assert calls == 1

    async def test_recovers_after_retryable_failures(self) -> None:
        calls = 0

        async def func() -> str:
            nonlocal calls
            calls += 1
            if calls < 3:
                raise AIProviderUnavailableError()
            return "recovered"

        with patch("app.ai.retry.asyncio_sleep", new=AsyncMock()):
            result, retries = await run_with_retry(_policy(), func)
        assert result == "recovered"
        assert retries == 2
        assert calls == 3

    async def test_non_retryable_propagates_immediately(self) -> None:
        calls = 0

        async def func() -> str:
            nonlocal calls
            calls += 1
            raise AIInvalidConfigurationError()

        with (
            patch("app.ai.retry.asyncio_sleep", new=AsyncMock()),
            pytest.raises(AIInvalidConfigurationError),
        ):
            await run_with_retry(_policy(), func)
        assert calls == 1

    async def test_budget_exhausted_raises_last_error(self) -> None:
        async def func() -> str:
            raise AIProviderUnavailableError()

        with (
            patch("app.ai.retry.asyncio_sleep", new=AsyncMock()),
            pytest.raises(AIProviderUnavailableError) as exc_info,
        ):
            await run_with_retry(_policy(), func)
        assert isinstance(exc_info.value, AIError)

    async def test_on_retry_callback_receives_attempts(self) -> None:
        calls = 0
        seen: list[tuple[int, AIError, float]] = []

        async def func() -> str:
            nonlocal calls
            calls += 1
            if calls < 3:
                raise AIProviderUnavailableError()
            return "ok"

        with patch("app.ai.retry.asyncio_sleep", new=AsyncMock()):
            await run_with_retry(_policy(), func, on_retry=lambda a, e, d: seen.append((a, e, d)))
        assert [(attempt, delay) for attempt, _, delay in seen] == [(1, 1.0), (2, 2.0)]


def _policy() -> RetryPolicy:
    return RetryPolicy(max_attempts=3, min_delay=1.0, max_delay=30.0, jitter=0)
