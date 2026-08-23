"""OpenAI embedding provider (REST via httpx).

Talks to the embeddings REST API directly. Owns authentication, request
construction, response parsing, token accounting and error translation.
OpenAI-specific exceptions never propagate upward — they become ``AIError``
subclasses.
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


@register_embedding_provider("openai")
class OpenAIEmbeddingProvider(HttpEmbeddingProvider):
    name = "openai"
    requires_api_key = True
    default_model = "text-embedding-3-small"
    default_base_url = "https://api.openai.com/v1"
    default_dimension = 1536
    description = "OpenAI text embeddings via the REST API"

    def __init__(self, config: EmbeddingProviderConfig) -> None:
        super().__init__(config)
        if not config.api_key:
            raise AIInvalidConfigurationError(
                message="AI_API_KEY is required for the 'openai' embedding provider",
                details={"provider": self.name},
            )

    # ── Request construction ──────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key or ''}",
        }

    # ── Embedding ─────────────────────────────────────────────────────────────

    async def _embed_impl(
        self,
        texts: list[str],
        *,
        request_id: str | None,
        correlation_id: str | None,
    ) -> EmbeddingResponse:
        url = f"{self.base_url}/embeddings"
        payload: dict[str, Any] = {"model": self.model, "input": texts}
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
                message="OpenAI returned a non-JSON embedding response",
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
        items = data.get("data") or []
        if not items:
            raise AIInvalidResponseError(
                message="OpenAI returned no embeddings",
                internal_details={"embeddings_count": 0},
                provider=self.name,
                model=self.model,
                request_id=request_id,
                correlation_id=correlation_id,
            )

        ordered = sorted(items, key=lambda item: int(item.get("index") or 0))
        vectors = [list(item.get("embedding") or []) for item in ordered]
        self._validate_vectors(vectors, request_id=request_id, correlation_id=correlation_id)

        usage = data.get("usage") or {}
        total_tokens = int(usage.get("total_tokens") or 0)
        if total_tokens == 0:
            total_tokens = sum(self.estimate_tokens(text) for text in texts)

        resolved_model = str(data.get("model") or self.model)
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

    def _validate_vectors(
        self,
        vectors: list[list[float]],
        *,
        request_id: str | None,
        correlation_id: str | None,
    ) -> None:
        if self.dimension and any(len(vector) != self.dimension for vector in vectors):
            raise AIInvalidResponseError(
                message="OpenAI returned embeddings with an unexpected dimension",
                internal_details={
                    "expected_dimension": self.dimension,
                    "actual_dimensions": sorted({len(v) for v in vectors}),
                },
                provider=self.name,
                model=self.model,
                request_id=request_id,
                correlation_id=correlation_id,
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
        error_type = str(error.get("type") or "")
        retry_after = retry_after_seconds(response)
        context: dict[str, Any] = {
            "provider": self.name,
            "model": self.model,
            "request_id": request_id,
            "correlation_id": correlation_id,
        }

        if status in (401, 403):
            return AIAuthenticationFailedError(
                message="OpenAI authentication failed",
                internal_details={"http_status": status, "message": message},
                **context,
            )
        if status == 404:
            return AIInvalidConfigurationError(
                message="OpenAI embedding model or endpoint not found",
                internal_details={"http_status": status, "message": message},
                **context,
            )
        if status == 429:
            lowered = message.lower() + " " + error_type.lower()
            if "quota" in lowered or "insufficient" in lowered:
                return AIQuotaExceededError(
                    message="OpenAI quota exceeded",
                    internal_details={"http_status": status, "message": message},
                    **context,
                )
            return AIRateLimitExceededError(
                message="OpenAI rate limit exceeded",
                internal_details={"http_status": status, "message": message},
                retry_after=retry_after,
                **context,
            )
        if status == 400:
            return AIInvalidConfigurationError(
                message="OpenAI rejected the embedding request parameters",
                internal_details={"http_status": status, "message": message},
                **context,
            )
        if status >= 500:
            return AIProviderUnavailableError(
                message="OpenAI is temporarily unavailable",
                internal_details={"http_status": status, "message": message},
                **context,
            )
        return AIInvalidResponseError(
            message="OpenAI returned an unexpected embedding error",
            internal_details={"http_status": status, "message": message},
            **context,
        )

    # ── Health ────────────────────────────────────────────────────────────────

    async def _ping(self) -> None:
        url = f"{self.base_url}/models"
        response = await fetch_json(
            self._client_instance(),
            url=url,
            config=self._config,
            headers=self._headers(),
        )
        if response.status_code >= 400:
            raise self._parse_error_response(response, request_id="health-check", correlation_id=None)
