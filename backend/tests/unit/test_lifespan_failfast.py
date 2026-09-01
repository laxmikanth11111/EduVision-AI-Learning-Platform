"""WS9: lifespan fail-fast on startup migration failure.

Verifies the app refuses to start when Alembic migrations fail and
``LIFESPAN_FAIL_FAST_ON_MIGRATION_ERROR`` is enabled, and continues
(tolerant) when disabled.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.main import lifespan


@pytest.fixture
def app_mock():
    return object()


async def _run_lifespan(app_mock) -> Exception | None:
    """Enter the lifespan, return the raised exception (or None)."""
    exc = None
    try:
        async with lifespan(app_mock):
            pass
    except Exception as e:  # noqa: BLE001
        exc = e
    return exc


async def test_migration_failure_fails_fast_when_enabled(app_mock) -> None:
    with patch(
        "app.main.settings.AUTO_MIGRATE_ON_STARTUP",
        True,
    ), patch(
        "app.main.settings.LIFESPAN_FAIL_FAST_ON_MIGRATION_ERROR",
        True,
    ), patch(
        "alembic.command.upgrade",
        side_effect=RuntimeError("db unreachable"),
    ), patch(
        "app.main.cancel_background_tasks",
        AsyncMock(),
    ), patch(
        "app.main.close_database_connections",
        AsyncMock(),
    ), patch(
        "app.main.close_redis_pool",
        AsyncMock(),
    ), patch(
        "app.main.close_storage_backend",
        AsyncMock(),
    ):
        exc = await _run_lifespan(app_mock)

    assert exc is not None
    assert "refusing to start" in str(exc)


async def test_migration_failure_tolerated_when_disabled(app_mock) -> None:
    with patch(
        "app.main.settings.AUTO_MIGRATE_ON_STARTUP",
        True,
    ), patch(
        "app.main.settings.LIFESPAN_FAIL_FAST_ON_MIGRATION_ERROR",
        False,
    ), patch(
        "alembic.command.upgrade",
        side_effect=RuntimeError("db unreachable"),
    ), patch(
        "app.main.cancel_background_tasks",
        AsyncMock(),
    ), patch(
        "app.main.close_database_connections",
        AsyncMock(),
    ), patch(
        "app.main.close_redis_pool",
        AsyncMock(),
    ), patch(
        "app.main.close_storage_backend",
        AsyncMock(),
    ):
        exc = await _run_lifespan(app_mock)

    assert exc is None


async def test_no_migration_when_auto_migrate_disabled(app_mock) -> None:
    with patch(
        "app.main.settings.AUTO_MIGRATE_ON_STARTUP",
        False,
    ), patch(
        "alembic.command.upgrade",
        side_effect=AssertionError("should not run"),
    ), patch(
        "app.main.cancel_background_tasks",
        AsyncMock(),
    ), patch(
        "app.main.close_database_connections",
        AsyncMock(),
    ), patch(
        "app.main.close_redis_pool",
        AsyncMock(),
    ), patch(
        "app.main.close_storage_backend",
        AsyncMock(),
    ):
        exc = await _run_lifespan(app_mock)

    assert exc is None


async def test_successful_migration_starts(app_mock) -> None:
    with patch(
        "app.main.settings.AUTO_MIGRATE_ON_STARTUP",
        True,
    ), patch(
        "app.main.settings.LIFESPAN_FAIL_FAST_ON_MIGRATION_ERROR",
        True,
    ), patch(
        "alembic.command.upgrade",
        return_value=None,
    ), patch(
        "app.main.cancel_background_tasks",
        AsyncMock(),
    ), patch(
        "app.main.close_database_connections",
        AsyncMock(),
    ), patch(
        "app.main.close_redis_pool",
        AsyncMock(),
    ), patch(
        "app.main.close_storage_backend",
        AsyncMock(),
    ):
        exc = await _run_lifespan(app_mock)

    assert exc is None

