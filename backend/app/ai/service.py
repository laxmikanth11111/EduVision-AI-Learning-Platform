"""AIContentService — orchestration layer between the application and providers.

The service is the only component above the provider interface. It applies
retries, overall timeouts, rate limiting, caching, observability and usage
accounting. Providers are reached exclusively through ``AIProvider``.

Prompts are never logged. Only safe metadata (request/correlation IDs,
provider, model, latency, status, retry count, token usage, estimated cost)
is emitted to structured logs.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from app.ai.base import AIHealthStatus, AIProvider
from app.ai.cache import AIResponseCache
from app.ai.config import AIProviderConfig, build_ai_provider_config
from app.ai.errors import AIError, AIGenerationTimeoutError
from app.ai.factory import create_ai_provider
from app.ai.models import AIRequest, AIResponse
from app.ai.ratelimit import AsyncRateLimiter
from app.ai.retry import RetryPolicy, run_with_retry
from app.core.logging import get_logger
from app.database.unit_of_work import UnitOfWork
from app.middleware.request_id import get_current_request_id
from app.repositories.ai_usage_repository import AIUsageRepository

logger = get_logger(__name__)


def _new_request_id() -> str:
    return f"ai_{uuid.uuid4().hex}"


class AIContentService:
    def __init__(
        self,
        uow: UnitOfWork | None = None,
        *,
        provider: AIProvider | None = None,
        config: AIProviderConfig | None = None,
        cache: AIResponseCache | None = None,
        rate_limiter: AsyncRateLimiter | None = None,
    ) -> None:
        self._config = config or build_ai_provider_config()
        self._provider = provider or create_ai_provider(config=self._config)
        self._policy = RetryPolicy.from_config(self._config)
        self._uow = uow
        self._usage_repo = AIUsageRepository(uow.session) if uow is not None else None
        self._cache = cache
        if self._cache is None and self._config.cache_enabled:
            self._cache = AIResponseCache(
                ttl=self._config.cache_ttl,
                max_entries=self._config.max_cache_entries,
            )
        self._limiter = rate_limiter or AsyncRateLimiter(self._config.rate_limit_rpm)

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def provider(self) -> AIProvider:
        return self._provider

    @property
    def config(self) -> AIProviderConfig:
        return self._config

    async def generate(self, request: AIRequest) -> AIResponse:
        """Generate content through the configured provider with full retries."""
        request = self._finalize_request(request)

        if self._cache is not None:
            cache_key = self._cache.key_for(request)
            cached = self._cache.get(cache_key)
            if cached is not None:
                logger.info(
                    "ai_cache_hit",
                    request_id=request.request_id,
                    correlation_id=request.correlation_id,
                    provider=self._provider.name,
                    model=self._resolved_model(request),
                )
                return cached

        logger.info(
            "ai_request_started",
            request_id=request.request_id,
            correlation_id=request.correlation_id,
            provider=self._provider.name,
            model=self._resolved_model(request),
            cache_enabled=self._cache is not None,
            retry_budget=self._policy.max_attempts,
        )

        start = time.monotonic()
        try:
            response, retries = await asyncio.wait_for(
                self._run_with_retry(request),
                timeout=self._config.timeout_overall,
            )
        except TimeoutError as exc:
            error = AIGenerationTimeoutError(
                message="AI generation timed out",
                internal_details={"timeout_seconds": self._config.timeout_overall},
                provider=self._provider.name,
                model=self._resolved_model(request),
                request_id=request.request_id,
                correlation_id=request.correlation_id,
            )
            await self._record_failure(error, request)
            logger.error("ai_generation_failed", **error.to_log_dict())
            raise error from exc
        except AIError as exc:
            await self._record_failure(exc, request)
            logger.error("ai_generation_failed", **exc.to_log_dict())
            raise

        latency_ms = (time.monotonic() - start) * 1000
        usage = response.usage.model_copy(
            update={"retry_count": retries, "latency_ms": latency_ms}
        )
        response = response.model_copy(
            update={
                "retry_count": retries,
                "latency_ms": latency_ms,
                "usage": usage,
                "request_id": response.request_id or request.request_id,
            }
        )

        await self._record_success(response, request)
        if self._cache is not None:
            self._cache.set(cache_key, response)

        logger.info(
            "ai_generation_success",
            request_id=response.request_id,
            correlation_id=response.correlation_id,
            provider=response.provider,
            model=response.model,
            latency_ms=response.latency_ms,
            status="success",
            retry_count=response.retry_count,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            total_tokens=response.usage.total_tokens,
            estimated_cost=str(response.usage.estimated_cost),
            finish_reason=response.finish_reason.value if response.finish_reason else None,
        )
        return response

    async def stream(self, request: AIRequest) -> Any:
        """Stream response text deltas through the provider (no caching)."""
        request = self._finalize_request(request)
        logger.info(
            "ai_stream_started",
            request_id=request.request_id,
            correlation_id=request.correlation_id,
            provider=self._provider.name,
            model=self._resolved_model(request),
        )
        if self._limiter.enabled:
            await self._limiter.acquire()
        return self._provider.stream(request)

    async def health(self) -> AIHealthStatus:
        return await self._provider.health_check()

    def estimate_tokens(self, text: str) -> int:
        return self._provider.estimate_tokens(text)

    async def close(self) -> None:
        await self._provider.close()

    # ── Internals ─────────────────────────────────────────────────────────────

    async def _run_with_retry(self, request: AIRequest) -> tuple[AIResponse, int]:
        async def _attempt() -> AIResponse:
            if self._limiter.enabled:
                await self._limiter.acquire()
            return await self._provider.generate(request)

        return await run_with_retry(
            self._policy,
            _attempt,
            on_retry=self._log_retry_attempt,
        )

    def _log_retry_attempt(self, attempt: int, exc: AIError, delay: float) -> None:
        logger.warning(
            "ai_retry_attempt",
            attempt=attempt,
            delay=delay,
            request_id=exc.request_id,
            correlation_id=exc.correlation_id,
            provider=exc.provider or self._provider.name,
            model=exc.model or self._resolved_model(AIRequest(user_prompt="")),
            error_type=type(exc).__name__,
        )

    def _finalize_request(self, request: AIRequest) -> AIRequest:
        return request.model_copy(
            update={
                "request_id": request.request_id or _new_request_id(),
                "correlation_id": request.correlation_id or get_current_request_id() or None,
                "temperature": (
                    request.temperature
                    if request.temperature is not None
                    else self._config.temperature
                ),
                "top_p": request.top_p if request.top_p is not None else self._config.top_p,
                "max_tokens": (
                    request.max_tokens if request.max_tokens is not None else self._config.max_tokens
                ),
                "language": request.language or self._config.default_language,
                "difficulty": request.difficulty or self._config.default_difficulty,
            }
        )

    def _resolved_model(self, request: AIRequest) -> str:
        return request.model_override or self._provider.info().model

    async def _record_success(
        self,
        response: AIResponse,
        request: AIRequest,
    ) -> None:
        if self._usage_repo is None:
            return
        resource_type, resource_id = self._resource_context(request)
        try:
            await self._usage_repo.create_from_response(
                response,
                resource_type=resource_type,
                resource_id=resource_id,
            )
        except Exception as exc:
            logger.warning(
                "ai_usage_record_failed",
                error=str(exc),
                request_id=response.request_id,
            )

    async def _record_failure(self, error: AIError, request: AIRequest) -> None:
        if self._usage_repo is None:
            return
        resource_type, resource_id = self._resource_context(request)
        try:
            await self._usage_repo.create_error_record(
                request=request,
                error=error,
                provider=self._provider.name,
                model=self._resolved_model(request),
                resource_type=resource_type,
                resource_id=resource_id,
            )
        except Exception as exc:
            logger.warning(
                "ai_usage_record_failed",
                error=str(exc),
                request_id=request.request_id,
            )

    @staticmethod
    def _resource_context(request: AIRequest) -> tuple[str | None, str | None]:
        metadata = request.metadata or {}
        return metadata.get("resource_type"), metadata.get("resource_id")
