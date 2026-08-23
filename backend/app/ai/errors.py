"""Application-level AI errors.

Provider-specific exceptions (SDK errors, raw HTTP errors, vendor wire errors)
must never leak beyond the provider boundary. Providers translate them into
these normalized errors. Each error carries a safe client-facing message,
internal-only details, a retry recommendation, and structured logging metadata.

No AI error should ever contain API keys, authorization headers, or raw prompt
content.
"""

from __future__ import annotations

from typing import Any

from app.core.error_codes import ErrorCode
from app.core.exceptions import EduVisionError


class AIError(EduVisionError):
    """Base class for every AI-layer error."""

    def __init__(
        self,
        message: str = "AI generation failed",
        *,
        code: ErrorCode = ErrorCode.EXTERNAL_SERVICE_ERROR,
        status_code: int = 500,
        details: dict[str, Any] | None = None,
        internal_details: dict[str, Any] | None = None,
        retryable: bool = False,
        retry_recommended: bool | None = None,
        retry_after: float | None = None,
        cause: Exception | None = None,
        provider: str | None = None,
        model: str | None = None,
        request_id: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=status_code,
            details=details,
        )
        self.internal_details = internal_details or {}
        self.retryable = retryable
        self.retry_recommended = (
            retry_recommended if retry_recommended is not None else retryable
        )
        self.retry_after = retry_after
        self.provider = provider
        self.model = model
        self.request_id = request_id
        self.correlation_id = correlation_id
        if cause is not None:
            self.__cause__ = cause

    @property
    def safe_message(self) -> str:
        """Message safe to expose to clients and logs."""
        return self.message

    def to_log_dict(self) -> dict[str, Any]:
        """Structured metadata safe to emit through logging."""
        return {
            "error_type": self.__class__.__name__,
            "code": self.code.value,
            "message": self.message,
            "retryable": self.retryable,
            "retry_recommended": self.retry_recommended,
            "retry_after": self.retry_after,
            "provider": self.provider,
            "model": self.model,
            "request_id": self.request_id,
            "correlation_id": self.correlation_id,
            "internal_details": self.internal_details,
        }


class AIProviderUnavailableError(AIError):
    """The AI provider could not be reached or is temporarily down."""

    def __init__(
        self,
        message: str = "The AI provider is temporarily unavailable",
        *,
        details: dict[str, Any] | None = None,
        internal_details: dict[str, Any] | None = None,
        cause: Exception | None = None,
        provider: str | None = None,
        model: str | None = None,
        request_id: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=ErrorCode.SERVICE_UNAVAILABLE,
            status_code=503,
            details=details,
            internal_details=internal_details,
            retryable=True,
            cause=cause,
            provider=provider,
            model=model,
            request_id=request_id,
            correlation_id=correlation_id,
        )


class AIInvalidConfigurationError(AIError):
    """The AI layer is not configured correctly (missing key, bad model...)."""

    def __init__(
        self,
        message: str = "AI configuration is invalid",
        *,
        details: dict[str, Any] | None = None,
        internal_details: dict[str, Any] | None = None,
        provider: str | None = None,
        model: str | None = None,
        request_id: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=ErrorCode.CONFIGURATION_ERROR,
            status_code=500,
            details=details,
            internal_details=internal_details,
            retryable=False,
            provider=provider,
            model=model,
            request_id=request_id,
            correlation_id=correlation_id,
        )


class AIRateLimitExceededError(AIError):
    """The provider rate limit was exceeded (429 with a retry window)."""

    def __init__(
        self,
        message: str = "AI provider rate limit exceeded",
        *,
        details: dict[str, Any] | None = None,
        internal_details: dict[str, Any] | None = None,
        retry_after: float | None = None,
        provider: str | None = None,
        model: str | None = None,
        request_id: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=ErrorCode.RATE_LIMITED,
            status_code=429,
            details=details,
            internal_details=internal_details,
            retryable=True,
            retry_after=retry_after,
            provider=provider,
            model=model,
            request_id=request_id,
            correlation_id=correlation_id,
        )


class AIAuthenticationFailedError(AIError):
    """The provider rejected the configured credentials."""

    def __init__(
        self,
        message: str = "AI provider authentication failed",
        *,
        details: dict[str, Any] | None = None,
        internal_details: dict[str, Any] | None = None,
        provider: str | None = None,
        model: str | None = None,
        request_id: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=ErrorCode.EXTERNAL_SERVICE_ERROR,
            status_code=500,
            details=details,
            internal_details=internal_details,
            retryable=False,
            retry_recommended=False,
            provider=provider,
            model=model,
            request_id=request_id,
            correlation_id=correlation_id,
        )


class AIQuotaExceededError(AIError):
    """The provider account quota / billing limit was exhausted."""

    def __init__(
        self,
        message: str = "AI provider quota exceeded",
        *,
        details: dict[str, Any] | None = None,
        internal_details: dict[str, Any] | None = None,
        provider: str | None = None,
        model: str | None = None,
        request_id: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=ErrorCode.EXTERNAL_SERVICE_ERROR,
            status_code=503,
            details=details,
            internal_details=internal_details,
            retryable=False,
            retry_recommended=False,
            provider=provider,
            model=model,
            request_id=request_id,
            correlation_id=correlation_id,
        )


class AIGenerationTimeoutError(AIError):
    """A provider call exceeded a configured timeout."""

    def __init__(
        self,
        message: str = "AI generation timed out",
        *,
        details: dict[str, Any] | None = None,
        internal_details: dict[str, Any] | None = None,
        cause: Exception | None = None,
        provider: str | None = None,
        model: str | None = None,
        request_id: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=ErrorCode.TIMEOUT,
            status_code=504,
            details=details,
            internal_details=internal_details,
            retryable=True,
            cause=cause,
            provider=provider,
            model=model,
            request_id=request_id,
            correlation_id=correlation_id,
        )


class AIInvalidResponseError(AIError):
    """The provider returned a response that could not be parsed / validated."""

    def __init__(
        self,
        message: str = "The AI provider returned an invalid response",
        *,
        details: dict[str, Any] | None = None,
        internal_details: dict[str, Any] | None = None,
        provider: str | None = None,
        model: str | None = None,
        request_id: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=ErrorCode.EXTERNAL_SERVICE_ERROR,
            status_code=502,
            details=details,
            internal_details=internal_details,
            retryable=False,
            retry_recommended=False,
            provider=provider,
            model=model,
            request_id=request_id,
            correlation_id=correlation_id,
        )


class AIContentFilteredError(AIError):
    """The provider blocked the request or response due to safety policy."""

    def __init__(
        self,
        message: str = "The AI provider filtered the content",
        *,
        details: dict[str, Any] | None = None,
        internal_details: dict[str, Any] | None = None,
        provider: str | None = None,
        model: str | None = None,
        request_id: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=ErrorCode.EXTERNAL_SERVICE_ERROR,
            status_code=502,
            details=details,
            internal_details=internal_details,
            retryable=False,
            retry_recommended=False,
            provider=provider,
            model=model,
            request_id=request_id,
            correlation_id=correlation_id,
        )


class AITruncationError(AIError):
    """The provider hit its maximum output token limit before finishing.

    The response text is incomplete and therefore unusable. Retrying at the
    provider layer with the identical prompt is pointless (the same budget
    applies), so this error is NOT ``retryable`` there — callers are expected
    to rebuild the request with a tighter budget and retry at their own layer
    (see ``retry_recommended``).
    """

    def __init__(
        self,
        message: str = "The AI response was truncated because it reached the maximum output token limit",
        *,
        details: dict[str, Any] | None = None,
        internal_details: dict[str, Any] | None = None,
        provider: str | None = None,
        model: str | None = None,
        request_id: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=ErrorCode.EXTERNAL_SERVICE_ERROR,
            status_code=502,
            details=details,
            internal_details=internal_details,
            retryable=False,
            retry_recommended=True,
            provider=provider,
            model=model,
            request_id=request_id,
            correlation_id=correlation_id,
        )


class AIRetryLimitExceededError(AIError):
    """Retry budget exhausted after repeated retryable failures."""

    def __init__(
        self,
        message: str = "AI request failed after exhausting retries",
        *,
        details: dict[str, Any] | None = None,
        internal_details: dict[str, Any] | None = None,
        cause: Exception | None = None,
        provider: str | None = None,
        model: str | None = None,
        request_id: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=ErrorCode.EXTERNAL_SERVICE_ERROR,
            status_code=503,
            details=details,
            internal_details=internal_details,
            retryable=False,
            retry_recommended=True,
            cause=cause,
            provider=provider,
            model=model,
            request_id=request_id,
            correlation_id=correlation_id,
        )
