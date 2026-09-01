"""PostgreSQL test infrastructure (WS2).

These tests run only against a real PostgreSQL instance and are selected with
``pytest -m postgres``. They are intentionally separate from the default
SQLite fast-test path so the two suites do not interfere (see Phase 2 scope).

DSN resolution order (first match wins):
  1. testcontainers ``PostgresContainer("postgres:16-alpine")`` when the
     ``testcontainers`` package is installed
  2. ``CI_DATABASE_URL``
  3. ``TEST_DATABASE_URL``
  4. a ``postgresql*://`` value in ``DATABASE_URL``
If none resolves to PostgreSQL, the whole module is skipped.

Every test runs against a dedicated scratch database that is created (and
dropped) around the session, migrated to the current Alembic head so that
behavioral tests exercise the *production migration lineage*, not
``metadata.create_all``.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator, Generator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.postgres

BACKEND_DIR = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = BACKEND_DIR / "app" / "database" / "migrations"
SCRATCH_DB = "eduvision_p2_pgtest"


def _to_asyncpg_url(url: str) -> str:
    return (
        url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
        .replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)
        .replace("postgresql://", "postgresql+asyncpg://", 1)
    )


@pytest.fixture(scope="session")
def pg_base_url() -> Generator[str]:
    """Resolve a PostgreSQL DSN or skip the whole module."""
    try:
        from testcontainers.postgres import PostgresContainer  # noqa: PLC0415

        container = PostgresContainer("postgres:16-alpine")
        container.start()
        try:
            yield _to_asyncpg_url(container.get_connection_url())
        finally:
            container.stop()
        return
    except Exception:
        pass

    url = (
        os.environ.get("CI_DATABASE_URL")
        or os.environ.get("TEST_DATABASE_URL")
        or os.environ.get("DATABASE_URL", "")
    )
    if not url or not url.startswith("postgresql"):
        pytest.skip(
            "no PostgreSQL instance configured for -m postgres; "
            "set CI_DATABASE_URL or TEST_DATABASE_URL "
            "(e.g. postgresql+asyncpg://...)"
        )
    yield _to_asyncpg_url(url)


def _admin_url(url: str) -> str:
    """Return a DSN that connects to the maintenance database on the server."""
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(url)
    return urlunsplit(("postgresql", parts.netloc, "/postgres", "", ""))


async def _create_scratch_database(url: str) -> str:
    """Create a fresh scratch database and return its DSN.

    Uses asyncpg directly because ``CREATE DATABASE`` cannot run inside a
    transaction block (SQLAlchemy's implicit transaction would reject it).
    Raises RuntimeError if the login role lacks CREATEDB privileges.
    """
    from urllib.parse import urlsplit, urlunsplit

    import asyncpg

    conn = await asyncpg.connect(_admin_url(url))
    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", SCRATCH_DB
        )
        if exists:
            await conn.execute(f"DROP DATABASE IF EXISTS {SCRATCH_DB} WITH (FORCE)")
        await conn.execute(f"CREATE DATABASE {SCRATCH_DB}")
    finally:
        await conn.close()

    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, f"/{SCRATCH_DB}", "", ""))


def _run_alembic_upgrade(dsn: str) -> None:
    """Run ``alembic upgrade head`` against the given (asyncpg) DSN."""
    from alembic import command
    from alembic.config import Config

    from app.core.config import settings as app_settings

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))

    original = app_settings.DATABASE_URL
    app_settings.DATABASE_URL = dsn
    try:
        command.upgrade(cfg, "head")
    finally:
        app_settings.DATABASE_URL = original


@pytest.fixture(scope="session")
def migrated_pg_url(pg_base_url: str) -> Generator[str]:
    """Create a scratch PG database and migrate it to the Alembic head."""
    import asyncio

    def _prepare() -> str:
        return asyncio.run(_create_scratch_database(pg_base_url))

    try:
        scratch = _prepare()
    except Exception:
        pytest.skip(
            "cannot create scratch PostgreSQL database (login role needs CREATEDB); "
            "the -m postgres suites require a dedicated instance"
        )
    try:
        _run_alembic_upgrade(scratch)
        yield scratch
    finally:
        async def _cleanup() -> None:
            import asyncpg

            conn = await asyncpg.connect(_admin_url(scratch))
            try:
                await conn.execute(
                    f"DROP DATABASE IF EXISTS {SCRATCH_DB} WITH (FORCE)"
                )
            except Exception:
                pass
            finally:
                await conn.close()

        asyncio.run(_cleanup())


@pytest_asyncio.fixture(scope="session")
async def pg_engine(migrated_pg_url: str) -> AsyncGenerator[AsyncEngine]:
    engine = create_async_engine(
        migrated_pg_url,
        echo=False,
        poolclass=NullPool,
    )
    yield engine
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
