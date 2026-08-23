"""Provider implementations.

Importing this package executes the ``@register_provider`` decorators so the
factory can resolve provider classes by name.
"""

from app.ai.providers.gemini import GeminiProvider
from app.ai.providers.local import LocalMockProvider
from app.ai.providers.openai import OpenAIProvider

__all__ = ["GeminiProvider", "LocalMockProvider", "OpenAIProvider"]
