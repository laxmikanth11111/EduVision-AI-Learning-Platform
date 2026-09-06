from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError

from app.core.config import settings
from app.core.security import hash_password
from app.database.retry import retry_on_db_failure
from app.database.unit_of_work import UnitOfWork
from app.models.user import User
from tests.conftest import TestSessionLocal

pytestmark = pytest.mark.asyncio


def _make_dbapi_error(pgcode: str) -> DBAPIError:
    orig = Exception("DB Error")
    orig.pgcode = pgcode
    return DBAPIError("statement", {}, orig)


async def _insert_then_boom(session) -> None:
    from app.core.security import hash_password

    async with UnitOfWork(session=session) as uow:
        uow.session.add(
            User(
                id=__import__("uuid").UUID("11111111-1111-1111-1111-111111111111"),
                email="rollback-probe@example.com",
                name="Rollback Probe",
                password_hash=hash_password("testpassword123"),
            )
        )
        await uow.flush()
        raise RuntimeError("boom")


async def test_uow_rolls_back_when_body_raises() -> None:
    async with TestSessionLocal() as session:
        with pytest.raises(RuntimeError):
            await _insert_then_boom(session)

        stmt = select(User).where(User.email == "rollback-probe@example.com")
        result = await session.execute(stmt)
        assert result.scalar_one_or_none() is None


async def test_uow_commits_pending_writes_on_success() -> None:
    from app.core.security import hash_password

    user_id = __import__("uuid").UUID("22222222-2222-2222-2222-222222222222")
    async with TestSessionLocal() as session, UnitOfWork(session=session) as uow:
        uow.session.add(
            User(
                id=user_id,
                email="commit-probe@example.com",
                name="Commit Probe",
                password_hash=hash_password("testpassword123"),
            )
        )
        await uow.flush()

    async with TestSessionLocal() as check:
        stmt = select(User).where(User.id == user_id)
        result = await check.execute(stmt)
        assert result.scalar_one_or_none() is not None


async def _flush_duplicate(session) -> None:
    async with UnitOfWork(session=session) as uow:
        uow.session.add(
            User(
                id=__import__("uuid").UUID("44444444-4444-4444-4444-444444444444"),
                email="dupe-probe@example.com",
                name="Second",
                password_hash=hash_password("testpassword123"),
            )
        )
        await uow.flush()


async def test_session_reusable_after_integrity_error() -> None:
    """After a failed flush the session must be recoverable via rollback and
    usable for subsequent work in the same object."""
    from app.core.security import hash_password

    async with TestSessionLocal() as session:
        async with UnitOfWork(session=session) as uow:
            uow.session.add(
                User(
                    id=__import__("uuid").UUID("33333333-3333-3333-3333-333333333333"),
                    email="dupe-probe@example.com",
                    name="First",
                    password_hash=hash_password("testpassword123"),
                )
            )
            await uow.flush()

        with pytest.raises(IntegrityError):
            await _flush_duplicate(session)
        # Recover the session and prove it works again.
        async with UnitOfWork(session=session) as uow:
            await uow.rollback()
            uow.session.add(
                User(
                    id=__import__("uuid").UUID("55555555-5555-5555-5555-555555555555"),
                    email="fresh-probe@example.com",
                    name="Third",
                    password_hash=hash_password("testpassword123"),
                )
            )
            await uow.flush()

        stmt = select(User).where(User.email == "fresh-probe@example.com")
        result = await session.execute(stmt)
        assert result.scalar_one_or_none() is not None


async def test_connection_acquisition_failure_propagates_and_recovers(monkeypatch) -> None:
    from app.database import unit_of_work as uow_module

    bad = OperationalError("SELECT 1", {}, Exception("cannot acquire connection"))

    def broken_factory() -> None:
        raise bad

    monkeypatch.setattr(uow_module, "async_session_factory", broken_factory)
    with pytest.raises(OperationalError):
        async with UnitOfWork() as uow:
            await uow.session.execute(select(1))

    # Recovery: the real factory still yields a usable session.
    async with TestSessionLocal() as session:

        def good_factory() -> object:
            return session

        monkeypatch.setattr(uow_module, "async_session_factory", good_factory)
        async with UnitOfWork() as uow:
            result = await uow.session.execute(select(1))
            assert result.scalar_one() == 1


async def test_uow_failed_commit_rolls_back_before_retry(monkeypatch) -> None:
    """UoW commit retry must roll back the aborted PG transaction in between."""
    monkeypatch.setattr(settings, "DATABASE_RETRY_ATTEMPTS", 1)
    monkeypatch.setattr(settings, "DATABASE_RETRY_BASE_DELAY", 0.001)
    monkeypatch.setattr(settings, "DATABASE_RETRY_MAX_DELAY", 0.01)
    monkeypatch.setattr(settings, "DATABASE_RETRY_JITTER", 0.0)

    session = AsyncMock()
    session.commit.side_effect = [
        _make_dbapi_error("40001"),
        None,
    ]

    with patch("asyncio.sleep", new_callable=AsyncMock):
        async with UnitOfWork(session=session):
            pass

    assert session.commit.await_count == 2
    assert session.rollback.await_count == 1
    session.close.assert_awaited_once()


async def test_uow_failed_commit_exhaustion_propagates_and_closes(monkeypatch) -> None:
    monkeypatch.setattr(settings, "DATABASE_RETRY_ATTEMPTS", 1)
    monkeypatch.setattr(settings, "DATABASE_RETRY_BASE_DELAY", 0.001)
    monkeypatch.setattr(settings, "DATABASE_RETRY_MAX_DELAY", 0.01)
    monkeypatch.setattr(settings, "DATABASE_RETRY_JITTER", 0.0)

    session = AsyncMock()
    session.commit.side_effect = _make_dbapi_error("40P01")

    with patch("asyncio.sleep", new_callable=AsyncMock), pytest.raises(DBAPIError):
        async with UnitOfWork(session=session):
            pass

    assert session.commit.await_count == 2
    assert session.rollback.await_count == 1
    session.close.assert_awaited_once()


async def test_retry_hook_only_exercised_on_transient_failure(monkeypatch) -> None:
    """Non-transient failures must not invoke the rollback hook or retry."""
    hooks = []

    async def failing() -> None:
        raise _make_dbapi_error("23505")

    async def on_retry(attempt: int) -> None:
        hooks.append(attempt)

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep, pytest.raises(DBAPIError):
        await retry_on_db_failure(
            failing,
            max_retries=1,
            base_delay=0.001,
            jitter=0.0,
            on_retry=on_retry,
        )
    assert hooks == []
    mock_sleep.assert_not_called()
