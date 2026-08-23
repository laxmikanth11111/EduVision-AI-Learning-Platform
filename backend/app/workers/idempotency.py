from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from datetime import timedelta
from enum import Enum
from functools import wraps
from typing import Any, TypeVar

from celery import Task
from redis.asyncio import Redis

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")

IDEMPOTENCY_NAMESPACE = "idempotency"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskIdempotencyService:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    def _build_key(self, task_name: str, task_id: str) -> str:
        return f"{IDEMPOTENCY_NAMESPACE}:{task_name}:{task_id}"

    def _build_lock_key(self, task_name: str, task_id: str) -> str:
        return f"{IDEMPOTENCY_NAMESPACE}:lock:{task_name}:{task_id}"

    async def is_duplicate(self, task_name: str, task_id: str) -> bool:
        key = self._build_key(task_name, task_id)
        exists = await self._redis.exists(key)
        return exists > 0

    async def mark_started(
        self,
        task_name: str,
        task_id: str,
        ttl: int | None = None,
    ) -> None:
        key = self._build_key(task_name, task_id)
        await self._redis.set(
            key,
            TaskStatus.RUNNING.value,
            ex=ttl or settings.CELERY_IDEMPOTENCY_TTL,
        )

    async def mark_completed(
        self,
        task_name: str,
        task_id: str,
        result: Any = None,
        ttl: int | None = None,
    ) -> None:
        key = self._build_key(task_name, task_id)
        payload = json.dumps(
            {
                "status": TaskStatus.COMPLETED.value,
                "result": result,
                "timestamp": time.time(),
            },
            default=str,
        )
        await self._redis.set(
            key,
            payload,
            ex=ttl or settings.CELERY_IDEMPOTENCY_TTL,
        )

    async def mark_failed(
        self,
        task_name: str,
        task_id: str,
        error: str,
        ttl: int | None = None,
    ) -> None:
        key = self._build_key(task_name, task_id)
        payload = json.dumps(
            {
                "status": TaskStatus.FAILED.value,
                "error": error,
                "timestamp": time.time(),
            },
            default=str,
        )
        await self._redis.set(
            key,
            payload,
            ex=ttl or settings.CELERY_IDEMPOTENCY_TTL,
        )

    async def get_status(
        self,
        task_name: str,
        task_id: str,
    ) -> TaskStatus | None:
        key = self._build_key(task_name, task_id)
        value = await self._redis.get(key)

        if value is None:
            return None

        try:
            parsed = json.loads(value)
            return TaskStatus(parsed["status"])
        except (json.JSONDecodeError, KeyError, ValueError):
            return TaskStatus(value)

    async def acquire_lock(
        self,
        task_name: str,
        task_id: str,
        ttl: int = 30,
    ) -> bool:
        lock_key = self._build_lock_key(task_name, task_id)
        acquired = await self._redis.set(
            lock_key,
            "1",
            nx=True,
            ex=ttl,
        )
        return acquired is not None

    async def release_lock(
        self,
        task_name: str,
        task_id: str,
    ) -> None:
        lock_key = self._build_lock_key(task_name, task_id)
        await self._redis.delete(lock_key)

    async def cleanup(
        self,
        task_name: str,
        task_id: str,
    ) -> None:
        key = self._build_key(task_name, task_id)
        lock_key = self._build_lock_key(task_name, task_id)
        await self._redis.delete(key, lock_key)

    async def generate_idempotency_key(
        self,
        task_name: str,
        *args: Any,
        **kwargs: Any,
    ) -> str:
        raw = (
            f"{task_name}:"
            f"{json.dumps(args, default=str)}:"
            f"{json.dumps(kwargs, default=str)}"
        )
        return hashlib.sha256(raw.encode()).hexdigest()


def idempotent_task(
    task_base: type[Task],
    idempotency_service: TaskIdempotencyService | None = None,
    ttl: timedelta | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(
            self: Task,
            *args: Any,
            **kwargs: Any,
        ) -> Any:
            task_id = str(self.request.id)
            task_name = str(self.name)

            service = idempotency_service

            if service is None:
                import asyncio

                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None

                if loop and loop.is_running():
                    logger.warning(
                        "idempotency_service_not_available_async",
                        task_name=task_name,
                        task_id=task_id,
                    )
                    return func(self, *args, **kwargs)

            assert service is not None

            try:
                import asyncio

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                if loop.run_until_complete(
                    service.is_duplicate(task_name, task_id)
                ):
                    logger.info(
                        "idempotency_duplicate_task_skipped",
                        task_name=task_name,
                        task_id=task_id,
                    )

                    status = loop.run_until_complete(
                        service.get_status(task_name, task_id)
                    )

                    return {
                        "status": "skipped",
                        "reason": "duplicate",
                        "previous_status": (
                            status.value if status else None
                        ),
                    }

                lock_acquired = loop.run_until_complete(
                    service.acquire_lock(task_name, task_id)
                )

                if not lock_acquired:
                    logger.info(
                        "idempotency_task_already_running",
                        task_name=task_name,
                        task_id=task_id,
                    )

                    return {
                        "status": "skipped",
                        "reason": "already_running",
                    }

                try:
                    task_ttl = (
                        int(ttl.total_seconds())
                        if ttl is not None
                        else None
                    )

                    loop.run_until_complete(
                        service.mark_started(
                            task_name,
                            task_id,
                            task_ttl,
                        )
                    )

                    result = func(self, *args, **kwargs)

                    loop.run_until_complete(
                        service.mark_completed(
                            task_name,
                            task_id,
                            result,
                            task_ttl,
                        )
                    )

                    return result

                except Exception as exc:
                    loop.run_until_complete(
                        service.mark_failed(
                            task_name,
                            task_id,
                            str(exc),
                        )
                    )
                    raise

                finally:
                    loop.run_until_complete(
                        service.release_lock(
                            task_name,
                            task_id,
                        )
                    )
                    loop.close()

            except Exception:
                raise

        return wrapper

    return decorator
