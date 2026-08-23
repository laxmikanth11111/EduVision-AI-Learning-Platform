from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

RATE_LIMIT_TEST_CLIENT = ("203.0.113.10", 12345)


@pytest_asyncio.fixture
async def rate_limited_client(setup_database: None) -> AsyncGenerator[AsyncClient]:
    """ASGI client originating from a non-whitelisted IP.

    Local/dev configuration whitelists loopback addresses
    (``RATE_LIMIT_WHITELIST=127.0.0.1,::1,localhost``), so requests made with
    the default ASGI transport (client ``127.0.0.1``) bypass the limiter before
    any Redis interaction. These tests must exercise the limiter itself, so
    they send traffic from a documentation-reserved IP instead.
    """
    from app.main import app

    transport = ASGITransport(app=app, client=RATE_LIMIT_TEST_CLIENT)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        follow_redirects=True,
    ) as async_client:
        yield async_client


class TestRateLimitHeaders:
    async def test_rate_limit_headers_present(
        self, mock_redis: AsyncMock, rate_limited_client: AsyncClient
    ) -> None:
        mock_redis.eval = AsyncMock(return_value=[1, 0])
        mock_redis.zcount = AsyncMock(return_value=1)
        with (
            patch("app.core.config.settings.RATE_LIMIT_ENABLED", True),
            patch("app.middleware.rate_limit.RateLimitMiddleware._get_redis", AsyncMock(return_value=mock_redis)),
        ):
            response = await rate_limited_client.get("/api/v1/health")
            assert response.status_code == 200
            assert "X-RateLimit-Limit" in response.headers
            assert "X-RateLimit-Remaining" in response.headers

    async def test_rate_limit_exceeded(
        self, mock_redis: AsyncMock, rate_limited_client: AsyncClient
    ) -> None:
        mock_redis.eval = AsyncMock(return_value=[0, 30])
        mock_redis.zcount = AsyncMock(return_value=100)
        with (
            patch("app.core.config.settings.RATE_LIMIT_ENABLED", True),
            patch("app.middleware.rate_limit.RateLimitMiddleware._get_redis", AsyncMock(return_value=mock_redis)),
        ):
            response = await rate_limited_client.get("/api/v1/health")
            assert response.status_code == 429
            assert response.headers.get("Retry-After") == "30"
            data = response.json()
            assert data["error"]["details"]["retry_after_seconds"] == 30

    async def test_redis_failure_fail_open(self, rate_limited_client: AsyncClient) -> None:
        with (
            patch("app.core.config.settings.RATE_LIMIT_ENABLED", True),
            patch("app.middleware.rate_limit.RateLimitMiddleware._get_redis", AsyncMock(return_value=None)),
        ):
            response = await rate_limited_client.get("/api/v1/health")
            assert response.status_code == 200


class TestRateLimitDisabled:
    @patch("app.core.config.settings.RATE_LIMIT_ENABLED", False)
    async def test_rate_limit_disabled_passes(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/health")
        assert response.status_code == 200


class TestNoRealRedisDependency:
    async def test_middleware_never_creates_real_redis_pool(
        self, rate_limited_client: AsyncClient
    ) -> None:
        async def _boom() -> None:
            raise AssertionError("RateLimitMiddleware attempted to create a real Redis pool in tests")

        with (
            patch("app.core.config.settings.RATE_LIMIT_ENABLED", True),
            patch("app.workers.redis_client.get_redis_pool", _boom),
        ):
            response = await rate_limited_client.get("/api/v1/health")

        assert response.status_code == 200
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers

    async def test_middleware_never_creates_real_redis_connection(
        self, rate_limited_client: AsyncClient
    ) -> None:
        from redis.asyncio.connection import ConnectionPool

        with (
            patch("app.core.config.settings.RATE_LIMIT_ENABLED", True),
            patch.object(ConnectionPool, "from_url") as mock_from_url,
        ):
            response = await rate_limited_client.get("/api/v1/health")

        mock_from_url.assert_not_called()
        assert response.status_code == 200
        assert "X-RateLimit-Limit" in response.headers


class TestParseRouteOverrides:
    def test_parses_quiz_defaults(self) -> None:
        from app.middleware.rate_limit import parse_route_overrides

        overrides = parse_route_overrides(
            r"^/api/v1/presentations/[^/]+/quizzes$=10/60,"
            r"^/api/v1/quizzes/[^/]+/attempts/[^/]+/submit$=30/60"
        )
        assert overrides == {
            r"^/api/v1/presentations/[^/]+/quizzes$": (10, 60),
            r"^/api/v1/quizzes/[^/]+/attempts/[^/]+/submit$": (30, 60),
        }

    def test_empty_string_returns_empty(self) -> None:
        from app.middleware.rate_limit import parse_route_overrides

        assert parse_route_overrides("") == {}

    def test_malformed_entries_are_skipped(self) -> None:
        from app.middleware.rate_limit import parse_route_overrides

        overrides = parse_route_overrides("garbage,^/health$=20/60,also_bad=not_a_limit")
        assert overrides == {r"^/health$": (20, 60)}

    def test_patterns_compile_for_regex_search(self) -> None:
        import re

        from app.middleware.rate_limit import parse_route_overrides

        overrides = parse_route_overrides(r"^/api/v1/quizzes/[^/]+/session$=240/60")
        compiled = [re.compile(pattern) for pattern in overrides]
        assert any(
            pattern.search("/api/v1/quizzes/quiz_abc/session") for pattern in compiled
        )
        assert not any(
            pattern.search("/api/v1/quizzes/quiz_abc/attempts") for pattern in compiled
        )


class TestRateLimitService:
    @pytest.mark.asyncio
    async def test_whitelist_bypass(self) -> None:
        from app.middleware.rate_limit import RateLimitMiddleware

        mock_app = MagicMock()
        mock_app.dispatch = AsyncMock()

        middleware = RateLimitMiddleware(
            mock_app,
            whitelist={"127.0.0.1", "10.0.0.1"},
        )

        assert "127.0.0.1" in middleware._whitelist
        assert "10.0.0.1" in middleware._whitelist

    @pytest.mark.asyncio
    async def test_blacklist_block(self) -> None:
        from app.middleware.rate_limit import RateLimitMiddleware

        middleware = RateLimitMiddleware(
            MagicMock(),
            blacklist={"192.168.1.100"},
        )

        assert "192.168.1.100" in middleware._blacklist

    @pytest.mark.asyncio
    async def test_trusted_proxies_default(self) -> None:
        from app.middleware.rate_limit import RateLimitMiddleware

        middleware = RateLimitMiddleware(MagicMock())

        assert "127.0.0.1" in middleware._trusted_proxies
        assert "10.0.0.0/8" in middleware._trusted_proxies

    @pytest.mark.asyncio
    async def test_resolve_client_ip_x_forwarded_for(self) -> None:
        from starlette.requests import Request

        from app.middleware.rate_limit import RateLimitMiddleware

        middleware = RateLimitMiddleware(MagicMock())

        scope = {
            "type": "http",
            "client": ("127.0.0.1", 50000),
            "headers": [
                (b"x-forwarded-for", b"203.0.113.1, 10.0.0.1, 192.168.1.1"),
            ],
        }
        request = Request(scope)
        ip = middleware._resolve_client_ip(request)
        assert ip == "203.0.113.1"

    @pytest.mark.asyncio
    async def test_resolve_client_ip_x_real_ip(self) -> None:
        from starlette.requests import Request

        from app.middleware.rate_limit import RateLimitMiddleware

        middleware = RateLimitMiddleware(MagicMock())

        scope = {
            "type": "http",
            "client": ("127.0.0.1", 50000),
            "headers": [(b"x-real-ip", b"203.0.113.7")],
        }
        request = Request(scope)
        ip = middleware._resolve_client_ip(request)
        assert ip == "203.0.113.7"
