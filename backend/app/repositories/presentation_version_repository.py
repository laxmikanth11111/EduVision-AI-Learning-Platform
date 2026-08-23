from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repository import BaseRepository
from app.models.presentation_version import PresentationVersion


class PresentationVersionRepository(BaseRepository[PresentationVersion]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, PresentationVersion)

    async def get_by_public_id(
        self,
        public_id: str,
    ) -> PresentationVersion | None:
        stmt = select(PresentationVersion).where(
            PresentationVersion.public_id == public_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_public_id_for_presentation(
        self,
        presentation_id: uuid.UUID,
        public_id: str,
    ) -> PresentationVersion | None:
        stmt = select(PresentationVersion).where(
            PresentationVersion.presentation_id == presentation_id,
            PresentationVersion.public_id == public_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def next_version_number(self, presentation_id: uuid.UUID) -> int:
        stmt = (
            select(func.max(PresentationVersion.version_number))
            .where(PresentationVersion.presentation_id == presentation_id)
        )
        result = await self._session.execute(stmt)
        current = result.scalar_one()
        return (current or 0) + 1

    async def list_for_presentation(
        self,
        presentation_id: uuid.UUID,
        limit: int | None = None,
    ) -> list[PresentationVersion]:
        stmt = (
            select(PresentationVersion)
            .where(PresentationVersion.presentation_id == presentation_id)
            .order_by(PresentationVersion.version_number.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
