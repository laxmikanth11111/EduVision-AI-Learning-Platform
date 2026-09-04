"""Repository for personalised learning paths (P11)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repository import BaseRepository
from app.models.learning_path import LearningPath


class LearningPathRepository(BaseRepository[LearningPath]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, LearningPath)

    async def get_by_public_id(self, public_id: str) -> LearningPath | None:
        stmt = select(LearningPath).where(LearningPath.public_id == public_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_user_and_public_id(
        self, user_id: uuid.UUID, public_id: str
    ) -> LearningPath | None:
        stmt = select(LearningPath).where(
            LearningPath.user_id == user_id,
            LearningPath.public_id == public_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_active(self, user_id: uuid.UUID) -> LearningPath | None:
        stmt = (
            select(LearningPath)
            .where(
                LearningPath.user_id == user_id,
                LearningPath.status == "active",
            )
            .order_by(LearningPath.created_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def persist(self, path: LearningPath) -> LearningPath:
        self._session.add(path)
        await self._session.flush()
        await self._session.refresh(path)
        return path
