"""Embedding provider configuration.

Values are read from the project ``Settings``. ``EMBEDDING_PROVIDER`` accepts
the same provider names as ``AI_PROVIDER``; when unset, the chat provider is
used for embeddings too. Transport-level settings (timeouts, rate limit) fall
back to the shared AI settings so operators do not need to duplicate them; the
embedding retry budget is owned by ``EMBEDDING_MAX_RETRIES``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.config import settings


class EmbeddingProviderConfig(BaseModel):
    """Resolved configuration for a single embedding provider instance."""

    provider: str
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    dimension: int = Field(default=0, ge=0)
    max_input_tokens: int = Field(default=8192, gt=0)
    max_batch_size: int = Field(default=32, gt=0)

    timeout_connect: float = Field(default=10.0, gt=0)
    timeout_request: float = Field(default=60.0, gt=0)
    timeout_overall: float = Field(default=120.0, gt=0)

    retry_count: int = Field(default=3, ge=0)
    retry_min_delay: float = Field(default=1.0, ge=0)
    retry_max_delay: float = Field(default=30.0, ge=0)
    retry_jitter: float = Field(default=0.1, ge=0)

    rate_limit_rpm: int = Field(default=60, ge=0)
    cache_enabled: bool = False
    cache_ttl: int = Field(default=86400, ge=0)
    max_cache_entries: int = Field(default=1024, ge=0)

    @classmethod
    def from_settings(cls, provider: str | None = None) -> EmbeddingProviderConfig:
        """Build a config from the global project settings.

        The provider defaults to ``EMBEDDING_PROVIDER`` and then to the shared
        ``AI_PROVIDER`` so an embedding pipeline can reuse the chat provider
        without extra configuration.
        """
        selected = provider or settings.EMBEDDING_PROVIDER or settings.AI_PROVIDER or ""
        return cls(
            provider=selected,
            model=settings.EMBEDDING_MODEL or settings.AI_MODEL,
            api_key=settings.AI_API_KEY,
            base_url=settings.AI_BASE_URL,
            max_input_tokens=settings.AI_MAX_INPUT_TOKENS,
            max_batch_size=settings.EMBEDDING_BATCH_SIZE,
            timeout_connect=settings.AI_TIMEOUT_CONNECT,
            timeout_request=settings.AI_TIMEOUT_REQUEST,
            timeout_overall=settings.AI_TIMEOUT_OVERALL,
            retry_count=settings.EMBEDDING_MAX_RETRIES,
            retry_min_delay=settings.AI_RETRY_MIN_DELAY,
            retry_max_delay=settings.AI_RETRY_MAX_DELAY,
            retry_jitter=settings.AI_RETRY_JITTER,
            rate_limit_rpm=settings.AI_RATE_LIMIT_RPM,
            cache_enabled=settings.AI_CACHE_ENABLED,
            cache_ttl=settings.EMBEDDING_CACHE_TTL,
        )


def build_embedding_provider_config(
    provider: str | None = None,
) -> EmbeddingProviderConfig:
    """Build a config from the current project settings."""
    return EmbeddingProviderConfig.from_settings(provider)
