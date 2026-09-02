from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

import app.api.v1.health as health_module
from app.schemas.health import ComponentHealth


@pytest.fixture(autouse=True)
def _healthy_celery() -> None:
    """Pin the worker check so DB/Redis/Storage branches drive the result."""
    with patch.object(
        health_module,
        "_check_celery",
        new=AsyncMock(return_value=ComponentHealth(status="healthy", details={})),
    ):
        yield


@pytest.mark.asyncio
async def test_liveness_probe(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "alive"
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_readiness_probe(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["checks"]["database"]["status"] == "healthy"
    assert data["checks"]["redis"]["status"] == "healthy"
    assert data["checks"]["storage"]["status"] == "healthy"


@pytest.mark.asyncio
async def test_readiness_not_ready_when_database_connection_raises(client: AsyncClient) -> None:
    with patch.object(
        health_module,
        "check_database_connection",
        new=AsyncMock(side_effect=RuntimeError("db down")),
    ):
        response = await client.get("/api/v1/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "not_ready"
    assert data["checks"]["database"]["status"] == "unhealthy"
    assert data["checks"]["database"]["details"]["error"] == "database connection failed"


@pytest.mark.asyncio
async def test_readiness_not_ready_when_database_returns_false(client: AsyncClient) -> None:
    with patch.object(
        health_module,
        "check_database_connection",
        new=AsyncMock(return_value=False),
    ):
        response = await client.get("/api/v1/health/ready")
    data = response.json()
    assert data["status"] == "not_ready"
    assert data["checks"]["database"]["status"] == "unhealthy"


@pytest.mark.asyncio
async def test_readiness_not_ready_when_redis_down(
    client: AsyncClient,
    mock_redis: AsyncMock,
) -> None:
    mock_redis.ping = AsyncMock(side_effect=ConnectionError("redis down"))
    response = await client.get("/api/v1/health/ready")
    data = response.json()
    assert data["status"] == "not_ready"
    assert data["checks"]["redis"]["status"] == "unhealthy"
    assert data["checks"]["redis"]["details"]["error"] == "redis connection failed"


@pytest.mark.asyncio
async def test_readiness_not_ready_when_storage_down(
    client: AsyncClient,
    mock_storage,
) -> None:
    mock_storage.list_buckets = AsyncMock(side_effect=RuntimeError("s3 down"))
    response = await client.get("/api/v1/health/ready")
    data = response.json()
    assert data["status"] == "not_ready"
    assert data["checks"]["storage"]["status"] == "unhealthy"
    assert data["checks"]["storage"]["details"]["error"] == "storage connection failed"


@pytest.mark.asyncio
async def test_health_degraded_when_redis_down(
    client: AsyncClient,
    mock_redis: AsyncMock,
) -> None:
    mock_redis.ping = AsyncMock(side_effect=ConnectionError("redis down"))
    response = await client.get("/api/v1/health")
    data = response.json()
    assert data["status"] == "degraded"
    assert data["checks"]["redis"]["status"] == "unhealthy"


@pytest.mark.asyncio
async def test_health_check_returns_valid_structure(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["app_name"] == "EduVision AI"
    assert data["app_version"] == "1.0.0"
    assert "timestamp" in data
    assert "response_time_ms" in data
    assert "checks" in data
    assert "database" in data["checks"]
    assert "redis" in data["checks"]
    assert "storage" in data["checks"]


@pytest.mark.asyncio
async def test_metrics_endpoint_prometheus_format(client: AsyncClient) -> None:
    response = await client.get("/api/v1/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert "http_requests_total" in body
    assert "# TYPE http_requests_total counter" in body
    assert "# TYPE http_requests_duration_seconds histogram" in body
