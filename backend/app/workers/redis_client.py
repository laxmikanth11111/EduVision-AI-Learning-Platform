from __future__ import annotations

from collections.abc import AsyncGenerator

from redis.asyncio import ConnectionPool
from redis.asyncio import Redis as AsyncRedis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.core.config import settings
from app.core.logging import get_logger
from app.utils.retry_helpers import retry_async

logger = get_logger(__name__)

_pool: ConnectionPool | None = None


async def get_redis_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            max_connections=50,
            socket_connect_timeout=settings.REDIS_SOCKET_TIMEOUT,
            socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
            retry_on_timeout=True,
            health_check_interval=30,
        )
        logger.info("redis_pool_created")
    return _pool


async def get_redis_client() -> AsyncGenerator[AsyncRedis]:
    pool = await get_redis_pool()
    redis = AsyncRedis(connection_pool=pool)
    try:
        yield redis
    finally:
        await redis.close()


async def check_redis_connection() -> bool:
    try:
        pool = await get_redis_pool()
        redis = AsyncRedis(connection_pool=pool)
        result = await redis.ping()
        await redis.close()
        logger.info("redis_connection_healthy")
        return result
    except (RedisConnectionError, RedisTimeoutError, OSError) as e:
        logger.error("redis_connection_failed", error=str(e))
        return False


async def close_redis_pool() -> None:
    global _pool
    if _pool:
        await _pool.disconnect()
        _pool = None
        logger.info("redis_pool_closed")


async def redis_with_retry() -> AsyncRedis:
    pool = await retry_async(
        get_redis_pool,
        attempts=settings.REDIS_RETRY_ATTEMPTS,
        min_wait=settings.REDIS_RETRY_DELAY,
        exceptions=(RedisConnectionError, RedisTimeoutError, OSError),
    )
    return AsyncRedis(connection_pool=pool)
