from __future__ import annotations

import pytest

from app.ai.errors import (
    AIAuthenticationFailedError,
    AIContentFilteredError,
    AIError,
    AIGenerationTimeoutError,
    AIInvalidConfigurationError,
    AIInvalidResponseError,
    AIProviderUnavailableError,
    AIQuotaExceededError,
    AIRateLimitExceededError,
    AIRetryLimitExceededError,
)
from app.core.error_codes import ErrorCode


class TestAIErrorBase:
    def test_to_log_dict_never_contains_prompts(self) -> None:
        error = AIProviderUnavailableError(
            message="boom",
            provider="gemini",
            model="gemini-1.5-flash",
            request_id="req-1",
            correlation_id="corr-1",
        )
        log = error.to_log_dict()
        assert log["error_type"] == "AIProviderUnavailableError"
        assert log["code"] == ErrorCode.SERVICE_UNAVAILABLE.value
        assert log["message"] == "boom"
        assert log["provider"] == "gemini"
        assert log["request_id"] == "req-1"
        assert log["correlation_id"] == "corr-1"
        joined = " ".join(str(value) for value in log.values())
        assert "user_prompt" not in joined
        assert "system_prompt" not in joined

    def test_cause_is_chained(self) -> None:
        root = RuntimeError("socket down")
        error = AIProviderUnavailableError(cause=root)
        assert error.__cause__ is root

    def test_default_retry_recommended_matches_retryable(self) -> None:
        assert AIProviderUnavailableError().retry_recommended is True
        assert AIInvalidConfigurationError().retry_recommended is False


class TestErrorMapping:
    @pytest.mark.parametrize(
        ("error_cls", "expected_code", "expected_status", "expected_retryable"),
        [
            (AIProviderUnavailableError, ErrorCode.SERVICE_UNAVAILABLE, 503, True),
            (AIInvalidConfigurationError, ErrorCode.CONFIGURATION_ERROR, 500, False),
            (AIRateLimitExceededError, ErrorCode.RATE_LIMITED, 429, True),
            (AIAuthenticationFailedError, ErrorCode.EXTERNAL_SERVICE_ERROR, 500, False),
            (AIQuotaExceededError, ErrorCode.EXTERNAL_SERVICE_ERROR, 503, False),
            (AIGenerationTimeoutError, ErrorCode.TIMEOUT, 504, True),
            (AIInvalidResponseError, ErrorCode.EXTERNAL_SERVICE_ERROR, 502, False),
            (AIContentFilteredError, ErrorCode.EXTERNAL_SERVICE_ERROR, 502, False),
            (AIRetryLimitExceededError, ErrorCode.EXTERNAL_SERVICE_ERROR, 503, False),
        ],
    )
    def test_metadata(
        self,
        error_cls: type[AIError],
        expected_code: ErrorCode,
        expected_status: int,
        expected_retryable: bool,
    ) -> None:
        error = error_cls()
        assert error.code == expected_code
        assert error.status_code == expected_status
        assert error.retryable is expected_retryable

    def test_rate_limit_retry_after(self) -> None:
        error = AIRateLimitExceededError(retry_after=7.5)
        assert error.retry_after == 7.5


class TestContextEnrichment:
    def test_provider_context_is_carried(self) -> None:
        error = AIGenerationTimeoutError(
            provider="openai",
            model="gpt-4o-mini",
            request_id="r1",
            correlation_id="c1",
        )
        assert error.provider == "openai"
        assert error.model == "gpt-4o-mini"
        assert error.request_id == "r1"
        assert error.correlation_id == "c1"
