"""AI provider configuration.

All AI behavior is configuration driven and centralized here. Values are read
from the existing project ``Settings`` (environment overridable). No provider
or service should hardcode API keys, timeouts, limits, or model names.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.config import settings


class AIProviderConfig(BaseModel):
    """Resolved configuration for a single AI provider instance."""

    provider: str
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    temperature: float = Field(default=0.7, ge=0, le=2)
    top_p: float = Field(default=0.9, ge=0, le=1)
    max_tokens: int = Field(default=4096, gt=0)
    max_input_tokens: int = Field(default=100000, gt=0)
    streaming_enabled: bool = True
    default_language: str | None = None
    default_difficulty: str | None = None

    timeout_connect: float = Field(default=10.0, gt=0)
    timeout_request: float = Field(default=60.0, gt=0)
    timeout_overall: float = Field(default=120.0, gt=0)

    retry_count: int = Field(default=3, ge=0)
    retry_min_delay: float = Field(default=1.0, ge=0)
    retry_max_delay: float = Field(default=30.0, ge=0)
    retry_jitter: float = Field(default=0.1, ge=0)

    rate_limit_rpm: int = Field(default=60, ge=0)
    cache_enabled: bool = False
    cache_ttl: int = Field(default=300, ge=0)
    max_cache_entries: int = Field(default=1024, ge=0)

    @classmethod
    def from_settings(cls, provider: str | None = None) -> AIProviderConfig:
        """Build a config from the global project settings."""
        selected = provider or settings.AI_PROVIDER or ""
        return cls(
            provider=selected,
            model=settings.AI_MODEL,
            api_key=settings.AI_API_KEY,
            base_url=settings.AI_BASE_URL,
            temperature=settings.AI_TEMPERATURE,
            top_p=settings.AI_TOP_P,
            max_tokens=settings.AI_MAX_TOKENS,
            max_input_tokens=settings.AI_MAX_INPUT_TOKENS,
            streaming_enabled=settings.AI_STREAMING_ENABLED,
            default_language=settings.AI_DEFAULT_LANGUAGE,
            default_difficulty=settings.AI_DEFAULT_DIFFICULTY,
            timeout_connect=settings.AI_TIMEOUT_CONNECT,
            timeout_request=settings.AI_TIMEOUT_REQUEST,
            timeout_overall=settings.AI_TIMEOUT_OVERALL,
            retry_count=settings.AI_RETRY_COUNT,
            retry_min_delay=settings.AI_RETRY_MIN_DELAY,
            retry_max_delay=settings.AI_RETRY_MAX_DELAY,
            retry_jitter=settings.AI_RETRY_JITTER,
            rate_limit_rpm=settings.AI_RATE_LIMIT_RPM,
            cache_enabled=settings.AI_CACHE_ENABLED,
            cache_ttl=settings.AI_CACHE_TTL,
        )

    @property
    def is_provider_configured(self) -> bool:
        return bool(self.provider)


def build_ai_provider_config(provider: str | None = None) -> AIProviderConfig:
    """Build a config from the current project settings."""
    return AIProviderConfig.from_settings(provider)
