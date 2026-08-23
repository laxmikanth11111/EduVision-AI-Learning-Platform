"""AI provider interface.

Everything above this module depends only on ``AIProvider`` and the normalized
request/response models — never on a specific vendor SDK or wire format.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from app.ai.config import AIProviderConfig
from app.ai.errors import AIInvalidResponseError
from app.ai.models import AIRequest, AIResponse, TokenUsage
from app.ai.tokens import estimate_tokens


class AICapability:
    """Capability identifiers reported by providers (future-proof)."""

    CHAT = "chat"
    STREAMING = "streaming"
    JSON = "json"
    VISION = "vision"
    EMBEDDINGS = "embeddings"


class AIProviderInfo(BaseModel):
    """Static metadata describing a configured provider instance."""

    provider: str
    model: str
    description: str = ""
    supports_streaming: bool = False
    capabilities: set[str] = Field(default_factory=set)
    max_context_tokens: int = Field(default=100000, gt=0)
    max_output_tokens: int | None = None
    cost_per_1k_input: Decimal | None = None
    cost_per_1k_output: Decimal | None = None
    base_url: str | None = None
    requires_api_key: bool = True


class AIHealthStatus(BaseModel):
    """Result of a provider health probe."""

    healthy: bool
    provider: str
    model: str
    latency_ms: float = Field(default=0, ge=0)
    details: dict[str, Any] = Field(default_factory=dict)
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AIProvider(ABC):
    """Provider-agnostic contract implemented by every AI backend."""

    name: ClassVar[str] = ""
    requires_api_key: ClassVar[bool] = True

    def __init__(self, config: AIProviderConfig) -> None:
        self._config = config

    @abstractmethod
    async def generate(self, request: AIRequest) -> AIResponse:
        """Run a single generation attempt and return a normalized response."""
        raise NotImplementedError

    def stream(self, request: AIRequest) -> AsyncIterator[str]:
        """Stream response text deltas if the provider supports streaming."""
        info = self.info()
        if not info.supports_streaming:
            raise AIInvalidResponseError(
                message=f"Provider '{self.name}' does not support streaming",
                internal_details={"capabilities": sorted(info.capabilities)},
                provider=self.name,
                model=info.model,
            )
        raise NotImplementedError

    @abstractmethod
    async def health_check(self) -> AIHealthStatus:
        """Probe provider reachability/configuration without generating content."""
        raise NotImplementedError

    @abstractmethod
    def info(self) -> AIProviderInfo:
        """Return static provider metadata."""
        raise NotImplementedError

    def estimate_tokens(self, text: str) -> int:
        """Estimate tokens deterministically (used when the API omits usage)."""
        return estimate_tokens(text)

    def estimate_cost(self, usage: TokenUsage) -> Decimal | None:
        """Estimate cost from the provider info cost table (fallback)."""
        info = self.info()
        if info.cost_per_1k_input is None or info.cost_per_1k_output is None:
            return None
        input_cost = (Decimal(usage.input_tokens) / Decimal(1000)) * info.cost_per_1k_input
        output_cost = (Decimal(usage.output_tokens) / Decimal(1000)) * info.cost_per_1k_output
        return (input_cost + output_cost).quantize(Decimal("0.000001"))

    async def close(self) -> None:
        """Release any provider-held resources (HTTP clients, etc.)."""
        return None
