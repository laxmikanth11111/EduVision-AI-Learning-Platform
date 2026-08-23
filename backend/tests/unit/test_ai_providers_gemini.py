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
    AITruncationError,
)
from app.ai.models import AIRequest, AIResponseFormat, FinishReason
from app.ai.providers.gemini import GeminiProvider

_REQUEST = AIRequest(
    user_prompt="Explain gravity",
    system_prompt="You are a tutor.",
    request_id="req-1",
    correlation_id="corr-1",
)


def _config() -> AIProviderConfig:
    return AIProviderConfig(
        provider="gemini",
        api_key="test-key",
        model="gemini-1.5-flash",
        timeout_overall=5,
    )


def _provider(handler) -> GeminiProvider:
    provider = GeminiProvider(_config())
    provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return provider


class TestPayload:
    def test_build_payload_includes_system_and_generation(self) -> None:
        provider = GeminiProvider(_config())
        payload = provider._build_payload(_REQUEST)
        assert payload["systemInstruction"]["parts"][0]["text"] == "You are a tutor."
        assert payload["contents"] == [
            {"role": "user", "parts": [{"text": "Explain gravity"}]}
        ]
        assert "generationConfig" not in payload

    def test_build_payload_json_and_limits(self) -> None:
        provider = GeminiProvider(_config())
        request = _REQUEST.model_copy(
            update={
                "response_format": AIResponseFormat.JSON,
                "temperature": 0.5,
                "top_p": 0.8,
                "max_tokens": 100,
                "stop_sequences": ["END"],
            }
        )
        payload = provider._build_payload(request)
        generation = payload["generationConfig"]
        assert generation["temperature"] == 0.5
        assert generation["topP"] == 0.8
        assert generation["maxOutputTokens"] == 100
        assert generation["stopSequences"] == ["END"]
        assert generation["responseMimeType"] == "application/json"


class TestGenerate:
    async def test_success(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "candidates": [
                        {
                            "content": {"parts": [{"text": "Hello!"}]},
                            "finishReason": "STOP",
                        }
                    ],
                    "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
                    "modelVersion": "gemini-1.5-flash",
                },
            )

        provider = _provider(handler)
        response = await provider.generate(_REQUEST)
        await provider.close()
        assert response.text == "Hello!"
        assert response.finish_reason == FinishReason.STOP
        assert response.usage.input_tokens == 10
        assert response.usage.output_tokens == 5
        assert response.usage.total_tokens == 15
        assert response.request_id == "req-1"

    async def test_connect_error_translated(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom")

        provider = _provider(handler)
        with pytest.raises(AIProviderUnavailableError):
            await provider.generate(_REQUEST)
        await provider.close()

    async def test_candidate_blocked(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "candidates": [
                        {
                            "content": {"parts": [{"text": ""}]},
                            "finishReason": "SAFETY",
                        }
                    ],
                },
            )

        provider = _provider(handler)
        with pytest.raises(AIContentFilteredError):
            await provider.generate(_REQUEST)
        await provider.close()

    async def test_max_tokens_raises_truncation_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "candidates": [
                        {
                            "content": {
                                "parts": [{"text": '{"title": "unfinished'}],
                            },
                            "finishReason": "MAX_TOKENS",
                        }
                    ],
                    "usageMetadata": {
                        "promptTokenCount": 10,
                        "candidatesTokenCount": 1400,
                    },
                    "modelVersion": "gemini-1.5-flash",
                },
            )

        provider = _provider(handler)
        with pytest.raises(AITruncationError) as exc_info:
            await provider.generate(_REQUEST)
        await provider.close()
        assert exc_info.value.retryable is False
        assert exc_info.value.retry_recommended is True
        assert exc_info.value.internal_details["output_tokens"] == 1400

    async def test_non_json_body(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="<html>not json</html>")

        provider = _provider(handler)
        with pytest.raises(AIInvalidResponseError):
            await provider.generate(_REQUEST)
        await provider.close()


class TestErrorTranslation:
    @pytest.mark.parametrize(
        ("status", "body", "expected"),
        [
            (
                401,
                {"error": {"message": "API key not valid", "status": "PERMISSION_DENIED"}},
                AIAuthenticationFailedError,
            ),
            (404, {"error": {"message": "model not found"}}, AIInvalidConfigurationError),
            (
                429,
                {"error": {"message": "You have exceeded your quota", "status": "RESOURCE_EXHAUSTED"}},
                AIQuotaExceededError,
            ),
            (
                429,
                {"error": {"message": "rate limit", "status": "UNAVAILABLE"}},
                AIRateLimitExceededError,
            ),
            (500, {"error": {"message": "internal"}}, AIProviderUnavailableError),
        ],
    )
    async def test_status_mapping(self, status: int, body: dict, expected: type) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status, json=body)

        provider = _provider(handler)
        with pytest.raises(expected):
            await provider.generate(_REQUEST)
        await provider.close()

    async def test_rate_limit_carries_retry_after(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                429,
                json={"error": {"message": "rate limit", "status": "UNAVAILABLE"}},
                headers={"Retry-After": "7"},
            )

        provider = _provider(handler)
        with pytest.raises(AIRateLimitExceededError) as exc_info:
            await provider.generate(_REQUEST)
        assert exc_info.value.retry_after == 7
        await provider.close()

    async def test_content_blocked(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "candidates": [],
                    "promptFeedback": {"blockReason": "SAFETY"},
                },
            )

        provider = _provider(handler)
        with pytest.raises(AIContentFilteredError):
            await provider.generate(_REQUEST)
        await provider.close()


class TestStreaming:
    async def test_stream_joins_deltas(self) -> None:
        sse = (
            "data: {\"candidates\": [{\"content\": {\"parts\": [{\"text\": \"Hel\"}]}}]}\n\n"
            "data: {\"candidates\": [{\"content\": {\"parts\": [{\"text\": \"lo\"}]}}]}\n\n"
            "data: [DONE]\n\n"
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=sse)

        provider = _provider(handler)
        chunks = [chunk async for chunk in provider.stream(_REQUEST)]
        await provider.close()
        assert "".join(chunks) == "Hello"

    async def test_stream_error_translated(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": {"message": "bad key"}})

        provider = _provider(handler)

        async def _consume() -> None:
            async for chunk in provider.stream(_REQUEST):
                _ = chunk

        with pytest.raises(AIAuthenticationFailedError):
            await _consume()
        await provider.close()

    async def test_stream_cut_off_when_it_stalls_midway(self) -> None:
        class _StallingStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield (
                    b'data: {"candidates": [{"content": {"parts": [{"text": "Hel"}]}}]}\n\n'
                )
                await asyncio.sleep(30)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                stream=_StallingStream(),
            )

        config = _config().model_copy(update={"timeout_overall": 0.2})
        provider = GeminiProvider(config)
        provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        collected: list[str] = []

        async def _consume() -> None:
            async for chunk in provider.stream(_REQUEST):
                collected.append(chunk)

        try:
            with pytest.raises(AIGenerationTimeoutError):
                await _consume()
        finally:
            await provider.close()
        assert collected == ["Hel"]


class TestHealth:
    async def test_health_healthy(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={})

        provider = _provider(handler)
        status = await provider.health_check()
        await provider.close()
        assert status.healthy is True
        assert status.provider == "gemini"
