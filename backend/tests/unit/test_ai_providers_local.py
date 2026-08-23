from __future__ import annotations

import json

import pytest

from app.ai.config import AIProviderConfig
from app.ai.models import AIRequest, AIResponseFormat, FinishReason
from app.ai.providers.local import LocalMockProvider

_config = AIProviderConfig(provider="local")


@pytest.fixture
def provider() -> LocalMockProvider:
    return LocalMockProvider(_config)


class TestLocalProviderGenerate:
    async def test_deterministic_text(self, provider: LocalMockProvider) -> None:
        first = await provider.generate(AIRequest(user_prompt="explain gravity"))
        second = await provider.generate(AIRequest(user_prompt="explain gravity"))
        assert first.text == second.text
        assert first.provider == "local"
        assert first.finish_reason == FinishReason.STOP
        assert first.usage.total_tokens > 0

    async def test_different_prompts_differ(self, provider: LocalMockProvider) -> None:
        a = await provider.generate(AIRequest(user_prompt="hello"))
        b = await provider.generate(AIRequest(user_prompt="world"))
        assert a.text != b.text

    async def test_json_format(self, provider: LocalMockProvider) -> None:
        response = await provider.generate(
            AIRequest(user_prompt="give me json", response_format=AIResponseFormat.JSON)
        )
        data = json.loads(response.text)
        assert data["ok"] is True
        assert data["provider"] == "local"


class TestLocalProviderStream:
    async def test_stream_returns_full_text(self, provider: LocalMockProvider) -> None:
        request = AIRequest(user_prompt="stream this")
        chunks = [chunk async for chunk in provider.stream(request)]
        joined = "".join(chunks)
        expected = await provider.generate(request)
        assert joined == expected.text
        assert len(chunks) > 0


class TestLocalProviderHealth:
    async def test_health_always_healthy(self, provider: LocalMockProvider) -> None:
        status = await provider.health_check()
        assert status.healthy is True
        assert status.provider == "local"
