from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repository import BaseRepository
from app.models.presentation import Presentation
from app.models.presentation_folder import PresentationFolder


class PresentationFolderRepository(BaseRepository[PresentationFolder]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, PresentationFolder)

    async def find_owned(
        self,
        owner_id: uuid.UUID,
        parent_id: uuid.UUID | None = None,
    ) -> list[PresentationFolder]:
        stmt = select(PresentationFolder).where(
            PresentationFolder.owner_id == owner_id,
        )
        if parent_id is None:
            stmt = stmt.where(PresentationFolder.parent_id.is_(None))
        else:
            stmt = stmt.where(PresentationFolder.parent_id == parent_id)
        stmt = stmt.order_by(PresentationFolder.name.asc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def find_all(
        self,
        parent_id: uuid.UUID | None = None,
    ) -> list[PresentationFolder]:
        stmt = select(PresentationFolder)
        if parent_id is None:
            stmt = stmt.where(PresentationFolder.parent_id.is_(None))
        else:
            stmt = stmt.where(PresentationFolder.parent_id == parent_id)
        stmt = stmt.order_by(PresentationFolder.name.asc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_presentations(self, folder_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(Presentation)
            .where(
                Presentation.folder_id == folder_id,
                Presentation.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()
