from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from app.api.v1 import auth
from app.core.config import settings
from app.middleware.rate_limit import RateLimitMiddleware
from app.workers import redis_client

pytestmark = pytest.mark.asyncio


class _FakeRedis:
    def __init__(self) -> None:
        self.eval_args: list[tuple] = []
        self.calls: list[str] = []

    async def eval(self, script: str, numkeys: int, *args) -> list:  # noqa: A002
        self.calls.append("eval")
        self.eval_args.append(args)
        return [1, 0]

    async def zcount(self, key: str, min_: float, max_: float) -> int:  # noqa: A002
        self.calls.append("zcount")
        return 0


def _build_request(path: str = "/api/v1/health") -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "raw_path": path.encode(),
            "scheme": "http",
            "server": ("testserver", 80),
            "headers": [],
            "query_string": b"",
            "client": ("203.0.113.42", 43210),
        }
    )


async def _call_next(request: Request) -> PlainTextResponse:  # noqa: ARG001
    return PlainTextResponse("ok")


async def _make_middleware(window: int = 60, limit: int = 100) -> RateLimitMiddleware:
    return RateLimitMiddleware(
        app=Starlette(),
        default_limit=limit,
        default_window=window,
    )


async def test_sliding_window_sends_epoch_seconds_not_millis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeRedis()
    monkeypatch.setattr(
        "app.middleware.rate_limit.Redis",
        lambda **kwargs: fake,
    )
    middleware = await _make_middleware()
    now = time.time()
    await middleware._eval_sliding_window(fake, "ratelimit:p", 60, 100, now)

    assert fake.eval_args, "eval must be invoked"
    epoch_arg = fake.eval_args[0][3]
    assert isinstance(epoch_arg, int)
    assert 1_000_000_000 <= epoch_arg <= 99_999_999_999, (
        f"sliding window got {epoch_arg} — expected a seconds epoch, not millis"
    )


async def test_rate_limit_fails_open_then_reprobes_after_cooldown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.core.config.settings.RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr("app.middleware.rate_limit.settings.RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.RATE_LIMIT_REDIS_RECONNECT_SECONDS", 0)
    monkeypatch.setattr("app.middleware.rate_limit.settings.RATE_LIMIT_REDIS_RECONNECT_SECONDS", 0)

    fake = _FakeRedis()
    attempts: list[str] = []

    async def _pool_with_schedule() -> SimpleNamespace:
        if len(attempts) == 0:
            attempts.append("fail")
            raise ConnectionError("redis down")
        attempts.append("ok")
        return SimpleNamespace()

    monkeypatch.setattr("app.workers.redis_client.get_redis_pool", _pool_with_schedule)
    monkeypatch.setattr(
        "app.middleware.rate_limit.Redis",
        lambda **kwargs: fake,
    )

    monkeypatch.setattr(
        "app.middleware.rate_limit.RateLimitMiddleware._get_redis",
        RateLimitMiddleware._unpatched_get_redis,
    )

    middleware = await _make_middleware()

    first = await middleware.dispatch(_build_request(), _call_next)
    assert first.status_code == 200

    second = await middleware.dispatch(_build_request(), _call_next)
    assert second.status_code == 200

    assert attempts == ["fail", "ok"], (
        "limiter must re-probe Redis after the cooldown instead of failing open forever"
    )
    assert len(fake.calls) >= 1
    assert middleware._redis_available is True


async def test_health_ready_not_ready_when_redis_unavailable(
    client,
) -> None:
    from app.main import app
    from app.workers.redis_client import get_redis_client

    async def _fake_redis_down():
        m = AsyncMock()
        m.ping = AsyncMock(side_effect=ConnectionError("redis down"))
        yield m

    app.dependency_overrides[get_redis_client] = _fake_redis_down
    try:
        response = await client.get("/api/v1/health/ready")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "not_ready"
        assert body["checks"]["redis"]["status"] == "unhealthy"
    finally:
        app.dependency_overrides.pop(get_redis_client, None)


async def test_auth_revocation_falls_back_in_memory_when_redis_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _raise() -> AsyncMock:
        raise ConnectionError("redis down")

    monkeypatch.setattr(redis_client, "get_redis_pool", _raise)

    await auth._revoke_refresh_jti("jti-fallback-probe")
    assert await auth._is_refresh_jti_revoked("jti-fallback-probe") is True
    assert await auth._is_refresh_jti_revoked("jti-unrelated") is False


async def test_oauth_state_falls_back_in_memory_when_redis_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _raise() -> AsyncMock:
        raise ConnectionError("redis down")

    monkeypatch.setattr(redis_client, "get_redis_pool", _raise)

    await auth._store_oauth_state("state-fallback-probe")
    assert await auth._consume_oauth_state("state-fallback-probe") is True
    assert await auth._consume_oauth_state("state-fallback-probe") is False
