from __future__ import annotations

import asyncio

import httpx
import pytest

from app.ai.config import AIProviderConfig
from app.ai.errors import (
    AIAuthenticationFailedError,
    AIContentFilteredError,
    AIGenerationTimeoutError,
    AIInvalidConfigurationError,
    AIInvalidResponseError,
    AIProviderUnavailableError,
    AIQuotaExceededError,
    AIRateLimitExceededError,
)
from app.ai.models import AIRequest, AIResponseFormat, FinishReason
from app.ai.providers.openai import OpenAIProvider

_REQUEST = AIRequest(
    user_prompt="Explain gravity",
    system_prompt="You are a tutor.",
    request_id="req-1",
    correlation_id="corr-1",
)


def _config() -> AIProviderConfig:
    return AIProviderConfig(
        provider="openai",
        api_key="test-key",
        model="gpt-4o-mini",
        timeout_overall=5,
    )


def _provider(handler) -> OpenAIProvider:
    provider = OpenAIProvider(_config())
    provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return provider


class TestPayload:
    def test_build_payload_includes_messages(self) -> None:
        provider = OpenAIProvider(_config())
        payload = provider._build_payload(_REQUEST)
        assert payload["model"] == "gpt-4o-mini"
        assert payload["messages"] == [
            {"role": "system", "content": "You are a tutor."},
            {"role": "user", "content": "Explain gravity"},
        ]

    def test_build_payload_json(self) -> None:
        provider = OpenAIProvider(_config())
        request = _REQUEST.model_copy(update={"response_format": AIResponseFormat.JSON})
        payload = provider._build_payload(request)
        assert payload["response_format"] == {"type": "json_object"}


class TestGenerate:
    async def test_success(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"content": "Hi there"}, "finish_reason": "stop"}
                    ],
                    "usage": {"prompt_tokens": 7, "completion_tokens": 2},
                    "model": "gpt-4o-mini",
                },
            )

        provider = _provider(handler)
        response = await provider.generate(_REQUEST)
        await provider.close()
        assert response.text == "Hi there"
        assert response.finish_reason == FinishReason.STOP
        assert response.usage.input_tokens == 7
        assert response.usage.output_tokens == 2
        assert response.usage.total_tokens == 9
        assert response.request_id == "req-1"

    async def test_content_filtered(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"content": ""}, "finish_reason": "content_filter"}
                    ]
                },
            )

        provider = _provider(handler)
        with pytest.raises(AIContentFilteredError):
            await provider.generate(_REQUEST)
        await provider.close()

    async def test_no_choices(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"choices": []})

        provider = _provider(handler)
        with pytest.raises(AIInvalidResponseError):
            await provider.generate(_REQUEST)
        await provider.close()


class TestErrorTranslation:
    @pytest.mark.parametrize(
        ("status", "body", "expected"),
        [
            (401, {"error": {"message": "bad key"}}, AIAuthenticationFailedError),
            (404, {"error": {"message": "model missing"}}, AIInvalidConfigurationError),
            (
                429,
                {"error": {"message": "You exceeded your current quota", "type": "insufficient_quota"}},
                AIQuotaExceededError,
            ),
            (
                429,
                {"error": {"message": "rate limit reached", "type": "requests"}},
                AIRateLimitExceededError,
            ),
            (
                400,
                {"error": {"message": "safety policy violation", "type": "invalid_request_error"}},
                AIContentFilteredError,
            ),
            (400, {"error": {"message": "bad params", "type": "invalid_request_error"}}, AIInvalidConfigurationError),
            (500, {"error": {"message": "server error"}}, AIProviderUnavailableError),
        ],
    )
    async def test_status_mapping(self, status: int, body: dict, expected: type) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status, json=body)

        provider = _provider(handler)
        with pytest.raises(expected):
            await provider.generate(_REQUEST)
        await provider.close()


class TestStreaming:
    async def test_stream_joins_deltas(self) -> None:
        sse = (
            "data: {\"choices\": [{\"delta\": {\"content\": \"Hi\"}}]}\n\n"
            "data: {\"choices\": [{\"delta\": {\"content\": \" there\"}}]}\n\n"
            "data: {\"choices\": [{\"delta\": {}}]}\n\n"
            "data: [DONE]\n\n"
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=sse)

        provider = _provider(handler)
        chunks = [chunk async for chunk in provider.stream(_REQUEST)]
        await provider.close()
        assert "".join(chunks) == "Hi there"

    async def test_stream_cut_off_when_it_stalls_midway(self) -> None:
        class _StallingStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b'data: {"choices": [{"delta": {"content": "Hi"}}]}\n\n'
                await asyncio.sleep(30)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                stream=_StallingStream(),
            )

        config = _config().model_copy(update={"timeout_overall": 0.2})
        provider = OpenAIProvider(config)
        provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        collected: list[str] = []

        async def _consume_stream() -> None:
            async for chunk in provider.stream(_REQUEST):
                collected.append(chunk)

        try:
            with pytest.raises(AIGenerationTimeoutError):
                await _consume_stream()
        finally:
            await provider.close()
        assert collected == ["Hi"]


class TestHealth:
    async def test_health_healthy(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": []})

        provider = _provider(handler)
        status = await provider.health_check()
        await provider.close()
        assert status.healthy is True
        assert status.provider == "openai"
