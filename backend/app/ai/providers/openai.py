"""OpenAI provider (chat completions REST API via httpx).

Owns authentication, request construction, response parsing, streaming,
timeouts, token accounting and error translation. OpenAI-specific exceptions
never propagate upward.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.ai.config import AIProviderConfig
from app.ai.cost import estimate_cost
from app.ai.errors import (
    AIAuthenticationFailedError,
    AIContentFilteredError,
    AIError,
    AIInvalidConfigurationError,
    AIInvalidResponseError,
    AIProviderUnavailableError,
    AIQuotaExceededError,
    AIRateLimitExceededError,
)
from app.ai.factory import register_provider
from app.ai.models import (
    AIRequest,
    AIResponse,
    AIResponseFormat,
    FinishReason,
    TokenUsage,
)
from app.ai.providers._base import HttpAIProvider
from app.ai.providers._http import fetch_json, iter_sse_events, retry_after_seconds

_FINISH_REASON_MAP: dict[str, FinishReason] = {
    "stop": FinishReason.STOP,
    "length": FinishReason.LENGTH,
    "content_filter": FinishReason.CONTENT_FILTER,
    "tool_calls": FinishReason.OTHER,
    "function_call": FinishReason.OTHER,
}


@register_provider("openai")
class OpenAIProvider(HttpAIProvider):
    name = "openai"
    requires_api_key = True
    default_model = "gpt-4o-mini"
    default_base_url = "https://api.openai.com/v1"
    description = "OpenAI chat completions via the REST API"

    def __init__(self, config: AIProviderConfig) -> None:
        super().__init__(config)
        if not config.api_key:
            raise AIInvalidConfigurationError(
                message="AI_API_KEY is required for the 'openai' provider",
                details={"provider": self.name},
            )

    # ── Request construction ──────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key or ''}",
        }

    def _build_payload(self, request: AIRequest) -> dict[str, Any]:
        model = request.model_override or self.model
        payload: dict[str, Any] = {
            "model": model,
            "messages": [message.model_dump() for message in request.effective_messages],
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.top_p is not None:
            payload["top_p"] = request.top_p
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.stop_sequences:
            payload["stop"] = request.stop_sequences
        if request.response_format == AIResponseFormat.JSON:
            payload["response_format"] = {"type": "json_object"}
        return payload

    # ── Generation ────────────────────────────────────────────────────────────

    async def generate(self, request: AIRequest) -> AIResponse:
        model = request.model_override or self.model
        url = f"{self.base_url}/chat/completions"
        payload = self._build_payload(request)
        start = time.monotonic()

        try:
            response = await fetch_json(
                self._client_instance(),
                method="POST",
                url=url,
                config=self._config,
                json_body=payload,
                headers=self._headers(),
            )
        except Exception as exc:
            error = self._translate_transport_error(
                exc,
                request_id=request.request_id,
                correlation_id=request.correlation_id,
            )
            raise self._wrap_ai_error(error, request=request) from exc

        latency_ms = (time.monotonic() - start) * 1000

        if response.status_code >= 400:
            raise self._parse_error_response(response, request)

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise self._wrap_ai_error(
                AIInvalidResponseError(
                    message="OpenAI returned a non-JSON response",
                    internal_details={"content_type": response.headers.get("content-type")},
                    provider=self.name,
                    model=model,
                    request_id=request.request_id,
                    correlation_id=request.correlation_id,
                ),
                request=request,
            ) from exc

        return self._parse_success(
            data,
            request=request,
            model=model,
            latency_ms=latency_ms,
        )

    # ── Response parsing ──────────────────────────────────────────────────────

    def _parse_success(
        self,
        data: dict[str, Any],
        *,
        request: AIRequest,
        model: str,
        latency_ms: float,
    ) -> AIResponse:
        choices = data.get("choices") or []
        if not choices:
            raise self._wrap_ai_error(
                AIInvalidResponseError(
                    message="OpenAI returned no choices",
                    internal_details={"choices_count": 0},
                    provider=self.name,
                    model=model,
                    request_id=request.request_id,
                    correlation_id=request.correlation_id,
                ),
                request=request,
            )

        choice = choices[0]
        raw_finish = str(choice.get("finish_reason") or "stop")

        if raw_finish == "content_filter":
            raise self._wrap_ai_error(
                AIContentFilteredError(
                    message="OpenAI filtered the generated content",
                    internal_details={"finish_reason": raw_finish},
                    provider=self.name,
                    model=model,
                    request_id=request.request_id,
                    correlation_id=request.correlation_id,
                ),
                request=request,
            )

        message = choice.get("message") or {}
        text = str(message.get("content") or "")

        usage_data = data.get("usage") or {}
        input_tokens = int(usage_data.get("prompt_tokens") or 0)
        output_tokens = int(usage_data.get("completion_tokens") or 0)
        if input_tokens == 0 and output_tokens == 0:
            input_tokens = self.estimate_tokens(
                request.system_prompt or ""
            ) + self.estimate_tokens(request.user_prompt)
            output_tokens = self.estimate_tokens(text)

        finish_reason = _FINISH_REASON_MAP.get(raw_finish, FinishReason.OTHER)
        resolved_model = str(data.get("model") or model)

        usage = TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost=estimate_cost(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=resolved_model,
            ),
            provider=self.name,
            model=resolved_model,
            latency_ms=latency_ms,
            finish_reason=finish_reason,
        )

        return AIResponse(
            text=text,
            finish_reason=finish_reason,
            usage=usage,
            provider=self.name,
            model=resolved_model,
            latency_ms=latency_ms,
            request_id=request.request_id or "",
            correlation_id=request.correlation_id,
        )

    # ── Error translation ─────────────────────────────────────────────────────

    def _parse_error_response(
        self,
        response: httpx.Response,
        request: AIRequest,
    ) -> AIError:
        try:
            body = response.json()
        except json.JSONDecodeError:
            body = {}
        error = body.get("error") or {}
        status = response.status_code
        message = str(error.get("message") or "")
        error_type = str(error.get("type") or "")
        retry_after = retry_after_seconds(response)
        context: dict[str, Any] = {
            "provider": self.name,
            "model": request.model_override or self.model,
            "request_id": request.request_id,
            "correlation_id": request.correlation_id,
        }

        if status in (401, 403):
            return self._wrap_ai_error(
                AIAuthenticationFailedError(
                    message="OpenAI authentication failed",
                    internal_details={"http_status": status, "message": message},
                    **context,
                ),
                request=request,
            )
        if status == 404:
            return self._wrap_ai_error(
                AIInvalidConfigurationError(
                    message="OpenAI model or endpoint not found",
                    internal_details={"http_status": status, "message": message},
                    **context,
                ),
                request=request,
            )
        if status == 429:
            lowered = message.lower() + " " + error_type.lower()
            if "quota" in lowered or "insufficient" in lowered:
                return self._wrap_ai_error(
                    AIQuotaExceededError(
                        message="OpenAI quota exceeded",
                        internal_details={"http_status": status, "message": message},
                        **context,
                    ),
                    request=request,
                )
            return self._wrap_ai_error(
                AIRateLimitExceededError(
                    message="OpenAI rate limit exceeded",
                    internal_details={"http_status": status, "message": message},
                    retry_after=retry_after,
                    **context,
                ),
                request=request,
            )
        if status == 400:
            lowered = message.lower()
            if any(word in lowered for word in ("policy", "safety", "filter")):
                return self._wrap_ai_error(
                    AIContentFilteredError(
                        message="OpenAI filtered the request content",
                        internal_details={"http_status": status, "message": message},
                        **context,
                    ),
                    request=request,
                )
            return self._wrap_ai_error(
                AIInvalidConfigurationError(
                    message="OpenAI rejected the request parameters",
                    internal_details={"http_status": status, "message": message},
                    **context,
                ),
                request=request,
            )
        if status >= 500:
            return self._wrap_ai_error(
                AIProviderUnavailableError(
                    message="OpenAI is temporarily unavailable",
                    internal_details={"http_status": status, "message": message},
                    **context,
                ),
                request=request,
            )
        return self._wrap_ai_error(
            AIInvalidResponseError(
                message="OpenAI returned an unexpected error response",
                internal_details={"http_status": status, "message": message},
                **context,
            ),
            request=request,
        )

    # ── Streaming ─────────────────────────────────────────────────────────────

    async def stream(self, request: AIRequest) -> AsyncIterator[str]:
        if not self._config.streaming_enabled:
            raise self._wrap_ai_error(
                AIInvalidResponseError(
                    message="Streaming is disabled by configuration",
                    provider=self.name,
                ),
                request=request,
            )

        url = f"{self.base_url}/chat/completions"
        payload = self._build_payload(request)
        payload["stream"] = True
        client = self._client_instance()

        try:
            async with asyncio.timeout(self._config.timeout_overall):
                async with client.stream(
                    "POST",
                    url,
                    json=payload,
                    headers=self._headers(),
                ) as response:
                    if response.status_code >= 400:
                        await response.aread()
                        raise self._parse_error_response(response, request)
                    async for event in iter_sse_events(response):
                        choices = event.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta") or {}
                        chunk = delta.get("content")
                        if chunk:
                            yield chunk
        except asyncio.CancelledError:
            raise
        except AIError:
            raise
        except Exception as exc:
            error = self._translate_transport_error(
                exc,
                request_id=request.request_id,
                correlation_id=request.correlation_id,
            )
            raise self._wrap_ai_error(error, request=request) from exc

    # ── Health ────────────────────────────────────────────────────────────────

    async def _ping(self) -> None:
        url = f"{self.base_url}/models"
        response = await fetch_json(
            self._client_instance(),
            method="GET",
            url=url,
            config=self._config,
            headers=self._headers(),
        )
        if response.status_code >= 400:
            raise self._parse_error_response(response, self._empty_request())

    @staticmethod
    def _empty_request() -> AIRequest:
        return AIRequest(user_prompt="health-check", request_id="health-check")
