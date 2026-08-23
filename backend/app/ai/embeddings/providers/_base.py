"""Base class for HTTP-based (REST) embedding providers."""

from __future__ import annotations

import asyncio
import time

import httpx

from app.ai.embeddings.base import EmbeddingProvider
from app.ai.embeddings.config import EmbeddingProviderConfig
from app.ai.embeddings.models import (
    EmbeddingHealthStatus,
    EmbeddingProviderInfo,
    EmbeddingResponse,
)
from app.ai.embeddings.providers._http import (
    as_embedding_timeout,
    as_embedding_unavailable,
    build_http_client,
)
from app.ai.errors import AIError
from app.ai.retry import RetryPolicy, run_with_retry


class HttpEmbeddingProvider(EmbeddingProvider):
    """Shared HTTP plumbing: lazy client, timeouts, transport error mapping."""

    default_base_url: str = ""
    description: str = ""

    def __init__(self, config: EmbeddingProviderConfig) -> None:
        super().__init__(config)
        self._client: httpx.AsyncClient | None = None

    @property
    def config(self) -> EmbeddingProviderConfig:
        return self._config

    @property
    def base_url(self) -> str:
        return (self._config.base_url or self.default_base_url).rstrip("/")

    @property
    def api_key(self) -> str | None:
        return self._config.api_key

    def _client_instance(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = build_http_client(self._config)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ── Embedding ─────────────────────────────────────────────────────────────

    async def embed(
        self,
        texts: list[str],
        *,
        request_id: str | None = None,
        correlation_id: str | None = None,
    ) -> EmbeddingResponse:
        if not texts:
            raise AIError(
                message="No texts provided to the embedding provider",
                internal_details={"provider": self.name},
                retryable=False,
                provider=self.name,
                model=self.model,
            )

        async def _attempt() -> EmbeddingResponse:
            try:
                return await self._embed_impl(
                    texts,
                    request_id=request_id,
                    correlation_id=correlation_id,
                )
            except AIError:
                raise
            except Exception as exc:
                raise self._translate_transport_error(
                    exc,
                    request_id=request_id,
                    correlation_id=correlation_id,
                ) from exc

        result, _retries = await run_with_retry(self._retry_policy(), _attempt)
        return result

    def _retry_policy(self) -> RetryPolicy:
        """Retry policy derived from the embedding config.

        Mirrors ``RetryPolicy.from_config`` semantics: ``retry_count`` is the
        number of retries *after* the initial attempt, so total attempts =
        ``EMBEDDING_MAX_RETRIES + 1``.
        """
        return RetryPolicy(
            max_attempts=max(1, self._config.retry_count + 1),
            min_delay=self._config.retry_min_delay,
            max_delay=self._config.retry_max_delay,
            jitter=self._config.retry_jitter,
        )

    async def _embed_impl(
        self,
        texts: list[str],
        *,
        request_id: str | None,
        correlation_id: str | None,
    ) -> EmbeddingResponse:
        raise NotImplementedError

    # ── Error translation ─────────────────────────────────────────────────────

    def _translate_transport_error(
        self,
        exc: Exception,
        *,
        request_id: str | None,
        correlation_id: str | None,
    ) -> AIError:
        if isinstance(exc, (asyncio.TimeoutError, httpx.TimeoutException)):
            return as_embedding_timeout(
                exc,
                provider=self.name,
                model=self.model,
                request_id=request_id,
                correlation_id=correlation_id,
            )
        return as_embedding_unavailable(
            exc,
            provider=self.name,
            model=self.model,
            request_id=request_id,
            correlation_id=correlation_id,
        )

    # ── Provider metadata ─────────────────────────────────────────────────────

    def info(self) -> EmbeddingProviderInfo:
        return EmbeddingProviderInfo(
            provider=self.name,
            model=self.model,
            description=self.description,
            dimension=self.dimension,
            max_input_tokens=self._config.max_input_tokens,
            max_batch_size=self._config.max_batch_size,
            supports_batching=True,
            requires_api_key=self.requires_api_key,
        )

    # ── Health ────────────────────────────────────────────────────────────────

    async def health_check(self) -> EmbeddingHealthStatus:
        start = time.monotonic() * 1000
        try:
            await self._ping()
            return EmbeddingHealthStatus(
                healthy=True,
                provider=self.name,
                model=self.model,
                latency_ms=(time.monotonic() * 1000) - start,
            )
        except AIError as exc:
            return EmbeddingHealthStatus(
                healthy=False,
                provider=self.name,
                model=self.model,
                latency_ms=(time.monotonic() * 1000) - start,
                details={"error_type": type(exc).__name__},
            )

    async def _ping(self) -> None:
        """Provider-specific reachability probe (no content embedding)."""
        raise NotImplementedError
