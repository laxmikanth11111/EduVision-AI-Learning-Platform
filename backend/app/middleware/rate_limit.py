from __future__ import annotations

import re
import time
from typing import Any

from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

SLIDING_WINDOW_SCRIPT = """
local key = KEYS[1]
local window = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

redis.call('ZREMRANGEBYSCORE', key, 0, now - window)

local count = redis.call('ZCARD', key)

if count >= limit then
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local retry_after = math.ceil((tonumber(oldest[2]) + window) - now)
    return {0, retry_after}
end

redis.call('ZADD', key, now, now .. ':' .. math.random())
redis.call('EXPIRE', key, window)
return {1, 0}
"""


def parse_route_overrides(raw: str) -> dict[str, tuple[int, int]]:
    """Parse the ``RATE_LIMIT_ROUTES`` setting into middleware overrides.

    Format: comma-separated ``PATH_REGEX=LIMIT/WINDOW`` entries, e.g.::

        RATE_LIMIT_ROUTES=^/api/v1/presentations/[^/]+/quizzes$=10/60,^/api/v1/quizzes/[^/]+/attempts/[^/]+/submit$=30/60

    Each pattern is compiled with :mod:`re` and matched with ``search`` against
    the request path; the first match wins. Malformed entries are logged and
    skipped so a bad value degrades to the default limit rather than crashing
    the process.
    """
    overrides: dict[str, tuple[int, int]] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        pattern, _, limits = entry.rpartition("=")
        try:
            limit_str, window_str = limits.split("/", 1)
            overrides[pattern.strip()] = (
                int(limit_str.strip()),
                int(window_str.strip()),
            )
        except ValueError:
            logger.warning("rate_limit_route_malformed", entry=entry)
    return overrides


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: ASGIApp,
        default_limit: int | None = None,
        default_window: int | None = None,
        whitelist: set[str] | None = None,
        blacklist: set[str] | None = None,
        route_overrides: dict[str, tuple[int, int]] | None = None,
        trusted_proxies: set[str] | None = None,
    ) -> None:
        super().__init__(app)
        self._redis: Redis | None = None
        self._default_limit = default_limit or settings.RATE_LIMIT_DEFAULT
        self._default_window = default_window or settings.RATE_LIMIT_WINDOW
        self._whitelist = whitelist or set()
        self._blacklist = blacklist or set()
        if trusted_proxies is None:
            raw_proxies = getattr(settings, "RATE_LIMIT_TRUSTED_PROXIES", "127.0.0.1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16")
            self._trusted_proxies = {p.strip() for p in raw_proxies.split(",") if p.strip()}
        else:
            self._trusted_proxies = trusted_proxies
        self._parsed_trusted_proxies: list[Any] = []
        import ipaddress

        for proxy_str in self._trusted_proxies:
            try:
                if "/" in proxy_str:
                    self._parsed_trusted_proxies.append(ipaddress.ip_network(proxy_str, strict=False))
                else:
                    self._parsed_trusted_proxies.append(ipaddress.ip_address(proxy_str))
            except ValueError:
                pass

        self._redis_available: bool | None = None
        self._route_overrides: dict[re.Pattern[str], tuple[int, int]] = {}
        if route_overrides:
            for pattern, (limit, window) in route_overrides.items():
                self._route_overrides[re.compile(pattern)] = (limit, window)

    async def _get_redis(self) -> Redis | None:
        if self._redis_available is False:
            return None
        if self._redis is not None:
            return self._redis
        try:
            from app.workers.redis_client import get_redis_pool

            pool = await get_redis_pool()
            self._redis = Redis(connection_pool=pool)
            self._redis_available = True
            return self._redis
        except Exception as exc:
            self._redis_available = False
            logger.error("rate_limit_redis_unavailable", error=str(exc))
            return None

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        if not settings.RATE_LIMIT_ENABLED:
            return await call_next(request)

        client_ip = self._resolve_client_ip(request)
        request_id = getattr(request.state, "request_id", None)

        if client_ip in self._whitelist:
            return await call_next(request)

        if client_ip in self._blacklist:
            logger.warning("rate_limit_blacklisted_request", client_ip=client_ip)
            return JSONResponse(
                status_code=403,
                content={
                    "success": False,
                    "error": {
                        "code": "FORBIDDEN",
                        "message": "Access denied",
                        "details": {},
                        "request_id": request_id,
                    },
                },
            )

        limit, window = self._resolve_limits(request)

        redis = await self._get_redis()
        if redis is None:
            return await call_next(request)

        try:
            allowed, retry_after = await self._check_rate_limit(
                redis, client_ip, str(request.url.path), limit, window
            )

            headers = {
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": str(
                    max(
                        0,
                        limit
                        - await self._estimate_count(
                            redis, client_ip, str(request.url.path), window
                        ),
                    )
                ),
                "X-RateLimit-Reset": str(int(time.time()) + window),
            }

            if not allowed:
                headers["Retry-After"] = str(retry_after)
                logger.warning(
                    "rate_limit_exceeded",
                    client_ip=client_ip,
                    path=str(request.url.path),
                    limit=limit,
                    window=window,
                )
                return JSONResponse(
                    status_code=429,
                    content={
                        "success": False,
                        "error": {
                            "code": "RATE_LIMIT_EXCEEDED",
                            "message": "Rate limit exceeded. Try again later.",
                            "details": {"retry_after_seconds": retry_after},
                            "request_id": request_id,
                        },
                    },
                    headers=headers,
                )

            response = await call_next(request)
            for key, value in headers.items():
                response.headers[key] = value
            return response
        except Exception as exc:
            self._redis_available = False
            self._redis = None
            logger.error("rate_limit_check_failed", error=str(exc))
            return await call_next(request)

    def _resolve_client_ip(self, request: Request) -> str:
        direct_ip = request.client.host if request.client else "unknown"
        if not self._is_trusted_proxy(direct_ip):
            return direct_ip

        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            ips = [ip.strip() for ip in forwarded.split(",")]
            for ip in reversed(ips):
                if not self._is_trusted_proxy(ip):
                    return ip
        real_ip = request.headers.get("X-Real-IP")
        if real_ip and not self._is_trusted_proxy(real_ip):
            return real_ip
        return direct_ip

    def _is_trusted_proxy(self, ip: str) -> bool:
        if not ip or ip == "unknown":
            return False
        import ipaddress

        try:
            addr = ipaddress.ip_address(ip)
            for proxy in self._parsed_trusted_proxies:
                if isinstance(proxy, (ipaddress.IPv4Network, ipaddress.IPv6Network)):
                    if addr in proxy:
                        return True
                elif addr == proxy:
                    return True
        except ValueError:
            pass
        return False

    def _resolve_limits(self, request: Request) -> tuple[int, int]:
        path = str(request.url.path)
        for pattern, (limit, window) in self._route_overrides.items():
            if pattern.search(path):
                return limit, window
        return self._default_limit, self._default_window

    async def _check_rate_limit(
        self,
        redis: Redis,
        client_ip: str,
        path: str,
        limit: int,
        window: int,
    ) -> tuple[bool, int]:
        key = f"ratelimit:{client_ip}:{path}"
        now = time.time()

        allowed, retry_after = await self._eval_sliding_window(
            redis, key, window, limit, now
        )
        return bool(allowed), retry_after

    async def _eval_sliding_window(
        self,
        redis: Redis,
        key: str,
        window: int,
        limit: int,
        now: float,
    ) -> tuple[int, int]:
        result = await redis.eval(
            SLIDING_WINDOW_SCRIPT,
            1,
            key,
            window,
            limit,
            int(now * 1000),
        )
        if isinstance(result, list) and len(result) == 2:
            return int(result[0]), int(result[1])
        return 1, 0

    async def _estimate_count(
        self,
        redis: Redis,
        client_ip: str,
        path: str,
        window: int,
    ) -> int:
        key = f"ratelimit:{client_ip}:{path}"
        now = time.time()
        count = await redis.zcount(key, now - window, now)
        return count or 0
