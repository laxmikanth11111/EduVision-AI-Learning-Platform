from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

from fastapi import Cookie, HTTPException, Request, status
from jose import JWTError
from redis.asyncio import Redis as AsyncRedis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import AIProvider
from app.ai.factory import get_ai_provider
from app.core.security import decode_access_token
from app.database.session import get_session
from app.database.unit_of_work import UnitOfWork
from app.models.user import User
from app.storage.base import StorageBackend
from app.storage.factory import get_storage_backend
from app.workers.redis_client import get_redis_client


async def get_db_session() -> AsyncGenerator[AsyncSession]:
    async for session in get_session():
        yield session


async def get_unit_of_work() -> AsyncGenerator[UnitOfWork]:
    async with UnitOfWork() as uow:
        yield uow


async def get_redis() -> AsyncGenerator[AsyncRedis]:
    async for redis in get_redis_client():
        yield redis


async def get_storage() -> AsyncGenerator[StorageBackend]:
    storage = await get_storage_backend()
    yield storage


async def get_ai() -> AsyncGenerator[AIProvider]:
    yield get_ai_provider()


async def get_current_user(
    request: Request,
    access_token: str | None = Cookie(None),
) -> User:
    """Resolve the current user from JWT access token (cookie or Authorization header).

    Raises 401 if token is missing, invalid, or user not found.
    """
    # Lazy import to avoid circular dependency
    from app.database.session import async_session_factory

    # Extract token from cookie or Authorization header
    token = access_token
    if not token:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = uuid.UUID(payload["sub"])

    async with async_session_factory() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user
