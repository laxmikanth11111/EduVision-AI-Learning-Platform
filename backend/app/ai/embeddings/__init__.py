"""Embedding pipeline package (Phase 4E.2).

Provides the provider-agnostic ``EmbeddingProvider`` abstraction, a
configuration-driven factory, and normalized models. Business services live in
``app.services``.
"""

from app.ai.embeddings.base import EmbeddingProvider
from app.ai.embeddings.config import (
    EmbeddingProviderConfig,
    build_embedding_provider_config,
)
from app.ai.embeddings.factory import (
    create_embedding_provider,
    get_embedding_provider,
    register_embedding_provider,
    reset_embedding_provider,
    supported_embedding_providers,
)
from app.ai.embeddings.models import (
    EmbeddingHealthStatus,
    EmbeddingProviderInfo,
    EmbeddingResponse,
)

__all__ = [
    "EmbeddingHealthStatus",
    "EmbeddingProvider",
    "EmbeddingProviderConfig",
    "EmbeddingProviderInfo",
    "EmbeddingResponse",
    "build_embedding_provider_config",
    "create_embedding_provider",
    "get_embedding_provider",
    "register_embedding_provider",
    "reset_embedding_provider",
    "supported_embedding_providers",
]
