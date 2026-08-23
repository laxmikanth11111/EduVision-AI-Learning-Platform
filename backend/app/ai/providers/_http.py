"""Shared HTTP plumbing for REST-based AI providers.

Keeps timeout enforcement and streaming (SSE) parsing in one place so each
provider only deals with its own request/response wire format. Credentials are
never logged: headers and query strings are intentionally excluded from all
logging helpers here.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.ai.config import AIProviderConfig
from app.ai.errors import AIGenerationTimeoutError, AIProviderUnavailableError

DEFAULT_LIMITS = httpx.Limits(max_connections=50, max_keepalive_connections=20)


def build_http_client(config: AIProviderConfig) -> httpx.AsyncClient:
    """Build an ``AsyncClient`` enforcing connection and request timeouts."""
    timeout = httpx.Timeout(
        config.timeout_request,
        connect=config.timeout_connect,
        write=config.timeout_request,
        pool=config.timeout_connect,
    )
    return httpx.AsyncClient(timeout=timeout, limits=DEFAULT_LIMITS)


def overall_timeout(config: AIProviderConfig) -> float:
    return config.timeout_overall


async def fetch_json(
    client: httpx.AsyncClient,
    *,
    method: str,
    url: str,
    config: AIProviderConfig,
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
            method=method,
            url=url,
            json=json_body,
            headers=headers,
            params=params,
        ),
        timeout=config.timeout_overall,
    )


async def iter_sse_events(response: httpx.Response) -> AsyncIterator[dict[str, Any]]:
    """Iterate parsed ``data:`` payloads from an SSE response stream."""
    async for line in response.aiter_lines():
        stripped = line.strip()
        if not stripped.startswith("data:"):
            continue
        payload = stripped[len("data:") :].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            yield json.loads(payload)
        except json.JSONDecodeError:
            # Non-fatal trailing/partial frames are skipped.
            continue


def retry_after_seconds(response: httpx.Response) -> float | None:
    """Best-effort parse of a ``Retry-After`` header (seconds or HTTP date)."""
    value = response.headers.get("Retry-After")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def as_ai_provider_unavailable(
    exc: Exception,
    *,
    provider: str,
    model: str,
    request_id: str | None,
    correlation_id: str | None,
) -> AIProviderUnavailableError:
    """Translate an httpx connectivity failure into an application error."""
    return AIProviderUnavailableError(
        message="The AI provider could not be reached",
        internal_details={"error_type": type(exc).__name__},
        cause=exc,
        provider=provider,
        model=model,
        request_id=request_id,
        correlation_id=correlation_id,
    )


def as_generation_timeout(
    exc: Exception,
    *,
    provider: str,
    model: str,
    request_id: str | None,
    correlation_id: str | None,
) -> AIGenerationTimeoutError:
    return AIGenerationTimeoutError(
        message="AI generation timed out",
        internal_details={"error_type": type(exc).__name__},
        cause=exc,
        provider=provider,
        model=model,
        request_id=request_id,
        correlation_id=correlation_id,
    )
