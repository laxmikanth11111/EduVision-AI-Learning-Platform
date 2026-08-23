"""Embedding provider interface.

Everything above this module depends only on ``EmbeddingProvider`` and the
normalized request/response models — never on a specific vendor SDK or wire
format.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.ai.embeddings.config import EmbeddingProviderConfig
from app.ai.embeddings.models import (
    EmbeddingHealthStatus,
    EmbeddingProviderInfo,
    EmbeddingResponse,
)
from app.ai.tokens import estimate_tokens


class EmbeddingProvider(ABC):
    """Provider-agnostic contract implemented by every embedding backend."""

    name: str = ""
    requires_api_key: bool = True
    default_model: str = ""
    default_dimension: int = 0

    def __init__(self, config: EmbeddingProviderConfig) -> None:
        self._config = config

    @property
    def config(self) -> EmbeddingProviderConfig:
        """Resolved configuration for this provider instance."""
        return self._config

    @property
    def model(self) -> str:
        return self._config.model or self.default_model

    @property
    def dimension(self) -> int:
        return self._config.dimension or self.default_dimension

    @abstractmethod
    async def embed(
        self,
        texts: list[str],
        *,
        request_id: str | None = None,
        correlation_id: str | None = None,
    ) -> EmbeddingResponse:
        """Embed a batch of texts and return a normalized response."""
        raise NotImplementedError

    @abstractmethod
    async def health_check(self) -> EmbeddingHealthStatus:
        """Probe provider reachability/configuration without embedding."""
        raise NotImplementedError

    @abstractmethod
    def info(self) -> EmbeddingProviderInfo:
        """Return static provider metadata."""
        raise NotImplementedError

    def estimate_tokens(self, text: str) -> int:
        """Estimate tokens deterministically (used when the API omits usage)."""
        return estimate_tokens(text)

    async def close(self) -> None:
        """Release any provider-held resources (HTTP clients, etc.)."""
        return None
