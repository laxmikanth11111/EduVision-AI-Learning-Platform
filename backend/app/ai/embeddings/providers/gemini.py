"""Google Gemini embedding provider (REST via httpx).

Talks to the ``batchEmbedContents`` endpoint directly. Owns authentication,
request construction, response parsing, token accounting and error
translation. Gemini-specific exceptions never propagate upward — they become
``AIError`` subclasses.
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from app.ai.embeddings.config import EmbeddingProviderConfig
from app.ai.embeddings.factory import register_embedding_provider
from app.ai.embeddings.models import EmbeddingResponse
from app.ai.embeddings.providers._base import HttpEmbeddingProvider
from app.ai.embeddings.providers._http import fetch_json, retry_after_seconds
from app.ai.errors import (
    AIAuthenticationFailedError,
    AIError,
    AIInvalidConfigurationError,
    AIInvalidResponseError,
    AIProviderUnavailableError,
    AIQuotaExceededError,
    AIRateLimitExceededError,
)


@register_embedding_provider("gemini")
class GeminiEmbeddingProvider(HttpEmbeddingProvider):
    name = "gemini"
    requires_api_key = True
    default_model = "text-embedding-004"
    default_base_url = "https://generativelanguage.googleapis.com/v1beta"
    default_dimension = 768
    description = "Google Gemini via the generative language REST API"

    # Output dimensions are model-specific: text-embedding-004 yields 768 dims
    # while gemini-embedding-001/004 yield 3072 dims. Unknown models fall back
    # to ``default_dimension``.
    _MODEL_DIMENSIONS: dict[str, int] = {
        "text-embedding-004": 768,
        "gemini-embedding-001": 3072,
        "gemini-embedding-004": 3072,
    }

    def __init__(self, config: EmbeddingProviderConfig) -> None:
        super().__init__(config)
        if not config.api_key:
            raise AIInvalidConfigurationError(
                message="AI_API_KEY is required for the 'gemini' embedding provider",
                details={"provider": self.name},
            )

    @property
    def dimension(self) -> int:
        if self._config.dimension:
            return self._config.dimension
        return self._MODEL_DIMENSIONS.get(self.model, self.default_dimension)

    # ── Request construction ──────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key or "",
        }

    # ── Embedding ─────────────────────────────────────────────────────────────

    async def _embed_impl(
        self,
        texts: list[str],
        *,
        request_id: str | None,
        correlation_id: str | None,
    ) -> EmbeddingResponse:
        url = f"{self.base_url}/models/{self.model}:batchEmbedContents"
        requests = [
            {
                "model": f"models/{self.model}",
                "content": {"parts": [{"text": text}]},
            }
            for text in texts
        ]
        payload: dict[str, Any] = {"requests": requests}
        start = time.monotonic()

        response = await fetch_json(
            self._client_instance(),
            url=url,
            config=self._config,
            json_body=payload,
            headers=self._headers(),
        )
        latency_ms = (time.monotonic() - start) * 1000

        if response.status_code >= 400:
            raise self._parse_error_response(
                response,
                request_id=request_id,
                correlation_id=correlation_id,
            )

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise AIInvalidResponseError(
                message="Gemini returned a non-JSON embedding response",
                internal_details={"content_type": response.headers.get("content-type")},
                provider=self.name,
                model=self.model,
                request_id=request_id,
                correlation_id=correlation_id,
            ) from exc

        return self._parse_success(
            data,
            texts=texts,
            latency_ms=latency_ms,
            request_id=request_id,
            correlation_id=correlation_id,
        )

    # ── Response parsing ──────────────────────────────────────────────────────

    def _parse_success(
        self,
        data: dict[str, Any],
        *,
        texts: list[str],
        latency_ms: float,
        request_id: str | None,
        correlation_id: str | None,
    ) -> EmbeddingResponse:
        embeddings = data.get("embeddings") or []
        if not embeddings:
            raise AIInvalidResponseError(
                message="Gemini returned no embeddings",
                internal_details={"embeddings_count": 0},
                provider=self.name,
                model=self.model,
                request_id=request_id,
                correlation_id=correlation_id,
            )

        vectors = [list(embedding.get("values") or []) for embedding in embeddings]
        if self.dimension and any(len(vector) != self.dimension for vector in vectors):
            raise AIInvalidResponseError(
                message="Gemini returned embeddings with an unexpected dimension",
                internal_details={
                    "expected_dimension": self.dimension,
                    "actual_dimensions": sorted({len(v) for v in vectors}),
                },
                provider=self.name,
                model=self.model,
                request_id=request_id,
                correlation_id=correlation_id,
            )

        # Gemini batch endpoints do not return token usage; estimate locally.
        total_tokens = sum(self.estimate_tokens(text) for text in texts)
        resolved_model = str(data.get("modelVersion") or self.model)

        return EmbeddingResponse(
            vectors=vectors,
            dimension=self.dimension,
            tokens_used=total_tokens,
            provider=self.name,
            model=resolved_model,
            latency_ms=latency_ms,
            request_id=request_id or "",
            metadata={"correlation_id": correlation_id or ""},
        )

    # ── Error translation ─────────────────────────────────────────────────────

    def _parse_error_response(
        self,
        response: httpx.Response,
        *,
        request_id: str | None,
        correlation_id: str | None,
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
            "model": self.model,
            "request_id": request_id,
            "correlation_id": correlation_id,
        }

        if status in (401, 403) or "permission" in message.lower():
            return AIAuthenticationFailedError(
                message="Gemini authentication failed",
                internal_details={"http_status": status, "message": message},
                **context,
            )
        if status == 404:
            return AIInvalidConfigurationError(
                message="Gemini embedding model or endpoint not found",
                internal_details={"http_status": status, "message": message},
                **context,
            )
        if status == 429 or provider_status == "RESOURCE_EXHAUSTED":
            if "quota" in message.lower() or provider_status == "RESOURCE_EXHAUSTED":
                return AIQuotaExceededError(
                    message="Gemini quota exceeded",
                    internal_details={"http_status": status, "message": message},
                    **context,
                )
            return AIRateLimitExceededError(
                message="Gemini rate limit exceeded",
                internal_details={"http_status": status, "message": message},
                retry_after=retry_after,
                **context,
            )
        if status in (500, 502, 503, 504):
            return AIProviderUnavailableError(
                message="Gemini is temporarily unavailable",
                internal_details={"http_status": status, "message": message},
                **context,
            )
        return AIInvalidResponseError(
            message="Gemini returned an unexpected embedding error",
            internal_details={"http_status": status, "message": message},
            **context,
        )

    # ── Health ────────────────────────────────────────────────────────────────

    async def _ping(self) -> None:
        url = f"{self.base_url}/models/{self.model}"
        response = await fetch_json(
            self._client_instance(),
            url=url,
            config=self._config,
            headers=self._headers(),
        )
        if response.status_code >= 400:
            raise self._parse_error_response(
                response,
                request_id="health-check",
                correlation_id=None,
            )
