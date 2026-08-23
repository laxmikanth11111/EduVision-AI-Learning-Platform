from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.database.repository import BaseRepository
from app.models.content_block import ContentBlock
from app.models.content_unit import ContentUnit


class ContentUnitRepository(BaseRepository[ContentUnit]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ContentUnit)

    async def get_by_public_id_for_presentation(
        self,
        presentation_id: uuid.UUID,
        public_id: str,
    ) -> ContentUnit | None:
        stmt = (
            select(ContentUnit)
            .where(
                ContentUnit.presentation_id == presentation_id,
                ContentUnit.public_id == public_id,
            )
            .options(self._block_load())
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_public_id_for_presentation_or_raise(
        self,
        presentation_id: uuid.UUID,
        public_id: str,
    ) -> ContentUnit:
        unit = await self.get_by_public_id_for_presentation(presentation_id, public_id)
        if unit is None:
            raise NotFoundError(
                message="Content unit not found",
                details={"content_unit_id": public_id},
            )
        return unit

    async def list_for_presentation(
        self,
        presentation_id: uuid.UUID,
        include_blocks: bool = True,
    ) -> list[ContentUnit]:
        stmt = select(ContentUnit).where(
            ContentUnit.presentation_id == presentation_id
        )
        if include_blocks:
            stmt = stmt.options(self._block_load())
        stmt = stmt.order_by(ContentUnit.position.asc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_for_presentation(self, presentation_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(ContentUnit)
            .where(ContentUnit.presentation_id == presentation_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def delete_for_presentation(self, presentation_id: uuid.UUID) -> int:
        unit_ids = select(ContentUnit.id).where(
            ContentUnit.presentation_id == presentation_id
        )
        stmt = delete(ContentBlock).where(ContentBlock.content_unit_id.in_(unit_ids))
        await self._session.execute(stmt)
        stmt = delete(ContentUnit).where(
            ContentUnit.presentation_id == presentation_id
        )
        result = await self._session.execute(stmt)
        return int(getattr(result, "rowcount", 0) or 0)

    def _block_load(self) -> Any:
        from sqlalchemy.orm import selectinload

        return selectinload(ContentUnit.blocks)
