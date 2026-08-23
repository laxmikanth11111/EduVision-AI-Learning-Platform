"""Base class for HTTP-based (REST) AI providers."""

from __future__ import annotations

import asyncio
import time

import httpx

from app.ai.base import AICapability, AIHealthStatus, AIProvider, AIProviderInfo
from app.ai.config import AIProviderConfig
from app.ai.errors import AIError
from app.ai.models import AIRequest
from app.ai.providers._http import (
    as_ai_provider_unavailable,
    as_generation_timeout,
    build_http_client,
)


class HttpAIProvider(AIProvider):
    """Shared HTTP plumbing: lazy client, timeouts, transport error mapping."""

    default_model: str = ""
    default_base_url: str = ""
    description: str = ""

    def __init__(self, config: AIProviderConfig) -> None:
        self._config = config
        self._client: httpx.AsyncClient | None = None

    # ── Configuration helpers ────────────────────────────────────────────────

    @property
    def config(self) -> AIProviderConfig:
        return self._config

    @property
    def model(self) -> str:
        return self._config.model or self.default_model

    @property
    def base_url(self) -> str:
        return (self._config.base_url or self.default_base_url).rstrip("/")

    @property
    def api_key(self) -> str | None:
        return self._config.api_key

    # ── HTTP client lifecycle ────────────────────────────────────────────────

    def _client_instance(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = build_http_client(self._config)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ── Error translation ─────────────────────────────────────────────────────

    def _translate_transport_error(
        self,
        exc: Exception,
        *,
        request_id: str | None,
        correlation_id: str | None,
    ) -> AIError:
        if isinstance(exc, (asyncio.TimeoutError, httpx.TimeoutException)):
            return as_generation_timeout(
                exc,
                provider=self.name,
                model=self.model,
                request_id=request_id,
                correlation_id=correlation_id,
            )
        if isinstance(exc, httpx.HTTPError):
            return as_ai_provider_unavailable(
                exc,
                provider=self.name,
                model=self.model,
                request_id=request_id,
                correlation_id=correlation_id,
            )
        return as_ai_provider_unavailable(
            exc,
            provider=self.name,
            model=self.model,
            request_id=request_id,
            correlation_id=correlation_id,
        )

    def _wrap_ai_error(
        self,
        exc: AIError,
        *,
        request: AIRequest,
    ) -> AIError:
        """Attach request context to an already translated AI error."""
        exc.request_id = exc.request_id or request.request_id
        exc.correlation_id = exc.correlation_id or request.correlation_id
        exc.provider = exc.provider or self.name
        exc.model = exc.model or self.model
        return exc

    # ── Provider metadata ─────────────────────────────────────────────────────

    def info(self) -> AIProviderInfo:
        return AIProviderInfo(
            provider=self.name,
            model=self.model,
            description=self.description,
            supports_streaming=self._config.streaming_enabled,
            capabilities={AICapability.CHAT, AICapability.JSON},
            max_context_tokens=self._config.max_input_tokens,
            max_output_tokens=self._config.max_tokens,
            base_url=self.base_url,
            requires_api_key=self.requires_api_key,
        )

    # ── Health ────────────────────────────────────────────────────────────────

    async def health_check(self) -> AIHealthStatus:
        start = _monotonic_ms()
        try:
            await self._ping()
            return AIHealthStatus(
                healthy=True,
                provider=self.name,
                model=self.model,
                latency_ms=_monotonic_ms() - start,
            )
        except AIError as exc:
            return AIHealthStatus(
                healthy=False,
                provider=self.name,
                model=self.model,
                latency_ms=_monotonic_ms() - start,
                details={"error_type": type(exc).__name__},
            )

    async def _ping(self) -> None:
        """Provider-specific reachability probe (no content generation)."""
        raise NotImplementedError


def _monotonic_ms() -> float:
    return time.monotonic() * 1000
