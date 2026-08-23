"""Deterministic local mock provider.

Requires no API key and never calls an external service. Used for development,
integration testing, and as a safe fallback when no cloud provider is
configured. Output is deterministic for a given prompt, which makes tests
stable and the cache meaningful.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from app.ai.base import AICapability, AIHealthStatus, AIProvider, AIProviderInfo
from app.ai.config import AIProviderConfig
from app.ai.factory import register_provider
from app.ai.models import AIRequest, AIResponse, AIResponseFormat, FinishReason, TokenUsage

_CHUNK_SIZE = 32


@register_provider("local")
class LocalMockProvider(AIProvider):
    name = "local"
    requires_api_key = False
    default_model = "local-mock-1"

    def __init__(self, config: AIProviderConfig) -> None:
        self._config = config

    @property
    def model(self) -> str:
        return self._config.model or self.default_model

    def info(self) -> AIProviderInfo:
        return AIProviderInfo(
            provider=self.name,
            model=self.model,
            description="Deterministic local mock provider (no external calls)",
            supports_streaming=True,
            capabilities={AICapability.CHAT, AICapability.STREAMING, AICapability.JSON},
            max_context_tokens=self._config.max_input_tokens,
            max_output_tokens=self._config.max_tokens,
            requires_api_key=False,
        )

    async def generate(self, request: AIRequest) -> AIResponse:
        text = self._generate_text(request)
        input_tokens = self.estimate_tokens(
            request.system_prompt or ""
        ) + self.estimate_tokens(request.user_prompt)
        output_tokens = self.estimate_tokens(text)

        usage = TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            provider=self.name,
            model=self.model,
            finish_reason=FinishReason.STOP,
        )
        return AIResponse(
            text=text,
            finish_reason=FinishReason.STOP,
            usage=usage,
            provider=self.name,
            model=self.model,
            latency_ms=0.0,
            request_id=request.request_id or "",
            correlation_id=request.correlation_id,
        )

    async def stream(self, request: AIRequest) -> AsyncIterator[str]:
        text = self._generate_text(request)
        for index in range(0, len(text), _CHUNK_SIZE):
            yield text[index : index + _CHUNK_SIZE]

    async def health_check(self) -> AIHealthStatus:
        return AIHealthStatus(
            healthy=True,
            provider=self.name,
            model=self.model,
            latency_ms=0.0,
            checked_at=datetime.now(UTC),
        )

    async def close(self) -> None:
        return None

    def _generate_text(self, request: AIRequest) -> str:
        digest = hashlib.sha256(request.user_prompt.encode("utf-8")).hexdigest()[:12]
        if request.response_format == AIResponseFormat.JSON:
            return json.dumps(
                {
                    "ok": True,
                    "provider": self.name,
                    "model": self.model,
                    "digest": digest,
                    "prompt_length": len(request.user_prompt),
                },
                sort_keys=True,
            )
        return f"[local:{self.model}] deterministic response (digest={digest})"
