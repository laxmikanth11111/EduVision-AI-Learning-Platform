from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ComponentHealth(BaseModel):
    status: str = Field(..., pattern="^(healthy|unhealthy|degraded)$")
    details: dict[str, Any] = Field(default_factory=dict)


class HealthChecks(BaseModel):
    database: ComponentHealth
    redis: ComponentHealth
    storage: ComponentHealth
    ai_provider: ComponentHealth | None = None
    celery: ComponentHealth | None = None


class HealthCheckResponse(BaseModel):
    status: str = Field(..., pattern="^(healthy|degraded|unhealthy)$")
    app_name: str
    app_version: str
    environment: str
    timestamp: datetime
    response_time_ms: float
    checks: HealthChecks


class LivenessResponse(BaseModel):
    status: str = Field(..., pattern="^(alive|dead)$")
    timestamp: datetime


class ReadinessResponse(BaseModel):
    status: str = Field(..., pattern="^(ready|not_ready)$")
    checks: dict[str, ComponentHealth]
