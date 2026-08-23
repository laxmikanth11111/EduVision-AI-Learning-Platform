"""Shared HTTP plumbing for REST-based embedding providers.

Keeps timeout enforcement and transport-error translation in one place so each
provider only deals with its own wire format. Credentials are never logged:
headers and query strings are intentionally excluded from all helpers here.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.ai.embeddings.config import EmbeddingProviderConfig
from app.ai.errors import AIGenerationTimeoutError, AIProviderUnavailableError

_DEFAULT_LIMITS = httpx.Limits(max_connections=50, max_keepalive_connections=20)


def build_http_client(config: EmbeddingProviderConfig) -> httpx.AsyncClient:
    """Build an ``AsyncClient`` enforcing connection and request timeouts."""
    timeout = httpx.Timeout(
        config.timeout_request,
        connect=config.timeout_connect,
        write=config.timeout_request,
        pool=config.timeout_connect,
    )
    return httpx.AsyncClient(timeout=timeout, limits=_DEFAULT_LIMITS)


async def fetch_json(
    client: httpx.AsyncClient,
    *,
    url: str,
    config: EmbeddingProviderConfig,
    json_body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
) -> httpx.Response:
    """Issue a request bounded by the overall timeout.

    Connectivity/timeout exceptions bubble up as raw httpx errors so providers
    can translate them with their own context.
    """
    return await asyncio.wait_for(
        client.request(
            method="POST",
            url=url,
            json=json_body,
            headers=headers,
            params=params,
        ),
        timeout=config.timeout_overall,
    )


def retry_after_seconds(response: httpx.Response) -> float | None:
    """Best-effort parse of a ``Retry-After`` header (seconds or HTTP date)."""
    value = response.headers.get("Retry-After")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def as_embedding_unavailable(
    exc: Exception,
    *,
    provider: str,
    model: str,
    request_id: str | None,
    correlation_id: str | None,
) -> AIProviderUnavailableError:
    """Translate an httpx connectivity failure into an application error."""
    return AIProviderUnavailableError(
        message="The embedding provider could not be reached",
        internal_details={"error_type": type(exc).__name__},
        cause=exc,
        provider=provider,
        model=model,
        request_id=request_id,
        correlation_id=correlation_id,
    )


def as_embedding_timeout(
    exc: Exception,
    *,
    provider: str,
    model: str,
    request_id: str | None,
    correlation_id: str | None,
) -> AIGenerationTimeoutError:
    return AIGenerationTimeoutError(
        message="Embedding request timed out",
        internal_details={"error_type": type(exc).__name__},
        cause=exc,
        provider=provider,
        model=model,
        request_id=request_id,
        correlation_id=correlation_id,
    )
