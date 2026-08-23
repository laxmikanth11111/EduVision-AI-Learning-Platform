"""AI infrastructure and provider layer for EduVision AI.

This package provides a provider-agnostic abstraction over external AI/LLM
APIs. Upper layers interact exclusively with the ``AIProvider`` interface and
the normalized ``AIRequest`` / ``AIResponse`` models — they never depend on a
specific vendor SDK or wire format.

    Application
        ↓
    AIContentService
        ↓
    AIProvider (interface)
        ↓
    Gemini / OpenAI / Local providers
        ↓
    External AI APIs
"""

from app.ai.base import AICapability, AIHealthStatus, AIProvider, AIProviderInfo
from app.ai.config import AIProviderConfig
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
from app.ai.models import (
    AIRequest,
    AIResponse,
    AIResponseFormat,
    FinishReason,
    TokenUsage,
)
from app.ai.service import AIContentService

__all__ = [
    "AICapability",
    "AIContentService",
    "AIError",
    "AIHealthStatus",
    "AIInvalidConfigurationError",
    "AIProvider",
    "AIProviderConfig",
    "AIProviderInfo",
    "AIProviderUnavailableError",
    "AIRequest",
    "AIResponse",
    "AIResponseFormat",
    "AIAuthenticationFailedError",
    "AIContentFilteredError",
    "AIGenerationTimeoutError",
    "AIInvalidResponseError",
    "AIQuotaExceededError",
    "AIRateLimitExceededError",
    "AIRetryLimitExceededError",
    "FinishReason",
    "TokenUsage",
]
