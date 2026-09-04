"""Repository for measurable learner goals (P11)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repository import BaseRepository
from app.models.learning_goal import LearningGoal


class LearningGoalRepository(BaseRepository[LearningGoal]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, LearningGoal)

    async def get_by_public_id(self, public_id: str) -> LearningGoal | None:
        stmt = select(LearningGoal).where(LearningGoal.public_id == public_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_user_and_public_id(
        self, user_id: uuid.UUID, public_id: str
    ) -> LearningGoal | None:
        stmt = select(LearningGoal).where(
            LearningGoal.user_id == user_id,
            LearningGoal.public_id == public_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_user(
        self,
        user_id: uuid.UUID,
        *,
        status: str | None = None,
        limit: int = 100,
    ) -> list[LearningGoal]:
        stmt = (
            select(LearningGoal)
            .where(LearningGoal.user_id == user_id)
            .order_by(
                LearningGoal.created_at.desc(),
                LearningGoal.public_id.asc(),
            )
            .limit(max(1, min(int(limit), 500)))
        )
        if status:
            stmt = stmt.where(LearningGoal.status == status)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def persist(self, goal: LearningGoal) -> LearningGoal:
        self._session.add(goal)
        await self._session.flush()
        await self._session.refresh(goal)
        return goal
