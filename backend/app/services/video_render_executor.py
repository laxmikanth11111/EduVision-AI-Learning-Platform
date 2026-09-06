"""Render execution seam for the async video runtime (P16).

``VIDEO_RENDER_EXECUTOR`` selects between:
  - ``celery`` — ``send_task("eduvision.videos.render_project")`` on the videos
    queue; used in real multi-worker deployments.
  - ``inline`` — an ``asyncio`` background task in the API process; used by
    default and by all tests via conftest, keeping renders non-blocking with no
    broker.
"""

from __future__ import annotations

import asyncio
import threading
import uuid

from app.core.config import settings
from app.core.logging import get_logger
from app.database.unit_of_work import UnitOfWork

logger = get_logger(__name__)


class VideoRenderExecutor:
    def dispatch(self, user_id: uuid.UUID, public_id: str) -> None:
        mode = settings.VIDEO_RENDER_EXECUTOR.strip().lower()
        if mode == "celery":
            self._dispatch_celery(user_id, public_id)
            return
        self._dispatch_inline(user_id, public_id)

    def _dispatch_celery(self, user_id: uuid.UUID, public_id: str) -> None:
        try:
            from app.workers.celery_app import celery_app

            celery_app.send_task(
                "eduvision.videos.render_project",
                args=[str(user_id), public_id],
                queue="videos",
            )
        except Exception as exc:
            logger.exception(
                "video_render_celery_dispatch_failed", project=public_id
            )
            self._mark_failed_best_effort(user_id, public_id, str(exc))

    def _dispatch_inline(self, user_id: uuid.UUID, public_id: str) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None:
            loop.create_task(self._run_inline(user_id, public_id))
            return

        threading.Thread(
            target=lambda: asyncio.run(self._run_inline(user_id, public_id)),
            daemon=True,
            name=f"video-render-{public_id}",
        ).start()

    async def _run_inline(self, user_id: uuid.UUID, public_id: str) -> None:
        try:
            from app.services.video_project_service import VideoProjectService

            async with UnitOfWork() as uow:
                service = VideoProjectService(uow.session)
                record = await service.get_owned(user_id, public_id)
                if record is None:
                    logger.warning("video_render_inline_orphan", project=public_id)
                    return
                await service.render_now(record)
        except Exception:
            logger.exception("video_render_inline_failed", project=public_id)

    def _mark_failed_best_effort(
        self,
        user_id: uuid.UUID,
        public_id: str,
        error: str,
    ) -> None:
        async def _apply() -> None:
            from app.models.video_project import VideoRenderStatus
            from app.services.video_project_service import VideoProjectService

            async with UnitOfWork() as uow:
                service = VideoProjectService(uow.session)
                record = await service.get_owned(user_id, public_id)
                if record is None:
                    return
                record.status = VideoRenderStatus.FAILED
                record.error = (error or "Render dispatch failed")[:1000]
                await uow.commit()

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None:
            loop.create_task(_apply())
        else:
            threading.Thread(
                target=lambda: asyncio.run(_apply()),
                daemon=True,
                name=f"video-render-mark-failed-{public_id}",
            ).start()
