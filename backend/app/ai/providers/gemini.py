"""Google Gemini provider (REST via httpx).

Talks to the generative language REST API directly so the provider owns
authentication, request construction, response parsing, streaming, timeouts,
token accounting and error translation. Gemini-specific exceptions never
propagate upward — they become ``AIError`` subclasses.
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
    AITruncationError,
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
    "STOP": FinishReason.STOP,
    "MAX_TOKENS": FinishReason.LENGTH,
    "SAFETY": FinishReason.CONTENT_FILTER,
    "RECITATION": FinishReason.CONTENT_FILTER,
    "PROHIBITED_CONTENT": FinishReason.CONTENT_FILTER,
    "BLOCKLIST": FinishReason.CONTENT_FILTER,
    "SPII": FinishReason.CONTENT_FILTER,
    "IMAGE_SAFETY": FinishReason.CONTENT_FILTER,
    "MALFORMED_FUNCTION_CALL": FinishReason.ERROR,
    "OTHER": FinishReason.OTHER,
}

_BLOCKED_FINISH_REASONS = {
    "SAFETY",
    "RECITATION",
    "PROHIBITED_CONTENT",
    "BLOCKLIST",
    "SPII",
    "IMAGE_SAFETY",
}


@register_provider("gemini")
class GeminiProvider(HttpAIProvider):
    name = "gemini"
    requires_api_key = True
    default_model = "gemini-3.5-flash"
    default_base_url = "https://generativelanguage.googleapis.com/v1beta"
    description = "Google Gemini via the generative language REST API"

    def __init__(self, config: AIProviderConfig) -> None:
        super().__init__(config)
        if not config.api_key:
            raise AIInvalidConfigurationError(
                message="AI_API_KEY is required for the 'gemini' provider",
                details={"provider": self.name},
            )

    # ── Request construction ──────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key or "",
        }

    def _build_payload(self, request: AIRequest) -> dict[str, Any]:
        contents: list[dict[str, Any]] = []
        for message in request.effective_messages:
            if message.role == "system":
                continue
            role = "user" if message.role in {"user", "system"} else "model"
            contents.append({"role": role, "parts": [{"text": message.content}]})

        payload: dict[str, Any] = {"contents": contents}

        if request.system_prompt:
            payload["systemInstruction"] = {
                "parts": [{"text": request.system_prompt}]
            }

        generation: dict[str, Any] = {}
        if request.temperature is not None:
            generation["temperature"] = request.temperature
        if request.top_p is not None:
            generation["topP"] = request.top_p
        if request.max_tokens is not None:
            generation["maxOutputTokens"] = request.max_tokens
        if request.stop_sequences:
            generation["stopSequences"] = request.stop_sequences
        if request.response_format == AIResponseFormat.JSON:
            generation["responseMimeType"] = "application/json"
        if generation:
            payload["generationConfig"] = generation

        return payload

    # ── Generation ────────────────────────────────────────────────────────────

    async def generate(self, request: AIRequest) -> AIResponse:
        model = request.model_override or self.model
        url = f"{self.base_url}/models/{model}:generateContent"
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
                    message="Gemini returned a non-JSON response",
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
        candidates = data.get("candidates") or []
        prompt_feedback = data.get("promptFeedback") or {}

        if not candidates:
            if prompt_feedback.get("blockReason"):
                raise self._wrap_ai_error(
                    AIContentFilteredError(
                        message="Gemini blocked the request content",
                        internal_details={"block_reason": prompt_feedback.get("blockReason")},
                        provider=self.name,
                        model=model,
                        request_id=request.request_id,
                        correlation_id=request.correlation_id,
                    ),
                    request=request,
                )
            raise self._wrap_ai_error(
                AIInvalidResponseError(
                    message="Gemini returned no candidates",
                    internal_details={"candidates_count": 0},
                    provider=self.name,
                    model=model,
                    request_id=request.request_id,
                    correlation_id=request.correlation_id,
                ),
                request=request,
            )

        candidate = candidates[0]
        block_reason = candidate.get("blockReason")
        raw_finish = candidate.get("finishReason") or "OTHER"

        if block_reason or raw_finish in _BLOCKED_FINISH_REASONS:
            raise self._wrap_ai_error(
                AIContentFilteredError(
                    message="Gemini filtered the generated content",
                    internal_details={
                        "finish_reason": raw_finish,
                        "block_reason": block_reason,
                    },
                    provider=self.name,
                    model=model,
                    request_id=request.request_id,
                    correlation_id=request.correlation_id,
                ),
                request=request,
            )

        content = candidate.get("content") or {}
        parts = content.get("parts") or []
        text = "".join(part.get("text", "") for part in parts if isinstance(part, dict))

        usage_meta = data.get("usageMetadata") or {}
        input_tokens = int(usage_meta.get("promptTokenCount") or 0)
        output_tokens = int(usage_meta.get("candidatesTokenCount") or 0)
        if input_tokens == 0 and output_tokens == 0:
            input_tokens = self.estimate_tokens(
                request.system_prompt or ""
            ) + self.estimate_tokens(request.user_prompt)
            output_tokens = self.estimate_tokens(text)

        if raw_finish == "MAX_TOKENS":
            raise self._wrap_ai_error(
                AITruncationError(
                    message=(
                        "Gemini response was truncated because it reached the "
                        "maximum output token limit"
                    ),
                    internal_details={
                        "finish_reason": raw_finish,
                        "output_tokens": output_tokens,
                    },
                    provider=self.name,
                    model=model,
                    request_id=request.request_id,
                    correlation_id=request.correlation_id,
                ),
                request=request,
            )

        finish_reason = _FINISH_REASON_MAP.get(raw_finish, FinishReason.OTHER)
        resolved_model = data.get("modelVersion") or model

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
        provider_status = str(error.get("status") or "")
        retry_after = retry_after_seconds(response)
        context: dict[str, Any] = {
            "provider": self.name,
            "model": request.model_override or self.model,
            "request_id": request.request_id,
            "correlation_id": request.correlation_id,
        }

        if status in (401, 403) or "permission" in message.lower():
            return self._wrap_ai_error(
                AIAuthenticationFailedError(
                    message="Gemini authentication failed",
                    internal_details={"http_status": status, "message": message},
                    **context,
                ),
                request=request,
            )
        if status == 404:
            return self._wrap_ai_error(
                AIInvalidConfigurationError(
                    message="Gemini model or endpoint not found",
                    internal_details={"http_status": status, "message": message},
                    **context,
                ),
                request=request,
            )
        if status == 429 or provider_status == "RESOURCE_EXHAUSTED":
            if "quota" in message.lower() or provider_status == "RESOURCE_EXHAUSTED":
                return self._wrap_ai_error(
                    AIQuotaExceededError(
                        message="Gemini quota exceeded",
                        internal_details={"http_status": status, "message": message},
                        **context,
                    ),
                    request=request,
                )
            return self._wrap_ai_error(
                AIRateLimitExceededError(
                    message="Gemini rate limit exceeded",
                    internal_details={"http_status": status, "message": message},
                    retry_after=retry_after,
                    **context,
                ),
                request=request,
            )
        if status in (500, 502, 503, 504):
            return self._wrap_ai_error(
                AIProviderUnavailableError(
                    message="Gemini is temporarily unavailable",
                    internal_details={"http_status": status, "message": message},
                    **context,
                ),
                request=request,
            )
        return self._wrap_ai_error(
            AIInvalidResponseError(
                message="Gemini returned an unexpected error response",
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

        model = request.model_override or self.model
        url = f"{self.base_url}/models/{model}:streamGenerateContent"
        payload = self._build_payload(request)
        client = self._client_instance()

        try:
            async with asyncio.timeout(self._config.timeout_overall):
                async with client.stream(
                    "POST",
                    url,
                    json=payload,
                    headers=self._headers(),
                    params={"alt": "sse"},
                ) as response:
                    if response.status_code >= 400:
                        await response.aread()
                        raise self._parse_error_response(response, request)
                    async for event in iter_sse_events(response):
                        chunk = _extract_stream_text(event)
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
        url = f"{self.base_url}/models/{self.model}"
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


def _extract_stream_text(event: dict[str, Any]) -> str:
    candidates = event.get("candidates") or []
    if not candidates:
        return ""
    content = candidates[0].get("content") or {}
    parts = content.get("parts") or []
    return "".join(part.get("text", "") for part in parts if isinstance(part, dict))
