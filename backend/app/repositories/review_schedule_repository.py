"""Repository for spaced-repetition review schedules (P10)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.repository import BaseRepository
from app.models.review_schedule import ReviewSchedule

# Bound on the number of due review items returned in a single request to avoid
# unbounded result sets. Clients can reduce it; this is the hard ceiling.
MAX_DUE_LIMIT = 200


class ReviewScheduleRepository(BaseRepository[ReviewSchedule]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ReviewSchedule)

    async def get_by_public_id(self, public_id: str) -> ReviewSchedule | None:
        stmt = (
            select(ReviewSchedule)
            .options(
                selectinload(ReviewSchedule.concept),
                selectinload(ReviewSchedule.lesson),
            )
            .execution_options(populate_existing=True)
            .where(ReviewSchedule.public_id == public_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_user_and_public_id(
        self, user_id: uuid.UUID, public_id: str
    ) -> ReviewSchedule | None:
        stmt = (
            select(ReviewSchedule)
            .options(
                selectinload(ReviewSchedule.concept),
                selectinload(ReviewSchedule.lesson),
            )
            .execution_options(populate_existing=True)
            .where(
                ReviewSchedule.user_id == user_id,
                ReviewSchedule.public_id == public_id,
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_active_by_concept(
        self,
        user_id: uuid.UUID,
        concept_id: uuid.UUID,
    ) -> ReviewSchedule | None:
        """Return the non-completed schedule for a learner+concept, if any."""
        stmt = (
            select(ReviewSchedule)
            .where(
                ReviewSchedule.user_id == user_id,
                ReviewSchedule.concept_id == concept_id,
                ReviewSchedule.status == "scheduled",
            )
            .order_by(ReviewSchedule.created_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_due(
        self,
        user_id: uuid.UUID,
        *,
        due_at: datetime | None = None,
        limit: int = MAX_DUE_LIMIT,
    ) -> list[ReviewSchedule]:
        """Return the learner's active review schedules.

        When ``due_at`` is provided, only items due by that instant are returned
        (null ``due_at`` counts as immediately due). Otherwise all active
        schedules are returned ordered by due time. Bounded to ``MAX_DUE_LIMIT``.
        """
        bounded = max(1, min(int(limit), MAX_DUE_LIMIT))
        stmt = (
            select(ReviewSchedule)
            .options(
                selectinload(ReviewSchedule.concept),
                selectinload(ReviewSchedule.lesson),
            )
            .execution_options(populate_existing=True)
            .where(
                ReviewSchedule.user_id == user_id,
                ReviewSchedule.status == "scheduled",
            )
            .order_by(ReviewSchedule.due_at.asc().nulls_last())
            .limit(bounded)
        )
        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        if due_at is not None:
            rows = [r for r in rows if r.due_at is None or r.due_at <= due_at]
        return rows

    async def count_due(
        self,
        user_id: uuid.UUID,
        *,
        due_at: datetime | None = None,
    ) -> int:
        stmt = select(ReviewSchedule).where(
            ReviewSchedule.user_id == user_id,
            ReviewSchedule.status == "scheduled",
        )
        rows = list((await self._session.execute(stmt)).scalars().all())
        if due_at is None:
            return len(rows)
        return sum(1 for r in rows if r.due_at is None or r.due_at <= due_at)

    async def persist(self, schedule: ReviewSchedule) -> ReviewSchedule:
        self._session.add(schedule)
        await self._session.flush()
        await self._session.refresh(schedule)
        return schedule

    async def save_due(
        self,
        schedule: ReviewSchedule,
        *,
        status: str,
        due_at: datetime,
        last_reviewed_at: datetime,
        interval_days: int,
        completed_at: datetime | None,
        mastery: float | None,
    ) -> ReviewSchedule:
        schedule.status = status
        schedule.due_at = due_at
        schedule.last_reviewed_at = last_reviewed_at
        schedule.interval_days = int(interval_days)
        schedule.completed_at = completed_at
        if mastery is not None:
            schedule.mastery_at_schedule = float(mastery)
        await self._session.flush()
        await self._session.refresh(schedule)
        return schedule
