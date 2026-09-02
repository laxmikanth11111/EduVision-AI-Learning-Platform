from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError
from app.database.repository import BaseRepository
from app.models.export_job import ExportJob
from shared.constants import ExportJobStatus


def _job_graph() -> list[Any]:
    return [selectinload(ExportJob.export_files)]


class ExportJobRepository(BaseRepository[ExportJob]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ExportJob)

    async def create_job(self, job: ExportJob) -> ExportJob:
        self._session.add(job)
        await self._session.flush()
        return job

    async def get_by_public_id(self, public_id: str) -> ExportJob | None:
        stmt = (
            select(ExportJob)
            .where(ExportJob.public_id == public_id, ExportJob.deleted_at.is_(None))
            .options(*_job_graph())
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_user_job_by_public_id(
        self, user_id: uuid.UUID, public_id: str
    ) -> ExportJob | None:
        stmt = (
            select(ExportJob)
            .where(
                ExportJob.public_id == public_id,
                ExportJob.user_id == user_id,
                ExportJob.deleted_at.is_(None),
            )
            .options(*_job_graph())
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_jobs(
        self,
        user_id: uuid.UUID,
        kind: str | None = None,
        format: str | None = None,
        status: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> list[ExportJob]:
        stmt = select(ExportJob).where(
            ExportJob.user_id == user_id, ExportJob.deleted_at.is_(None)
        )
        if kind:
            stmt = stmt.where(ExportJob.kind == kind)
        if format:
            stmt = stmt.where(ExportJob.format == format)
        if status:
            stmt = stmt.where(ExportJob.status == status)

        stmt = stmt.order_by(ExportJob.created_at.desc()).offset(offset).limit(limit)
        stmt = stmt.options(*_job_graph())
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    async def count_jobs(
        self,
        user_id: uuid.UUID,
        kind: str | None = None,
        format: str | None = None,
        status: str | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(ExportJob).where(
            ExportJob.user_id == user_id, ExportJob.deleted_at.is_(None)
        )
        if kind:
            stmt = stmt.where(ExportJob.kind == kind)
        if format:
            stmt = stmt.where(ExportJob.format == format)
        if status:
            stmt = stmt.where(ExportJob.status == status)

        res = await self._session.execute(stmt)
        return res.scalar_one() or 0

    async def get_active_job_for_target(
        self, user_id: uuid.UUID, target_id: str, kind: str, format: str
    ) -> ExportJob | None:
        active_statuses = [ExportJobStatus.QUEUED.value, ExportJobStatus.PROCESSING.value]
        stmt = (
            select(ExportJob)
            .where(
                ExportJob.user_id == user_id,
                ExportJob.target_id == target_id,
                ExportJob.kind == kind,
                ExportJob.format == format,
                ExportJob.status.in_(active_statuses),
                ExportJob.deleted_at.is_(None),
            )
            .options(*_job_graph())
            .order_by(ExportJob.created_at.desc())
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def count_active_for_user(self, user_id: uuid.UUID) -> int:
        """Count a user's active (queued/processing) export jobs."""
        stmt = (
            select(func.count())
            .select_from(ExportJob)
            .where(
                ExportJob.user_id == user_id,
                ExportJob.status.in_(
                    [ExportJobStatus.QUEUED.value, ExportJobStatus.PROCESSING.value]
                ),
                ExportJob.deleted_at.is_(None),
            )
        )
        res = await self._session.execute(stmt)
        return int(res.scalar_one() or 0)

    async def update_job_progress(
        self,
        job_id: uuid.UUID,
        progress_percentage: int,
        status: str | None = None,
        error_message: str | None = None,
    ) -> ExportJob:
        stmt = select(ExportJob).where(ExportJob.id == job_id)
        res = await self._session.execute(stmt)
        job = res.scalar_one_or_none()
        if not job:
            raise NotFoundError(f"ExportJob {job_id} not found")

        job.progress_percentage = progress_percentage
        if status:
            job.status = status
        if error_message is not None:
            job.error_message = error_message

        await self._session.flush()
        return job
