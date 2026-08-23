from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.exc import DBAPIError

from app.database.retry import is_transient_pg_error, retry_on_db_failure


class FakeDBAPIError(DBAPIError):
    def __init__(self, pgcode: str | None) -> None:
        orig_exc = type("Orig", (Exception,), {"pgcode": pgcode})("test error") if pgcode else Exception("test error")
        super().__init__("statement", {}, orig_exc)


class TestIsTransientPgError:
    def test_serialization_failure(self) -> None:
        error = FakeDBAPIError("40001")
        assert is_transient_pg_error(error) is True

    def test_deadlock_detected(self) -> None:
        error = FakeDBAPIError("40P01")
        assert is_transient_pg_error(error) is True

    def test_non_transient_error(self) -> None:
        error = FakeDBAPIError("23505")
        assert is_transient_pg_error(error) is False

    def test_no_orig(self) -> None:
        error = DBAPIError("stmt", {}, Exception("test"))
        assert is_transient_pg_error(error) is False


class TestRetryOnDbFailure:
    async def test_success_first_attempt(self) -> None:
        func = AsyncMock(return_value="success")
        result = await retry_on_db_failure(func, max_retries=3)
        assert result == "success"
        assert func.call_count == 1

    async def test_retry_then_success(self) -> None:
        call_count = 0

        async def flaky_func() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise FakeDBAPIError("40001")
            return "success"

        result = await retry_on_db_failure(flaky_func, max_retries=3, base_delay=0.01)
        assert result == "success"
        assert call_count == 3

    async def test_exhaust_retries(self) -> None:
        func = AsyncMock(side_effect=FakeDBAPIError("40001"))

        with pytest.raises(DBAPIError):
            await retry_on_db_failure(func, max_retries=2, base_delay=0.01)

        assert func.call_count == 3

    async def test_non_retryable_error_raises_immediately(self) -> None:
        func = AsyncMock(side_effect=FakeDBAPIError("23505"))

        with pytest.raises(DBAPIError):
            await retry_on_db_failure(func, max_retries=3, base_delay=0.01)

        assert func.call_count == 1
