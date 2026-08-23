from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repository import BaseRepository
from app.models.presentation_audit_log import PresentationAuditLog


class PresentationAuditLogRepository(BaseRepository[PresentationAuditLog]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, PresentationAuditLog)

    async def list_for_presentation(
        self,
        presentation_id: uuid.UUID,
        limit: int = 100,
    ) -> list[PresentationAuditLog]:
        stmt = (
            select(PresentationAuditLog)
            .where(PresentationAuditLog.presentation_id == presentation_id)
            .order_by(PresentationAuditLog.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
