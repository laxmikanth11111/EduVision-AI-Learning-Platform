from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repository import BaseRepository
from app.models.topic_outline import TopicOutline


class TopicOutlineRepository(BaseRepository[TopicOutline]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, TopicOutline)

    async def get_by_presentation_id(
        self, presentation_id: uuid.UUID
    ) -> TopicOutline | None:
        stmt = select(TopicOutline).where(
            TopicOutline.presentation_id == presentation_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_for_presentation(self, presentation_id: uuid.UUID) -> None:
        stmt = delete(TopicOutline).where(
            TopicOutline.presentation_id == presentation_id
        )
        await self._session.execute(stmt)

    async def create_for_presentation(
        self,
        presentation_id: uuid.UUID,
        *,
        title: str | None,
        topics: list[dict[str, Any]],
        status: str = "succeeded",
        provider: str | None = None,
        model: str | None = None,
        request_id: str | None = None,
        correlation_id: str | None = None,
    ) -> TopicOutline:
        await self.delete_for_presentation(presentation_id)
        return await self.create(
            presentation_id=presentation_id,
            title=title,
            topics=topics,
            status=status,
            provider=provider,
            model=model,
            request_id=request_id,
            correlation_id=correlation_id,
        )
