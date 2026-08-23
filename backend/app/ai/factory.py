"""AI provider factory.

Selection depends entirely on configuration — never hardcode a provider in
business code. New providers self-register via ``@register_provider``; the
factory lazily imports the provider package on first use.
"""

from __future__ import annotations

from collections.abc import Callable

from app.ai.base import AIProvider
from app.ai.config import AIProviderConfig, build_ai_provider_config
from app.ai.errors import AIInvalidConfigurationError

_PROVIDER_CLASSES: dict[str, type[AIProvider]] = {}

_singleton: AIProvider | None = None


def register_provider(name: str) -> Callable[[type[AIProvider]], type[AIProvider]]:
    """Class decorator registering an AI provider implementation."""

    def _decorator(cls: type[AIProvider]) -> type[AIProvider]:
        _PROVIDER_CLASSES[name] = cls
        return cls

    return _decorator


def _load_providers() -> None:
    if _PROVIDER_CLASSES:
        return
    # Importing the package executes the module-level registration decorators.
    from app.ai.providers import GeminiProvider, LocalMockProvider, OpenAIProvider  # noqa: F401

    _ = (LocalMockProvider, GeminiProvider, OpenAIProvider)


def supported_providers() -> list[str]:
    _load_providers()
    return sorted(_PROVIDER_CLASSES)


def create_ai_provider(
    provider: str | None = None,
    config: AIProviderConfig | None = None,
) -> AIProvider:
    """Instantiate a provider based on configuration.

    ``config`` wins when provided; otherwise a config is resolved from settings
    for ``provider`` (or the globally configured ``AI_PROVIDER``).
    """
    _load_providers()
    resolved_config = config or build_ai_provider_config(provider)
    name = resolved_config.provider

    if not name:
        raise AIInvalidConfigurationError(
            message="No AI provider configured (AI_PROVIDER is empty)",
            details={"supported": supported_providers()},
        )

    cls = _PROVIDER_CLASSES.get(name)
    if cls is None:
        raise AIInvalidConfigurationError(
            message=f"Unknown AI provider: {name}",
            details={"provider": name, "supported": supported_providers()},
        )

    return cls(resolved_config)


def get_ai_provider() -> AIProvider:
    """Return the process-wide configured provider singleton."""
    global _singleton
    if _singleton is None:
        _singleton = create_ai_provider()
    return _singleton


async def close_ai_provider() -> None:
    global _singleton
    if _singleton is not None:
        await _singleton.close()
        _singleton = None


def reset_ai_provider() -> None:
    """Drop the cached singleton (used by tests and reconfiguration)."""
    global _singleton
    _singleton = None
