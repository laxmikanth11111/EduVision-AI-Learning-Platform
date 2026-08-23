"""Embedding provider factory.

Selection depends entirely on configuration — never hardcode a provider in
business code. New providers self-register via ``@register_embedding_provider``;
the factory lazily imports the provider package on first use.
"""

from __future__ import annotations

from collections.abc import Callable

from app.ai.embeddings.base import EmbeddingProvider
from app.ai.embeddings.config import EmbeddingProviderConfig, build_embedding_provider_config
from app.ai.errors import AIInvalidConfigurationError

_EMBEDDING_PROVIDER_CLASSES: dict[str, type[EmbeddingProvider]] = {}

_singleton: EmbeddingProvider | None = None


def register_embedding_provider(
    name: str,
) -> Callable[[type[EmbeddingProvider]], type[EmbeddingProvider]]:
    """Class decorator registering an embedding provider implementation."""

    def _decorator(cls: type[EmbeddingProvider]) -> type[EmbeddingProvider]:
        _EMBEDDING_PROVIDER_CLASSES[name] = cls
        return cls

    return _decorator


def _load_embedding_providers() -> None:
    if _EMBEDDING_PROVIDER_CLASSES:
        return
    # Importing the package executes the module-level registration decorators.
    from app.ai.embeddings.providers import (  # noqa: F401
        GeminiEmbeddingProvider,
        LocalEmbeddingProvider,
        OpenAIEmbeddingProvider,
    )

    _ = (LocalEmbeddingProvider, OpenAIEmbeddingProvider, GeminiEmbeddingProvider)


def supported_embedding_providers() -> list[str]:
    _load_embedding_providers()
    return sorted(_EMBEDDING_PROVIDER_CLASSES)


def create_embedding_provider(
    provider: str | None = None,
    config: EmbeddingProviderConfig | None = None,
) -> EmbeddingProvider:
    """Instantiate an embedding provider based on configuration.

    ``config`` wins when provided; otherwise a config is resolved from settings
    for ``provider`` (or the globally configured ``EMBEDDING_PROVIDER`` / chat
    ``AI_PROVIDER``).
    """
    _load_embedding_providers()
    resolved_config = config or build_embedding_provider_config(provider)
    name = resolved_config.provider

    if not name:
        raise AIInvalidConfigurationError(
            message="No embedding provider configured (EMBEDDING_PROVIDER/AI_PROVIDER empty)",
            details={"supported": supported_embedding_providers()},
        )

    cls = _EMBEDDING_PROVIDER_CLASSES.get(name)
    if cls is None:
        raise AIInvalidConfigurationError(
            message=f"Unknown embedding provider: {name}",
            details={"provider": name, "supported": supported_embedding_providers()},
        )

    return cls(resolved_config)


def get_embedding_provider() -> EmbeddingProvider:
    """Return the process-wide configured embedding provider singleton."""
    global _singleton
    if _singleton is None:
        _singleton = create_embedding_provider()
    return _singleton


async def close_embedding_provider() -> None:
    global _singleton
    if _singleton is not None:
        await _singleton.close()
        _singleton = None


def reset_embedding_provider() -> None:
    """Drop the cached singleton (used by tests and reconfiguration)."""
    global _singleton
    _singleton = None
