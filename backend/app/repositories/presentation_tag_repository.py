from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repository import BaseRepository
from app.models.presentation_tag import PresentationTag


class PresentationTagRepository(BaseRepository[PresentationTag]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, PresentationTag)

    async def list_for_presentation(
        self,
        presentation_id: uuid.UUID,
    ) -> list[PresentationTag]:
        stmt = (
            select(PresentationTag)
            .where(PresentationTag.presentation_id == presentation_id)
            .order_by(PresentationTag.name.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def find_by_presentation_and_name(
        self,
        presentation_id: uuid.UUID,
        name: str,
    ) -> PresentationTag | None:
        return await self.find_one(
            presentation_id=presentation_id,
            name=name,
        )
