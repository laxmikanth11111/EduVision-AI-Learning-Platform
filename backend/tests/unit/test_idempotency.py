from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.workers.idempotency import TaskIdempotencyService, TaskStatus


class TestTaskIdempotencyService:
    @pytest.fixture
    def service(self) -> TaskIdempotencyService:
        redis = AsyncMock()
        redis.get.return_value = None
        redis.set.return_value = True
        redis.exists.return_value = 0
        redis.delete.return_value = 1
        return TaskIdempotencyService(redis)

    def test_build_key(self, service: TaskIdempotencyService) -> None:
        key = service._build_key("test_task", "1234")
        assert key == "idempotency:test_task:1234"

    def test_build_lock_key(self, service: TaskIdempotencyService) -> None:
        key = service._build_lock_key("test_task", "1234")
        assert key == "idempotency:lock:test_task:1234"

    @pytest.mark.asyncio
    async def test_is_duplicate_not_found(self, service: TaskIdempotencyService) -> None:
        service._redis.exists.return_value = 0
        result = await service.is_duplicate("task", "id")
        assert result is False

    @pytest.mark.asyncio
    async def test_is_duplicate_found(self, service: TaskIdempotencyService) -> None:
        service._redis.exists.return_value = 1
        result = await service.is_duplicate("task", "id")
        assert result is True

    @pytest.mark.asyncio
    async def test_mark_started(self, service: TaskIdempotencyService) -> None:
        await service.mark_started("task", "id")
        service._redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_mark_completed(self, service: TaskIdempotencyService) -> None:
        await service.mark_completed("task", "id", {"result": "ok"})
        service._redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_mark_failed(self, service: TaskIdempotencyService) -> None:
        await service.mark_failed("task", "id", "error occurred")
        service._redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_status_running(self, service: TaskIdempotencyService) -> None:
        service._redis.get.return_value = "running"
        status = await service.get_status("task", "id")
        assert status == TaskStatus.RUNNING

    @pytest.mark.asyncio
    async def test_get_status_none(self, service: TaskIdempotencyService) -> None:
        service._redis.get.return_value = None
        status = await service.get_status("task", "id")
        assert status is None

    @pytest.mark.asyncio
    async def test_acquire_lock_success(self, service: TaskIdempotencyService) -> None:
        service._redis.set.return_value = "OK"
        acquired = await service.acquire_lock("task", "id")
        assert acquired is True

    @pytest.mark.asyncio
    async def test_acquire_lock_failure(self, service: TaskIdempotencyService) -> None:
        service._redis.set.return_value = None
        acquired = await service.acquire_lock("task", "id")
        assert acquired is False

    @pytest.mark.asyncio
    async def test_cleanup(self, service: TaskIdempotencyService) -> None:
        await service.cleanup("task", "id")
        assert service._redis.delete.call_count == 1

    @pytest.mark.asyncio
    async def test_generate_idempotency_key(self, service: TaskIdempotencyService) -> None:
        key = await service.generate_idempotency_key("task", "arg1", kwarg1="val1")
        assert isinstance(key, str)
        assert len(key) == 64
