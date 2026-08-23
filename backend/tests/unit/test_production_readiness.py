from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.v1.health import health_router
from app.core.config import Settings
from app.middleware.rate_limit import RateLimitMiddleware


def test_production_secret_validation():
    """Verify that default secrets raise ValidationError when APP_ENV is production."""
    with pytest.raises(ValidationError):
        Settings(
            APP_ENV="production",
            APP_SECRET_KEY="CHANGE-ME-TO-A-RANDOM-SECRET-KEY-32CHARS",
            CSRF_SECRET="CHANGE-ME-CSRF-SECRET",
        )


def test_production_database_secret_validation():
    """Verify default eduvision:eduvision database credentials raise error in production."""
    with pytest.raises(ValidationError):
        Settings(
            APP_ENV="production",
            APP_SECRET_KEY="a-very-long-production-secret-key-32chars!",
            CSRF_SECRET="a-very-long-csrf-production-secret!",
            DATABASE_URL="postgresql+asyncpg://eduvision:eduvision@localhost:5432/eduvision",
        )


def test_rate_limit_middleware_trusted_proxy_parsing():
    """Verify rate limit middleware correctly parses trusted proxy subnets."""
    app = FastAPI()
    mw = RateLimitMiddleware(
        app,
        trusted_proxies={"127.0.0.1", "10.0.0.0/8"},
    )
    assert mw._is_trusted_proxy("127.0.0.1") is True
    assert mw._is_trusted_proxy("10.1.2.3") is True
    assert mw._is_trusted_proxy("8.8.8.8") is False


@pytest.mark.asyncio
async def test_health_endpoints(client: Any):
    """Verify health endpoints return valid responses."""
    response = await client.get("/api/v1/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "alive"

    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "checks" in data
    assert "celery" in data["checks"]

