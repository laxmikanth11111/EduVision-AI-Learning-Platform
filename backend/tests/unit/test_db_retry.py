from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.exc import DBAPIError, OperationalError

from app.database.retry import db_retry, is_transient_pg_error, retry_on_db_failure

pytestmark = pytest.mark.asyncio


def _make_dbapi_error(pgcode: str | None) -> DBAPIError:
    orig = Exception("DB Error")
    if pgcode is not None:
        orig.pgcode = pgcode
    exc = DBAPIError("statement", {}, orig)
    return exc


async def test_is_transient_pg_error_serialization() -> None:
    exc = _make_dbapi_error("40001")
    assert is_transient_pg_error(exc) is True


async def test_is_transient_pg_error_deadlock() -> None:
    exc = _make_dbapi_error("40P01")
    assert is_transient_pg_error(exc) is True


async def test_is_transient_pg_error_non_transient() -> None:
    exc = _make_dbapi_error("23505")  # unique violation
    assert is_transient_pg_error(exc) is False


async def test_is_transient_pg_error_no_code() -> None:
    exc = _make_dbapi_error(None)
    assert is_transient_pg_error(exc) is False


async def test_retry_on_db_failure_success_on_second_attempt() -> None:
    attempts = 0

    async def sample_func() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise _make_dbapi_error("40001")
        return "success"

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = await retry_on_db_failure(
            sample_func,
            max_retries=3,
            base_delay=0.01,
            max_delay=0.1,
            jitter=0.0,
        )
        assert result == "success"
        assert attempts == 2
        mock_sleep.assert_called_once()


async def test_retry_on_db_failure_non_transient_raises_immediately() -> None:
    attempts = 0

    async def sample_func() -> str:
        nonlocal attempts
        attempts += 1
        raise _make_dbapi_error("23505")

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        with pytest.raises(DBAPIError):
            await retry_on_db_failure(
                sample_func,
                max_retries=3,
                base_delay=0.01,
            )
        assert attempts == 1
        mock_sleep.assert_not_called()


async def test_retry_on_db_failure_exhaustion() -> None:
    attempts = 0

    async def sample_func() -> str:
        nonlocal attempts
        attempts += 1
        raise _make_dbapi_error("40P01")

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        with pytest.raises(DBAPIError):
            await retry_on_db_failure(
                sample_func,
                max_retries=2,
                base_delay=0.01,
                jitter=0.0,
            )
        assert attempts == 3  # initial + 2 retries
        assert mock_sleep.call_count == 2


async def test_db_retry_decorator() -> None:
    attempts = 0

    @db_retry(max_retries=2, base_delay=0.01, jitter=0.0)
    async def decorated_func(val: int) -> int:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise _make_dbapi_error("40001")
        return val * 2

    with patch("asyncio.sleep", new_callable=AsyncMock):
        res = await decorated_func(21)
        assert res == 42
        assert attempts == 2
