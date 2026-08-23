from __future__ import annotations

import contextlib
import os
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ---------------------------------------------------------------------------
# JSONB / SQLite compatibility: compile PostgreSQL JSONB to plain JSON on
# SQLite so the same ORM model definitions work in both production (PG) and
# the test suite (SQLite).
# ---------------------------------------------------------------------------
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import NullPool


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):  # noqa: D401
    return "JSON"


# The imports below intentionally follow the JSONB compiler registration so
# every app module observes the SQLite-compatible compilation rule.
import app.database.session as db_session_module  # noqa: E402
import app.database.unit_of_work as uow_module  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.main import app  # noqa: E402

ROOT_DIR = Path(__file__).resolve().parents[1]
TEST_DB_PATH = Path(
    os.environ.get("EDUVISION_TEST_DB_PATH") or (ROOT_DIR / "test.db")
)

test_engine = create_async_engine(
    f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}",
    echo=False,
    poolclass=NullPool,
    connect_args={"timeout": 30},
)

TestSessionLocal = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_database() -> AsyncGenerator[None]:
    from app.core.config import settings

    original_db_url = settings.DATABASE_URL
    original_app_env = settings.APP_ENV
    original_db_async_session_factory = db_session_module.async_session_factory
    original_uow_async_session_factory = uow_module.async_session_factory

    original_storage_provider = settings.STORAGE_PROVIDER
    settings.APP_ENV = "test"
    settings.STORAGE_PROVIDER = "local"
    settings.DATABASE_URL = "sqlite+aiosqlite:///test.db"
    db_session_module.async_session_factory = TestSessionLocal
    uow_module.async_session_factory = TestSessionLocal

    import app.models  # noqa: F401

    for stale_db in (TEST_DB_PATH, Path(str(TEST_DB_PATH) + "-wal"), Path(str(TEST_DB_PATH) + "-shm")):
        if stale_db.exists():
            with contextlib.suppress(PermissionError):
                stale_db.unlink()
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()

    db_session_module.async_session_factory = original_db_async_session_factory
    uow_module.async_session_factory = original_uow_async_session_factory
    settings.DATABASE_URL = original_db_url
    settings.APP_ENV = original_app_env
    settings.STORAGE_PROVIDER = original_storage_provider


@pytest_asyncio.fixture
async def db_session(setup_database: None) -> AsyncGenerator[AsyncSession]:
    async with TestSessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(setup_database: None) -> AsyncGenerator[AsyncClient]:
    from app.core.config import settings

    original_email_verification_required = settings.EMAIL_VERIFICATION_REQUIRED
    original_cookie_secure = settings.COOKIE_SECURE
    original_rate_limit_enabled = settings.RATE_LIMIT_ENABLED
    original_app_env = settings.APP_ENV
    original_db_url = settings.DATABASE_URL

    settings.APP_ENV = "test"
    settings.EMAIL_VERIFICATION_REQUIRED = False
    settings.COOKIE_SECURE = False
    settings.RATE_LIMIT_ENABLED = False
    settings.DATABASE_URL = "sqlite+aiosqlite:///test.db"

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        follow_redirects=True,
    ) as client:
        yield client

    settings.EMAIL_VERIFICATION_REQUIRED = original_email_verification_required
    settings.COOKIE_SECURE = original_cookie_secure
    settings.RATE_LIMIT_ENABLED = original_rate_limit_enabled
    settings.APP_ENV = original_app_env
    settings.DATABASE_URL = original_db_url


@pytest.fixture
def app_config():
    from app.core.config import settings

    return settings


@pytest.fixture
def mock_redis() -> AsyncMock:
    redis_mock = AsyncMock()
    redis_mock.ping.return_value = True
    redis_mock.info.return_value = {"redis_version": "7.0"}
    redis_mock.eval = AsyncMock(return_value=[1, 0])
    redis_mock.zcount = AsyncMock(return_value=1)
    return redis_mock


@pytest.fixture
def mock_storage() -> MagicMock:
    storage = MagicMock()
    storage.list_buckets = AsyncMock(return_value=[{"name": "eduvision-content", "creation_date": "test"}])
    storage.initialize = AsyncMock()
    storage.close = AsyncMock()
    storage.upload_fileobj = AsyncMock(return_value="test-key")
    storage.download_fileobj = AsyncMock(return_value=b"test-data")
    storage.delete_object = AsyncMock()
    storage.object_exists = AsyncMock(return_value=True)
    return storage


@pytest.fixture(autouse=True)
def disable_celery_task_dispatch():
    with patch(
        "app.workers.tasks.generate_thumbnail_task.delay",
        new=MagicMock(),
    ), patch(
        "app.workers.tasks.process_source_ingestion_task.delay",
        new=MagicMock(),
    ):
        yield


@pytest.fixture(autouse=True)
def override_external_deps(mock_redis: AsyncMock, mock_storage: MagicMock):
    from app.storage.factory import get_storage_backend
    from app.workers.redis_client import get_redis_client

    async def _get_redis_override():
        yield mock_redis

    def _get_storage_override():
        return mock_storage

    app.dependency_overrides[get_redis_client] = _get_redis_override
    app.dependency_overrides[get_storage_backend] = _get_storage_override

    with patch(
        "app.middleware.rate_limit.RateLimitMiddleware._get_redis",
        new=AsyncMock(return_value=mock_redis),
    ):
        yield
    app.dependency_overrides.pop(get_redis_client, None)
    app.dependency_overrides.pop(get_storage_backend, None)


# ---------------------------------------------------------------------------
# Auth fixtures — create a test user and override get_current_user so all
# protected endpoints work in tests without real JWT tokens.
# ---------------------------------------------------------------------------

TEST_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
TEST_USER_EMAIL = "test@example.com"
TEST_USER_NAME = "Test User"


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _create_test_user(setup_database: None) -> None:
    """Insert a minimal test user into the database once per session."""
    from sqlalchemy import select

    from app.core.security import hash_password
    from app.models.user import User

    async with TestSessionLocal() as session:
        existing = await session.execute(select(User).where(User.id == TEST_USER_ID))
        if existing.scalar_one_or_none() is None:
            user = User(
                id=TEST_USER_ID,
                email=TEST_USER_EMAIL,
                name=TEST_USER_NAME,
                password_hash=hash_password("testpassword123"),
            )
            session.add(user)
            await session.flush()


class _FakeUser:
    """Minimal stand-in for User model used by get_current_user override."""
    def __init__(self) -> None:
        self.id = TEST_USER_ID
        self.email = TEST_USER_EMAIL
        self.name = TEST_USER_NAME


@pytest.fixture(autouse=True)
def _override_get_current_user():
    """Override get_current_user in all tests so protected endpoints work."""
    from app.core.dependencies import get_current_user

    async def _fake_user():
        return _FakeUser()

    app.dependency_overrides[get_current_user] = _fake_user
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Return Authorization headers for tests that need to hit auth endpoints directly."""
    from app.core.security import create_access_token
    token = create_access_token(TEST_USER_ID, role="user")
    return {"Authorization": f"Bearer {token}"}

