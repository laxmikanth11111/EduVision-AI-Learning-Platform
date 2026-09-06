"""Video render worker task (P16).

``eduvision.videos.render_project`` executes a single render pass for one
learner-owned project. Ownership is re-verified inside the service so a row
deleted between enqueue and execution resolves to a graceful no-op instead of a
job failure.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.core.logging import get_logger
from app.database.unit_of_work import UnitOfWork
from app.workers.celery_app import celery_app
from app.workers.tasks import TaskWithDLQ, _run_async

logger = get_logger(__name__)


async def _render_project_async(user_id: uuid.UUID, public_id: str) -> str:
    from app.services.video_project_service import VideoProjectService

    async with UnitOfWork() as uow:
        service = VideoProjectService(uow.session)
        record = await service.get_owned(user_id, public_id)
        if record is None:
            logger.warning("video_render_task_orphan", public_id=public_id)
            return public_id
        await service.render_now(record)
    return public_id


@celery_app.task(
    bind=True,
    base=TaskWithDLQ,
    name="eduvision.videos.render_project",
    max_retries=0,
    acks_late=True,
)
def video_render_task(self: Any, user_id: str, public_id: str) -> str:
    logger.info("video_render_task_started", project=public_id)
    return _run_async(_render_project_async(uuid.UUID(user_id), public_id))
