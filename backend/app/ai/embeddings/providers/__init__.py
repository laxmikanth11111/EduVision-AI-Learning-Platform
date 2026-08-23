"""Embedding provider implementations.

Importing this package executes the module-level ``@register_embedding_provider``
decorators, making the providers discoverable by the factory.
"""

from app.ai.embeddings.providers.gemini import GeminiEmbeddingProvider
from app.ai.embeddings.providers.local import LocalEmbeddingProvider
from app.ai.embeddings.providers.openai import OpenAIEmbeddingProvider

__all__ = ["GeminiEmbeddingProvider", "LocalEmbeddingProvider", "OpenAIEmbeddingProvider"]
