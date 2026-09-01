from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.v1.health import health_router
from app.core.config import Settings
from app.middleware.rate_limit import RateLimitMiddleware


def _valid_production_settings(**overrides: Any) -> dict[str, Any]:
    """A production Settings kwargs set that passes every production guard."""
    base: dict[str, Any] = {
        "APP_ENV": "production",
        "APP_DEBUG": False,
        "APP_SECRET_KEY": "a-very-long-production-secret-key-32chars!",
        "CSRF_SECRET": "a-very-long-csrf-production-secret!",
        "DATABASE_URL": "postgresql+asyncpg://app:app@db:5432/eduvision",
        "DATABASE_SYNC_URL": "postgresql://app:app@db:5432/eduvision",
        "STORAGE_PROVIDER": "local",
        "AI_PROVIDER": "local",
        "LOG_LEVEL": "INFO",
        "JWT_SECRET_KEY": "a-very-long-jwt-secret-key-for-tokens-32chars!",
        "LIFESPAN_FAIL_FAST_ON_MIGRATION_ERROR": True,
        "REDIS_URL": "redis://redis.example.com:6379/0",
        "CELERY_BROKER_URL": "redis://broker.example.com:6379/1",
        "CELERY_RESULT_BACKEND": "redis://broker.example.com:6379/2",
    }
    base.update(overrides)
    return base


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


def test_production_debug_blocked():
    """APP_DEBUG=True must fail fast in production."""
    with pytest.raises(ValidationError):
        Settings(
            APP_ENV="production",
            APP_DEBUG=True,
            APP_SECRET_KEY="a-very-long-production-secret-key-32chars!",
            CSRF_SECRET="a-very-long-csrf-production-secret!",
            DATABASE_URL="postgresql+asyncpg://app:app@db:5432/eduvision",
            DATABASE_SYNC_URL="postgresql://app:app@db:5432/eduvision",
            STORAGE_PROVIDER="local",
            AI_PROVIDER="local",
        )


def test_production_short_secret_blocked():
    """APP_SECRET_KEY shorter than 32 chars must fail fast in production."""
    with pytest.raises(ValidationError):
        Settings(
            APP_ENV="production",
            APP_DEBUG=False,
            APP_SECRET_KEY="too-short",
            CSRF_SECRET="a-very-long-csrf-production-secret!",
            DATABASE_URL="postgresql+asyncpg://app:app@db:5432/eduvision",
            STORAGE_PROVIDER="local",
            AI_PROVIDER="local",
        )


def test_production_csrf_secret_blocked():
    """A CHANGE-ME CSRF_SECRET must fail fast in production."""
    with pytest.raises(ValidationError):
        Settings(
            APP_ENV="production",
            APP_DEBUG=False,
            APP_SECRET_KEY="a-very-long-production-secret-key-32chars!",
            CSRF_SECRET="CHANGE-ME-CSRF-SECRET",
            DATABASE_URL="postgresql+asyncpg://app:app@db:5432/eduvision",
            STORAGE_PROVIDER="local",
            AI_PROVIDER="local",
        )


def test_production_ai_key_required_for_nonlocal_provider():
    """A non-local AI_PROVIDER requires AI_API_KEY in production."""
    with pytest.raises(ValidationError):
        Settings(
            APP_ENV="production",
            APP_DEBUG=False,
            APP_SECRET_KEY="a-very-long-production-secret-key-32chars!",
            CSRF_SECRET="a-very-long-csrf-production-secret!",
            DATABASE_URL="postgresql+asyncpg://app:app@db:5432/eduvision",
            STORAGE_PROVIDER="local",
            AI_PROVIDER="gemini",
            AI_API_KEY=None,
        )


def test_production_local_ai_provider_allowed_without_key():
    """'local' AI_PROVIDER must not require AI_API_KEY in production."""
    settings = Settings(**_valid_production_settings())
    assert settings.AI_PROVIDER == "local"


def test_production_log_level_debug_blocked():
    """LOG_LEVEL=DEBUG must fail fast in production."""
    with pytest.raises(ValidationError):
        Settings(**_valid_production_settings(LOG_LEVEL="DEBUG"))


def test_production_jwt_secret_required():
    """A missing JWT_SECRET_KEY must fail fast in production."""
    with pytest.raises(ValidationError):
        Settings(**_valid_production_settings(JWT_SECRET_KEY=None))


def test_production_jwt_secret_too_short():
    """A JWT_SECRET_KEY shorter than 32 chars must fail fast in production."""
    with pytest.raises(ValidationError):
        Settings(**_valid_production_settings(JWT_SECRET_KEY="too-short"))


def test_production_jwt_secret_must_differ_from_app_secret():
    """JWT_SECRET_KEY equal to APP_SECRET_KEY must fail fast in production."""
    with pytest.raises(ValidationError):
        Settings(
            **_valid_production_settings(
                JWT_SECRET_KEY="a-very-long-production-secret-key-32chars!",
            )
        )


def test_production_lifespan_fail_fast_required():
    """LIFESPAN_FAIL_FAST_ON_MIGRATION_ERROR must be True in production."""
    with pytest.raises(ValidationError):
        Settings(**_valid_production_settings(LIFESPAN_FAIL_FAST_ON_MIGRATION_ERROR=False))


def test_production_redis_localhost_blocked():
    """An unauthenticated localhost REDIS_URL must fail fast in production."""
    with pytest.raises(ValidationError):
        Settings(**_valid_production_settings(REDIS_URL="redis://localhost:6379/0"))


def test_production_celery_broker_localhost_blocked():
    """An unauthenticated localhost CELERY_BROKER_URL must fail fast in production."""
    with pytest.raises(ValidationError):
        Settings(**_valid_production_settings(CELERY_BROKER_URL="redis://127.0.0.1:6379/1"))


def test_production_celery_result_backend_localhost_blocked():
    """An unauthenticated localhost CELERY_RESULT_BACKEND must fail fast in production."""
    with pytest.raises(ValidationError):
        Settings(**_valid_production_settings(CELERY_RESULT_BACKEND="redis://localhost:6379/2"))


def test_production_redis_localhost_with_password_allowed():
    """Password-protected loopback Redis is an allowed single-box deployment."""
    settings = Settings(
        **_valid_production_settings(REDIS_URL="redis://:secret@localhost:6379/0"),
    )
    assert settings.REDIS_URL.startswith("redis://:secret@localhost")


def test_production_s3_credentials_required():
    """STORAGE_PROVIDER=s3 without S3 credentials must fail fast in production."""
    with pytest.raises(ValidationError):
        Settings(
            **_valid_production_settings(
                STORAGE_PROVIDER="s3",
                S3_ENDPOINT_URL="https://s3.example.com",
                S3_ACCESS_KEY_ID=None,
                S3_SECRET_ACCESS_KEY=None,
            )
        )


def test_production_valid_settings_accept():
    """A fully-valid production settings object must construct cleanly."""
    settings = Settings(**_valid_production_settings())
    assert settings.is_production
    assert settings.LOG_LEVEL == "INFO"


def test_production_s3_requires_endpoint_url():
    """STORAGE_PROVIDER=s3 without S3_ENDPOINT_URL must fail fast outside test env."""
    with pytest.raises(ValidationError):
        Settings(
            **_valid_production_settings(
                STORAGE_PROVIDER="s3",
                S3_ENDPOINT_URL=None,
                S3_ACCESS_KEY_ID="key",
                S3_SECRET_ACCESS_KEY="secret",
            )
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

