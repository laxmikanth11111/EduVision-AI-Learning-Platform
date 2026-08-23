from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError
from app.database.repository import BaseRepository
from app.models.export_file import ExportFile


class ExportFileRepository(BaseRepository[ExportFile]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ExportFile)

    async def create_file(self, export_file: ExportFile) -> ExportFile:
        self._session.add(export_file)
        await self._session.flush()
        return export_file

    async def get_by_public_id(self, public_id: str) -> ExportFile | None:
        stmt = (
            select(ExportFile)
            .where(ExportFile.public_id == public_id, ExportFile.deleted_at.is_(None))
            .options(selectinload(ExportFile.job))
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_job_id(self, job_id: uuid.UUID) -> list[ExportFile]:
        stmt = (
            select(ExportFile)
            .where(ExportFile.job_id == job_id, ExportFile.deleted_at.is_(None))
            .order_by(ExportFile.created_at.asc())
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    async def get_user_file_by_public_id(
        self, user_id: uuid.UUID, public_id: str
    ) -> ExportFile | None:
        stmt = (
            select(ExportFile)
            .where(
                ExportFile.public_id == public_id,
                ExportFile.user_id == user_id,
                ExportFile.deleted_at.is_(None),
            )
            .options(selectinload(ExportFile.job))
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def increment_download_count(self, public_id: str) -> ExportFile:
        export_file = await self.get_by_public_id(public_id)
        if not export_file:
            raise NotFoundError(f"ExportFile {public_id} not found")

        export_file.download_count += 1
        await self._session.flush()
        return export_file
