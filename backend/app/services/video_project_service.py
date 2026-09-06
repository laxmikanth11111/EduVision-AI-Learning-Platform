"""Video project service layer for the async learner-owned runtime (P16).

Ownership is enforced in every read/write by pairing ``user_id`` with the
``public_id`` (or engine ``video_id``); an unknown or foreign project resolves
to the same 404 so no cross-user ID oracle exists.
"""

from __future__ import annotations

import asyncio
import uuid
from time import monotonic
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.models.video_project import VideoProjectRecord, VideoRenderStatus
from app.observability.metrics import metrics
from app.repositories.video_project_repository import VideoProjectRepository
from app.schemas.video_engine import VideoProject
from app.services.video_render_backend import (
    VideoRenderBackend,
    get_video_render_backend,
)

logger = get_logger(__name__)


def record_to_dict(record: VideoProjectRecord) -> dict[str, Any]:
    return {
        "public_id": record.public_id,
        "video_id": record.video_id,
        "topic": record.topic,
        "status": record.status,
        "progress_percentage": float(record.progress_percentage or 0.0),
        "playable_url": record.playable_url,
        "error": record.error,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


class VideoProjectService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = VideoProjectRepository(session)

    async def create(
        self,
        user_id: uuid.UUID,
        video_id: str,
        topic: str,
        project_data: dict[str, Any],
        *,
        dispatch_render: bool = True,
    ) -> VideoProjectRecord:
        active_count = await self.repo.count_active(user_id)
        if active_count >= settings.VIDEO_RENDER_MAX_CONCURRENT_PER_USER:
            metrics.increment(
                "p16_video_render_concurrency_rejects_total",
                reason="per_user_cap",
            )
            raise ConflictError(
                message="Too many active video renders; retry once the current render completes",
                details={"user_active": active_count, "max": settings.VIDEO_RENDER_MAX_CONCURRENT_PER_USER},
            )
        record = await self.repo.create_project(
            user_id=user_id,
            video_id=video_id,
            topic=topic,
            project_data=project_data,
        )
        await self.session.commit()
        await self.session.refresh(record)
        if dispatch_render:
            self._dispatch(user_id, record.public_id)
        return record

    async def get_owned(
        self,
        user_id: uuid.UUID,
        public_id: str,
    ) -> VideoProjectRecord | None:
        return await self.repo.get_by_user_and_public_id(user_id, public_id)

    async def get_owned_by_video_id(
        self,
        user_id: uuid.UUID,
        video_id: str,
    ) -> VideoProjectRecord | None:
        return await self.repo.get_by_user_and_video_id(user_id, video_id)

    async def list_owned(self, user_id: uuid.UUID) -> list[VideoProjectRecord]:
        return list(await self.repo.list_by_user(user_id))

    async def request_render(
        self,
        user_id: uuid.UUID,
        public_id: str,
        *,
        force: bool = False,
    ) -> VideoProjectRecord:
        record = await self.repo.get_by_user_and_public_id(user_id, public_id)
        if record is None:
            raise NotFoundError(
                message="Video project not found",
                details={"public_id": public_id},
            )
        if record.status in VideoRenderStatus.ACTIVE and not force:
            raise ConflictError(
                message="Video render is already in progress for this project",
                details={"public_id": public_id, "status": record.status},
            )
        active_count = await self.repo.count_active(user_id)
        if active_count >= settings.VIDEO_RENDER_MAX_CONCURRENT_PER_USER and record.status not in VideoRenderStatus.ACTIVE:
            metrics.increment(
                "p16_video_render_concurrency_rejects_total",
                reason="per_user_cap",
            )
            raise ConflictError(
                message="Too many active video renders; retry once the current render completes",
                details={"user_active": active_count, "max": settings.VIDEO_RENDER_MAX_CONCURRENT_PER_USER},
            )

        record.status = VideoRenderStatus.QUEUED
        record.progress_percentage = 0.0
        record.playable_url = None
        record.error = None
        await self.session.commit()
        await self.session.refresh(record)

        self._dispatch(user_id, record.public_id)
        return record

    async def render_now(
        self,
        record: VideoProjectRecord,
        backend: VideoRenderBackend | None = None,
    ) -> VideoProjectRecord:
        """Perform a single render pass on the owning session's row.

        Runs the backend off the event loop with a hard timeout so the request
        path never blocks on FFmpeg/PIL. Mutates ``record`` in place and commits
        ``rendering``/``ready``/``failed`` lifecycle transitions.
        """
        backend = backend or get_video_render_backend()

        record.status = VideoRenderStatus.RENDERING
        record.progress_percentage = 10.0
        record.error = None
        await self.session.commit()
        metrics.increment("p16_video_render_starts_total")

        started = monotonic()
        state: dict[str, float] = {"progress": 10.0}

        def _on_progress(value: float) -> None:
            state["progress"] = max(0.0, min(1.0, float(value))) * 100.0

        finished = None
        try:
            project = self._rebuild_project(record)
            if project is None:
                raise RuntimeError("video blueprint is missing or invalid; re-create the project")
            coro = asyncio.to_thread(backend.render, project, _on_progress)
            finished = await asyncio.wait_for(
                coro,
                timeout=settings.VIDEO_RENDER_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            duration = monotonic() - started
            record.status = VideoRenderStatus.FAILED
            record.error = str(exc)[:1000]
            await self.session.commit()
            await self.session.refresh(record)
            metrics.increment("p16_video_render_failures_total")
            metrics.observe("p16_video_render_duration_seconds", duration, outcome="failed")
            logger.exception("video_render_failed", video_id=record.video_id)
            return record

        if finished is None or not finished.ok:
            record.status = VideoRenderStatus.FAILED
            record.error = (finished.error or "Render failed")[:1000]
            await self.session.commit()
            await self.session.refresh(record)
            metrics.increment("p16_video_render_failures_total")
            metrics.observe("p16_video_render_duration_seconds", duration, outcome="failed")
            return record

        duration = monotonic() - started
        record.status = VideoRenderStatus.READY
        record.progress_percentage = 100.0
        record.playable_url = finished.playable_url
        record.error = None
        await self.session.commit()
        await self.session.refresh(record)
        metrics.increment("p16_video_render_completions_total")
        metrics.observe("p16_video_render_duration_seconds", duration, outcome="success")
        logger.info(
            "video_render_succeeded",
            video_id=record.video_id,
            public_id=record.public_id,
            seconds=round(duration, 3),
        )
        return record

    def _rebuild_project(self, record: VideoProjectRecord) -> VideoProject | None:
        if not record.project_data:
            return None
        try:
            return VideoProject.model_validate(record.project_data)
        except Exception:
            logger.exception("video_project_blueprint_invalid", video_id=record.video_id)
            return None

    @staticmethod
    def _dispatch(user_id: uuid.UUID, public_id: str) -> None:
        from app.services.video_render_executor import VideoRenderExecutor

        VideoRenderExecutor().dispatch(user_id, public_id)
