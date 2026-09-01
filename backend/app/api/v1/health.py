from __future__ import annotations

import time
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from redis.asyncio import Redis

from app.core.config import settings
from app.core.logging import get_logger
from app.database.session import check_database_connection
from app.schemas.health import (
    ComponentHealth,
    HealthCheckResponse,
    LivenessResponse,
    ReadinessResponse,
)
from app.storage.base import StorageBackend
from app.storage.factory import get_storage_backend
from app.workers.redis_client import get_redis_client

logger = get_logger(__name__)

health_router = APIRouter(tags=["Health"])


@health_router.get(
    "/health",
    response_model=HealthCheckResponse,
    summary="Unified health check",
)
async def health_check(
    redis: Redis = Depends(get_redis_client),
    storage: StorageBackend = Depends(get_storage_backend),
) -> HealthCheckResponse:
    start = time.monotonic()

    database_check = await _check_database()
    redis_check = await _check_redis(redis)
    storage_check = await _check_storage(storage)
    ai_check = _check_ai_provider()
    celery_check = await _check_celery()
    checks = {
        "database": database_check,
        "redis": redis_check,
        "storage": storage_check,
        "ai_provider": ai_check,
        "celery": celery_check,
    }

    status = "healthy"
    if any(c.status != "healthy" for c in checks.values()):
        status = "degraded"

    elapsed = time.monotonic() - start

    return HealthCheckResponse(
        status=status,
        app_name=settings.APP_NAME,
        app_version=settings.APP_VERSION,
        environment=settings.APP_ENV,
        timestamp=datetime.now(UTC),
        response_time_ms=round(elapsed * 1000, 2),
        checks=checks,  # type: ignore
    )


@health_router.get("/health/live", response_model=LivenessResponse, summary="Liveness probe")
async def liveness() -> LivenessResponse:
    return LivenessResponse(
        status="alive",
        timestamp=datetime.now(UTC),
    )


@health_router.get("/health/ready", response_model=ReadinessResponse, summary="Readiness probe")
async def readiness(
    redis: Redis = Depends(get_redis_client),
    storage: StorageBackend = Depends(get_storage_backend),
) -> ReadinessResponse:
    db_check = await _check_database()
    redis_check = await _check_redis(redis)
    storage_check = await _check_storage(storage)
    checks = {"database": db_check, "redis": redis_check, "storage": storage_check}

    ready = all(c.status == "healthy" for c in checks.values())

    return ReadinessResponse(
        status="ready" if ready else "not_ready",
        checks=checks,
    )


async def _check_database() -> ComponentHealth:
    try:
        db_healthy = await check_database_connection()
        return ComponentHealth(
            status="healthy" if db_healthy else "unhealthy",
            details={"database_type": _database_dialect()},
        )
    except Exception as e:
        logger.error("health_check_db_failed", error=str(e))
        return ComponentHealth(status="unhealthy", details={"error": "database connection failed"})


def _database_dialect() -> str:
    """Report the real engine dialect rather than assuming PostgreSQL."""
    try:
        from app.database.session import engine

        return engine.dialect.name
    except Exception:
        return "unknown"


async def _check_redis(redis: Redis) -> ComponentHealth:
    try:
        await redis.ping()
        info = await redis.info("server")
        return ComponentHealth(
            status="healthy",
            details={"redis_version": info.get("redis_version", "unknown")},
        )
    except Exception as e:
        logger.error("health_check_redis_failed", error=str(e))
        return ComponentHealth(status="unhealthy", details={"error": "redis connection failed"})


async def _check_storage(storage: StorageBackend) -> ComponentHealth:
    try:
        buckets = await storage.list_buckets()
        return ComponentHealth(
            status="healthy",
            details={
                "provider": settings.STORAGE_PROVIDER,
                "buckets": [b["name"] for b in buckets],
            },
        )
    except Exception as e:
        logger.error("health_check_storage_failed", error=str(e))
        return ComponentHealth(status="unhealthy", details={"error": "storage connection failed"})


def _check_ai_provider() -> ComponentHealth:
    provider = settings.AI_PROVIDER or "local"
    configured = True if provider == "local" else bool(settings.AI_API_KEY)
    return ComponentHealth(
        status="healthy" if configured else "degraded",
        details={
            "provider": provider,
            "configured": configured,
            "model": settings.AI_MODEL or "default",
        },
    )


async def _check_celery() -> ComponentHealth:
    try:
        from app.workers.celery_app import celery_app
        ping_res = celery_app.control.ping(timeout=0.5)
        worker_count = len(ping_res) if ping_res else 0
        return ComponentHealth(
            status="healthy" if worker_count > 0 or settings.CELERY_TASK_ALWAYS_EAGER else "degraded",
            details={
                "active_workers": worker_count,
                "eager_mode": settings.CELERY_TASK_ALWAYS_EAGER,
            },
        )
    except Exception as e:
        logger.error("health_check_celery_failed", error=str(e))
        return ComponentHealth(
            status="degraded",
            details={"error": "celery broker unreachable"},
        )

