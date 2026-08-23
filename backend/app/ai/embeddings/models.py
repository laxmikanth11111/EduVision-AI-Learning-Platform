"""Normalized embedding request / response models.

Every embedding provider accepts ``list[str]`` and returns an
``EmbeddingResponse`` using exactly this shape, so upper layers never perform
provider-specific parsing.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class EmbeddingResponse(BaseModel):
    """Normalized result of an embedding provider call (one vector per input)."""

    vectors: list[list[float]]
    dimension: int = Field(default=0, ge=0)
    tokens_used: int = Field(default=0, ge=0)
    provider: str
    model: str
    latency_ms: float = Field(default=0, ge=0)
    request_id: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, object] = Field(default_factory=dict)

    @property
    def success(self) -> bool:
        return len(self.vectors) > 0


class EmbeddingProviderInfo(BaseModel):
    """Static metadata describing a configured embedding provider instance."""

    provider: str
    model: str
    description: str = ""
    dimension: int = Field(default=0, ge=0)
    max_input_tokens: int = Field(default=8192, gt=0)
    max_batch_size: int = Field(default=32, gt=0)
    supports_batching: bool = True
    requires_api_key: bool = True


class EmbeddingHealthStatus(BaseModel):
    """Result of an embedding provider health probe."""

    healthy: bool
    provider: str
    model: str
    latency_ms: float = Field(default=0, ge=0)
    details: dict[str, object] = Field(default_factory=dict)
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
