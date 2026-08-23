"""Deterministic local mock embedding provider.

Requires no API key and never calls an external service. Vectors are derived
deterministically from the input text via sha256, so identical text always
produces identical vectors — making tests stable and the embedding cache
meaningful.
"""

from __future__ import annotations

import hashlib
import time

from app.ai.embeddings.base import EmbeddingProvider
from app.ai.embeddings.config import EmbeddingProviderConfig
from app.ai.embeddings.factory import register_embedding_provider
from app.ai.embeddings.models import (
    EmbeddingHealthStatus,
    EmbeddingProviderInfo,
    EmbeddingResponse,
)


@register_embedding_provider("local")
class LocalEmbeddingProvider(EmbeddingProvider):
    name = "local"
    requires_api_key = False
    default_model = "local-embedding-1"
    default_dimension = 384

    def __init__(self, config: EmbeddingProviderConfig) -> None:
        super().__init__(config)
        if config.dimension:
            self._dimension = config.dimension
        else:
            self._dimension = self.default_dimension

    def info(self) -> EmbeddingProviderInfo:
        return EmbeddingProviderInfo(
            provider=self.name,
            model=self.model,
            description="Deterministic local mock embedding provider (no external calls)",
            dimension=self._dimension,
            max_input_tokens=self._config.max_input_tokens,
            max_batch_size=self._config.max_batch_size,
            requires_api_key=False,
        )

    async def embed(
        self,
        texts: list[str],
        *,
        request_id: str | None = None,
        correlation_id: str | None = None,
    ) -> EmbeddingResponse:
        start = time.monotonic()
        vectors = [self._vector(text) for text in texts]
        tokens = sum(self.estimate_tokens(text) for text in texts)
        return EmbeddingResponse(
            vectors=vectors,
            dimension=self._dimension,
            tokens_used=tokens,
            provider=self.name,
            model=self.model,
            latency_ms=(time.monotonic() - start) * 1000,
            request_id=request_id or "",
            metadata={"correlation_id": correlation_id or ""},
        )

    async def health_check(self) -> EmbeddingHealthStatus:
        return EmbeddingHealthStatus(
            healthy=True,
            provider=self.name,
            model=self.model,
            latency_ms=0.0,
            details={"dimension": self._dimension},
        )

    async def close(self) -> None:
        return None

    def _vector(self, text: str) -> list[float]:
        dimension = self._dimension
        if not text:
            return [0.0] * dimension
        seed = hashlib.sha256(text.encode("utf-8")).digest()
        values: list[float] = []
        block_index = 0
        while len(values) < dimension:
            block = hashlib.sha256(seed + block_index.to_bytes(4, "little")).digest()
            values.extend(byte / 255.0 for byte in block)
            block_index += 1
        return values[:dimension]
