from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.animation_router import animation_router
from app.api.v1.animation_runtime_router import animation_runtime_router
from app.api.v1.assistant import assistant_router
from app.api.v1.auth import auth_router
from app.api.v1.effectiveness import effectiveness_router
from app.api.v1.health import health_router
from app.api.v1.metrics import metrics_router
from app.api.v1.player import player_router
from app.api.v1.presentation_folders import folders_router
from app.api.v1.presentations import presentations_router
from app.api.v1.quiz import quiz_router
from app.api.v1.simulation import simulation_router
from app.api.v1.storage import storage_router
from app.api.v1.video_router import video_router
from app.api.v1.video_runtime_router import video_runtime_router
from app.api.v1.visual_canvases import visual_router
from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.database.session import close_database_connections
from app.middleware.exception_handler import setup_exception_handlers
from app.middleware.logging import LoggingMiddleware
from app.middleware.rate_limit import RateLimitMiddleware, parse_route_overrides
from app.middleware.request_id import RequestIDMiddleware
from app.middleware.request_size_limit import RequestSizeLimitMiddleware
from app.middleware.security import SecurityHeadersMiddleware
from app.middleware.timing import TimingMiddleware
from app.middleware.trusted_host import TrustedHostMiddleware
from app.storage.factory import close_storage_backend
from app.workers.redis_client import close_redis_pool

setup_logging()
logger = get_logger(__name__)

_background_tasks: set[asyncio.Task[Any]] = set()


def track_background_task(task: asyncio.Task[Any]) -> None:
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def cancel_background_tasks() -> None:
    if not _background_tasks:
        return
    logger.info("cancelling_background_tasks", count=len(_background_tasks))
    for task in list(_background_tasks):
        task.cancel()
    if _background_tasks:
        await asyncio.wait(_background_tasks, timeout=10.0)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    setup_logging()
    logger.info(
        "application_starting",
        app_name=settings.APP_NAME,
        app_version=settings.APP_VERSION,
        environment=settings.APP_ENV,
    )
    try:
        if settings.AUTO_MIGRATE_ON_STARTUP:
            from alembic import command
            from alembic.config import Config

            alembic_cfg = Config("alembic.ini")
            await asyncio.to_thread(command.upgrade, alembic_cfg, "head")
            logger.info("alembic_migrations_applied")
    except Exception as e:
        if settings.LIFESPAN_FAIL_FAST_ON_MIGRATION_ERROR:
            logger.critical("alembic_migration_failed_aborting", error=str(e))
            raise RuntimeError("Database migration failed at startup; refusing to start") from e
        logger.warning("alembic_migration_failed", error=str(e))
    yield
    logger.info("application_shutting_down")
    await cancel_background_tasks()
    await close_database_connections()
    await close_redis_pool()
    await close_storage_backend()
    logger.info("application_stopped")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-powered Interactive Learning Platform API",
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    openapi_url="/openapi.json" if not settings.is_production else None,
    lifespan=lifespan,
    contact={"name": "EduVision AI Team"},
    license_info={"name": "Proprietary"},
    terms_of_service=None,
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.cors_origins_list
    + ["localhost", "127.0.0.1", "[::1]", "backend", "frontend", "test", "testserver"],
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Response-Time"],
)
app.add_middleware(GZipMiddleware, minimum_size=500)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(TimingMiddleware)
app.add_middleware(RequestSizeLimitMiddleware)
app.add_middleware(
    RateLimitMiddleware,
    default_limit=settings.RATE_LIMIT_DEFAULT,
    default_window=settings.RATE_LIMIT_WINDOW,
    whitelist={
        ip.strip()
        for ip in settings.RATE_LIMIT_WHITELIST.split(",")
        if ip.strip()
    },
    blacklist={
        ip.strip()
        for ip in settings.RATE_LIMIT_BLACKLIST.split(",")
        if ip.strip()
    },
    route_overrides=parse_route_overrides(settings.RATE_LIMIT_ROUTES),
)
app.add_middleware(LoggingMiddleware)
app.add_middleware(RequestIDMiddleware)

setup_exception_handlers(app)

app.include_router(health_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(metrics_router, prefix="/api/v1")
app.include_router(presentations_router, prefix="/api/v1")
app.include_router(storage_router, prefix="/api/v1")
app.include_router(folders_router, prefix="/api/v1")
app.include_router(player_router, prefix="/api/v1")
app.include_router(quiz_router, prefix="/api/v1")
app.include_router(visual_router, prefix="/api/v1")
app.include_router(simulation_router, prefix="/api/v1")
app.include_router(animation_router, prefix="/api/v1")
app.include_router(animation_runtime_router, prefix="/api/v1")
app.include_router(video_router, prefix="/api/v1")
app.include_router(video_runtime_router, prefix="/api/v1")
app.include_router(assistant_router, prefix="/api/v1")
app.include_router(effectiveness_router, prefix="/api/v1")

uploads_dir = settings.upload_path
uploads_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")

frontend_dir = os.path.join(os.getcwd(), "frontend")
os.makedirs(frontend_dir, exist_ok=True)
app.mount(
    "/frontend",
    StaticFiles(directory=frontend_dir, html=True),
    name="frontend",
)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    return Response(
        content=(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
            '<rect width="32" height="32" rx="6" fill="#111111"/>'
            '<path d="M8 22 16 9l8 13z" fill="#f5b942"/>'
            "</svg>"
        ),
        media_type="image/svg+xml",
    )
