from __future__ import annotations

import pytest
from httpx import AsyncClient


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
    assert "status" in data
    assert "checks" in data


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
    assert "# TYPE http_requests_duration_seconds_count counter" in body
