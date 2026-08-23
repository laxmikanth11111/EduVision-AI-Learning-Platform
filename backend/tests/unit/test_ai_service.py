from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.ai.base import AICapability, AIHealthStatus, AIProvider, AIProviderInfo
from app.ai.cache import AIResponseCache
from app.ai.config import AIProviderConfig
from app.ai.errors import (
    AIGenerationTimeoutError,
    AIInvalidConfigurationError,
    AIProviderUnavailableError,
)
from app.ai.models import AIRequest, AIResponse, TokenUsage
from app.ai.providers.local import LocalMockProvider
from app.ai.service import AIContentService
from app.database.unit_of_work import UnitOfWork
from app.repositories.ai_usage_repository import AIUsageRepository


def _response(**overrides: Any) -> AIResponse:
    values = {
        "text": "ok",
        "usage": TokenUsage(input_tokens=5, output_tokens=3),
        "provider": "fake",
        "model": "fake-model",
    }
    values.update(overrides)
    return AIResponse(**values)


class FakeProvider(AIProvider):
    name = "fake"
    requires_api_key = False

    def __init__(self, config: AIProviderConfig, outcomes: list[Any]) -> None:
        super().__init__(config)
        self._outcomes = list(outcomes)
        self.calls = 0

    def info(self) -> AIProviderInfo:
        return AIProviderInfo(
            provider="fake",
            model="fake-model",
            supports_streaming=False,
            capabilities={AICapability.CHAT},
        )

    async def generate(self, request: AIRequest) -> AIResponse:
        self.calls += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        if callable(outcome):
            return await outcome(request)
        return outcome

    async def health_check(self) -> AIHealthStatus:
        return AIHealthStatus(healthy=True, provider="fake", model="fake-model")


def _config(**overrides: Any) -> AIProviderConfig:
    values: dict[str, Any] = {
        "provider": "fake",
        "retry_count": 2,
        "retry_min_delay": 0.001,
        "retry_max_delay": 0.01,
        "retry_jitter": 0,
        "timeout_overall": 10,
        "rate_limit_rpm": 0,
        "cache_enabled": False,
    }
    values.update(overrides)
    return AIProviderConfig(**values)


def _local_config() -> AIProviderConfig:
    return AIProviderConfig(provider="local", retry_count=0)


class TestGenerate:
    async def test_success(self) -> None:
        provider = FakeProvider(_config(), [_response()])
        service = AIContentService(provider=provider, config=_config())
        response = await service.generate(AIRequest(user_prompt="hi"))
        assert response.text == "ok"
        assert provider.calls == 1
        assert response.retry_count == 0
        assert response.request_id.startswith("ai_")

    async def test_request_defaults_applied_from_config(self) -> None:
        captured: list[AIRequest] = []

        async def record(request: AIRequest) -> AIResponse:
            captured.append(request)
            return _response()

        provider = FakeProvider(_config(), [record])
        service = AIContentService(provider=provider, config=_config())
        await service.generate(AIRequest(user_prompt="hi"))
        assert captured[0].temperature == _config().temperature
        assert captured[0].top_p == _config().top_p
        assert captured[0].max_tokens == _config().max_tokens
        assert captured[0].request_id is not None

    async def test_recovers_after_retryable_failures(self) -> None:
        failure = AIProviderUnavailableError(provider="fake", model="fake-model")
        provider = FakeProvider(_config(), [failure, failure, _response()])
        service = AIContentService(provider=provider, config=_config())
        response = await service.generate(AIRequest(user_prompt="hi"))
        assert provider.calls == 3
        assert response.retry_count == 2

    async def test_non_retryable_propagates_without_retry(self) -> None:
        provider = FakeProvider(_config(), [AIInvalidConfigurationError()])
        service = AIContentService(provider=provider, config=_config())
        with pytest.raises(AIInvalidConfigurationError):
            await service.generate(AIRequest(user_prompt="hi"))
        assert provider.calls == 1

    async def test_overall_timeout(self) -> None:
        async def slow(request: AIRequest) -> AIResponse:
            await asyncio.sleep(1)
            return _response()

        config = _config(retry_count=0, timeout_overall=0.05)
        provider = FakeProvider(config, [slow])
        service = AIContentService(provider=provider, config=config)
        with pytest.raises(AIGenerationTimeoutError):
            await service.generate(AIRequest(user_prompt="hi"))
        assert provider.calls == 1


class TestCache:
    async def test_second_call_hits_cache(self) -> None:
        config = _config(cache_enabled=True, cache_ttl=60)
        provider = FakeProvider(config, [_response()])
        provider.generate = AsyncMock(wraps=provider.generate)
        service = AIContentService(provider=provider, config=config)

        first = await service.generate(AIRequest(user_prompt="same"))
        second = await service.generate(AIRequest(user_prompt="same"))
        assert provider.generate.await_count == 1
        assert first.text == second.text

    async def test_different_prompts_bypass_cache(self) -> None:
        config = _config(cache_enabled=True, cache_ttl=60)
        provider = FakeProvider(config, [_response(), _response()])
        service = AIContentService(provider=provider, config=config)

        await service.generate(AIRequest(user_prompt="one"))
        await service.generate(AIRequest(user_prompt="two"))
        assert provider.calls == 2

    async def test_cache_disabled_by_default(self) -> None:
        config = _config(cache_enabled=False)
        provider = FakeProvider(config, [_response(), _response()])
        service = AIContentService(provider=provider, config=config)
        await service.generate(AIRequest(user_prompt="same"))
        await service.generate(AIRequest(user_prompt="same"))
        assert provider.calls == 2


class TestUsageRecording:
    async def test_success_recorded(self, db_session) -> None:
        config = _local_config()
        provider = LocalMockProvider(config)
        service = AIContentService(
            uow=UnitOfWork(session=db_session),
            provider=provider,
            config=config,
        )
        response = await service.generate(AIRequest(user_prompt="hello"))
        rows = await AIUsageRepository(db_session).find(request_id=response.request_id)
        assert len(rows) == 1
        assert rows[0].status == "success"
        assert rows[0].provider == "local"
        assert rows[0].input_tokens == response.usage.input_tokens
        assert rows[0].output_tokens == response.usage.output_tokens
        assert rows[0].total_tokens == response.usage.total_tokens
        assert rows[0].estimated_cost == Decimal("0.000000")

    async def test_error_recorded(self, db_session) -> None:
        config = _config(retry_count=0)
        failure = AIProviderUnavailableError(provider="fake", model="fake-model")
        provider = FakeProvider(config, [failure])
        service = AIContentService(
            uow=UnitOfWork(session=db_session),
            provider=provider,
            config=config,
        )
        with pytest.raises(AIProviderUnavailableError):
            await service.generate(AIRequest(user_prompt="hello"))
        rows = await AIUsageRepository(db_session).find(provider="fake", status="error")
        assert len(rows) == 1
        assert rows[0].error_code == "SERVICE_UNAVAILABLE"
        assert rows[0].total_tokens == 0


class TestMisc:
    async def test_stream_through_service(self) -> None:
        config = _local_config()
        provider = LocalMockProvider(config)
        service = AIContentService(provider=provider, config=config)
        stream = await service.stream(AIRequest(user_prompt="stream me"))
        chunks = [chunk async for chunk in stream]
        assert len("".join(chunks)) > 0

    async def test_health(self) -> None:
        config = _local_config()
        provider = LocalMockProvider(config)
        service = AIContentService(provider=provider, config=config)
        status = await service.health()
        assert status.healthy is True

    def test_estimate_tokens(self) -> None:
        config = _local_config()
        provider = LocalMockProvider(config)
        service = AIContentService(provider=provider, config=config)
        assert service.estimate_tokens("hello world") == 3

    def test_injected_cache_is_used(self) -> None:
        config = _config(cache_enabled=False)
        provider = FakeProvider(config, [_response()])
        cache = AIResponseCache(ttl=60, max_entries=10)
        service = AIContentService(provider=provider, config=config, cache=cache)
        assert service._cache is cache
