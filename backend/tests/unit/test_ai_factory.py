from __future__ import annotations

from unittest.mock import patch

import pytest

from app.ai.config import AIProviderConfig
from app.ai.errors import AIInvalidConfigurationError
from app.ai.factory import (
    close_ai_provider,
    create_ai_provider,
    get_ai_provider,
    reset_ai_provider,
    supported_providers,
)
from app.ai.providers.gemini import GeminiProvider
from app.ai.providers.local import LocalMockProvider
from app.ai.providers.openai import OpenAIProvider
from app.core.config import settings


class TestRegistration:
    def test_supported_providers(self) -> None:
        assert supported_providers() == ["gemini", "local", "openai"]

    def test_create_local_from_config(self) -> None:
        provider = create_ai_provider(config=AIProviderConfig(provider="local"))
        assert isinstance(provider, LocalMockProvider)

    def test_create_gemini_requires_key(self) -> None:
        with pytest.raises(AIInvalidConfigurationError):
            create_ai_provider(config=AIProviderConfig(provider="gemini"))

    def test_create_gemini_with_key(self) -> None:
        provider = create_ai_provider(
            config=AIProviderConfig(provider="gemini", api_key="test-key")
        )
        assert isinstance(provider, GeminiProvider)

    def test_create_openai_with_key(self) -> None:
        provider = create_ai_provider(
            config=AIProviderConfig(provider="openai", api_key="test-key")
        )
        assert isinstance(provider, OpenAIProvider)

    def test_unknown_provider_raises(self) -> None:
        with pytest.raises(AIInvalidConfigurationError):
            create_ai_provider(config=AIProviderConfig(provider="not-a-provider"))

    def test_empty_provider_raises(self) -> None:
        with pytest.raises(AIInvalidConfigurationError):
            create_ai_provider(config=AIProviderConfig(provider=""))


class TestSingleton:
    async def test_singleton_and_reset(self) -> None:
        reset_ai_provider()
        with patch.object(settings, "AI_PROVIDER", "local"):
            first = get_ai_provider()
            second = get_ai_provider()
            assert first is second
            reset_ai_provider()
            third = get_ai_provider()
            assert third is not first
            await close_ai_provider()
