from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import AsyncAdaptedQueuePool, NullPool

from app.core.commit_barrier import clear_commit_hook, publish_commit_hook
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_engine_kwargs: dict[str, Any] = {
    "echo": settings.DATABASE_ECHO,
    "poolclass": NullPool if settings.is_testing else AsyncAdaptedQueuePool,
    "pool_recycle": settings.DATABASE_POOL_RECYCLE,
    "pool_pre_ping": True,
}
if not settings.is_testing:
    _engine_kwargs.update(
        {
            "pool_size": settings.DATABASE_POOL_SIZE,
            "max_overflow": settings.DATABASE_MAX_OVERFLOW,
            "pool_timeout": settings.DATABASE_POOL_TIMEOUT,
        }
    )

engine = create_async_engine(settings.DATABASE_URL, **_engine_kwargs)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session(request: Request) -> AsyncGenerator[AsyncSession]:
    """Yield a request-scoped session, committing before the response is sent.

    The commit is published to
    :class:`~app.core.commit_barrier.CommitBarrierRoute` because dependency
    teardown runs after the response has already been handed to the ASGI
    server; committing only there lets a successful response be observed
    before its own transaction is visible elsewhere.
    """
    async with async_session_factory() as session:
        publish_commit_hook(request, session.commit)
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            clear_commit_hook(request)
            await session.close()


async def check_database_connection() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("database_connection_healthy")
        return True
    except Exception as e:
        logger.error("database_connection_failed", error=str(e))
        return False


async def close_database_connections() -> None:
    await engine.dispose()
    logger.info("database_connections_closed")

