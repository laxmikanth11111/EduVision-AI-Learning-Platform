from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repository import BaseRepository
from app.models.presentation_analytics import PresentationAnalytics


class PresentationAnalyticsRepository(BaseRepository[PresentationAnalytics]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, PresentationAnalytics)

    async def get_by_presentation(
        self,
        presentation_id: uuid.UUID,
    ) -> PresentationAnalytics | None:
        return await self.find_one(presentation_id=presentation_id)
