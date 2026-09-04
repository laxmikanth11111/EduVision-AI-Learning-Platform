"""Repository for dated study plans (P11)."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repository import BaseRepository
from app.models.study_plan import StudyPlan


class StudyPlanRepository(BaseRepository[StudyPlan]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, StudyPlan)

    async def get_by_public_id(self, public_id: str) -> StudyPlan | None:
        stmt = select(StudyPlan).where(StudyPlan.public_id == public_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_user_and_public_id(
        self, user_id: uuid.UUID, public_id: str
    ) -> StudyPlan | None:
        stmt = select(StudyPlan).where(
            StudyPlan.user_id == user_id,
            StudyPlan.public_id == public_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_active_for_date(
        self, user_id: uuid.UUID, on_date: date
    ) -> StudyPlan | None:
        stmt = (
            select(StudyPlan)
            .where(
                StudyPlan.user_id == user_id,
                StudyPlan.status == "active",
                StudyPlan.start_date <= on_date,
                StudyPlan.end_date >= on_date,
            )
            .order_by(StudyPlan.created_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_active(self, user_id: uuid.UUID) -> list[StudyPlan]:
        stmt = (
            select(StudyPlan)
            .where(StudyPlan.user_id == user_id, StudyPlan.status == "active")
            .order_by(StudyPlan.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def persist(self, plan: StudyPlan) -> StudyPlan:
        self._session.add(plan)
        await self._session.flush()
        await self._session.refresh(plan)
        return plan
