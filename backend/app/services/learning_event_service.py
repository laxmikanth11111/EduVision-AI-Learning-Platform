"""Learning Event Service — record and query meaningful learning events."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.learning_event import LearningEvent


class LearningEventService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        user_id: uuid.UUID,
        event_type: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
        concept_id: str | None = None,
        presentation_id: uuid.UUID | None = None,
        metadata_json: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> LearningEvent:
        event = LearningEvent(
            user_id=user_id,
            event_type=event_type,
            resource_type=resource_type,
            resource_id=resource_id,
            concept_id=concept_id,
            presentation_id=presentation_id,
            metadata_json=metadata_json,
            occurred_at=occurred_at or datetime.now(UTC),
        )
        self._session.add(event)
        await self._session.flush()
        await self._session.refresh(event)
        return event

    async def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        event_type: str | None = None,
        presentation_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[LearningEvent], int]:
        filters = [LearningEvent.user_id == user_id]
        if event_type:
            filters.append(LearningEvent.event_type == event_type)
        if presentation_id:
            filters.append(LearningEvent.presentation_id == presentation_id)

        count_stmt = select(func.count()).select_from(LearningEvent).where(*filters)
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = (
            select(LearningEvent)
            .where(*filters)
            .order_by(LearningEvent.occurred_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all()), total

    async def summary_for_presentation(
        self,
        user_id: uuid.UUID,
        presentation_id: uuid.UUID,
    ) -> dict[str, Any]:
        filters = [
            LearningEvent.user_id == user_id,
            LearningEvent.presentation_id == presentation_id,
        ]
        stmt = select(LearningEvent).where(*filters)
        result = await self._session.execute(stmt)
        events = list(result.scalars().all())

        summary: dict[str, Any] = {
            "total_events": len(events),
            "event_types": {},
            "first_event_at": None,
            "last_event_at": None,
        }
        if events:
            summary["first_event_at"] = events[-1].occurred_at
            summary["last_event_at"] = events[0].occurred_at
            for e in events:
                summary["event_types"][e.event_type] = (
                    summary["event_types"].get(e.event_type, 0) + 1
                )
        return summary

    async def total_learning_time(
        self,
        user_id: uuid.UUID,
        presentation_id: uuid.UUID,
    ) -> int:
        duration_events = list(
            (await self._session.execute(
                select(LearningEvent).where(
                    LearningEvent.user_id == user_id,
                    LearningEvent.presentation_id == presentation_id,
                    LearningEvent.event_type.in_([
                        "lesson_started", "lesson_completed",
                        "quiz_started", "quiz_completed",
                        "ai_tutor_used",
                    ]),
                )
            )).scalars().all()
        )
        total = 0
        for i in range(len(duration_events) - 1):
            curr = duration_events[i]
            nxt = duration_events[i + 1]
            if curr.occurred_at and nxt.occurred_at:
                delta = (curr.occurred_at - nxt.occurred_at).total_seconds()
                if 0 < delta < 7200:
                    total += int(delta)
        return max(total, 0)
