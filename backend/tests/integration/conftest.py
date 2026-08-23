from __future__ import annotations

import os
from collections.abc import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.database.base import Base

pytestmark = pytest.mark.integration


@pytest.fixture(scope="session")
def postgres_dsn() -> Generator[str]:
    try:
        from testcontainers.postgres import PostgresContainer

        container = PostgresContainer("postgres:16-alpine")
        container.start()
        sync_url = container.get_connection_url()
        async_url = sync_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1).replace("postgresql://", "postgresql+asyncpg://", 1)
        os.environ["DATABASE_URL"] = async_url
        try:
            yield async_url
        finally:
            container.stop()
    except Exception:
        db_url = os.environ.get("CI_DATABASE_URL") or os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
        if db_url:
            async_url = db_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1).replace("postgresql://", "postgresql+asyncpg://", 1)
            os.environ["DATABASE_URL"] = async_url
            yield async_url
        else:
            fallback_url = "sqlite+aiosqlite:///:memory:"
            os.environ["DATABASE_URL"] = fallback_url
            yield fallback_url


@pytest_asyncio.fixture(scope="session")
async def pg_engine(postgres_dsn: str) -> AsyncGenerator[AsyncEngine]:
    engine = create_async_engine(
        postgres_dsn,
        echo=False,
        poolclass=NullPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def pg_session(pg_engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    session_factory = async_sessionmaker(
        pg_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session
        await session.rollback()
