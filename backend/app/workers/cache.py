from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar, cast

from redis.asyncio import Redis

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class CacheService:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def get(self, key: str) -> Any | None:
        value = await self._redis.get(key)
        if value is not None:
            return json.loads(value)
        return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None,
    ) -> None:
        serialized = json.dumps(value, default=str)
        await self._redis.set(key, serialized, ex=ttl or settings.REDIS_CACHE_TTL)

    async def delete(self, key: str) -> None:
        await self._redis.delete(key)

    async def delete_pattern(self, pattern: str) -> None:
        cursor = 0
        while True:
            cursor, keys = await self._redis.scan(cursor=cursor, match=pattern, count=100)
            if keys:
                await self._redis.delete(*keys)
            if cursor == 0:
                break

    async def remember(
        self,
        key: str,
        ttl: int | None,
        factory: Callable[[], Awaitable[T]],
    ) -> T:
        cached = await self.get(key)
        if cached is not None:
            return cast(T, cached)
        value = await factory()
        await self.set(key, value, ttl)
        return value

    async def exists(self, key: str) -> bool:
        return await self._redis.exists(key) > 0

    async def incr(self, key: str, amount: int = 1) -> int:
        return await self._redis.incr(key, amount)

    async def expire(self, key: str, ttl: int) -> None:
        await self._redis.expire(key, ttl)

    async def acquire_lock(self, lock_key: str, ttl: int = 10) -> bool:
        acquired = await self._redis.set(
            f"lock:{lock_key}",
            "1",
            nx=True,
            ex=ttl,
        )
        return acquired is not None

    async def release_lock(self, lock_key: str) -> None:
        await self._redis.delete(f"lock:{lock_key}")

    async def clear_all(self) -> None:
        await self._redis.flushdb()
        logger.info("cache_cleared")
