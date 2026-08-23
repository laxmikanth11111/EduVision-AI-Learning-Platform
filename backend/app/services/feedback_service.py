"""User Feedback Service — collect and aggregate optional learner feedback."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_feedback import UserFeedback


class UserFeedbackService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def submit(
        self,
        *,
        user_id: uuid.UUID,
        presentation_id: uuid.UUID | None = None,
        assessment_id: uuid.UUID | None = None,
        perceived_understanding: int | None = None,
        confidence: int | None = None,
        usefulness: int | None = None,
        visual_usefulness: int | None = None,
        animation_usefulness: int | None = None,
        tutor_usefulness: int | None = None,
        recommendation_usefulness: int | None = None,
        overall_experience: int | None = None,
        qualitative_feedback: str | None = None,
    ) -> UserFeedback:
        feedback = UserFeedback(
            user_id=user_id,
            presentation_id=presentation_id,
            assessment_id=assessment_id,
            perceived_understanding=perceived_understanding,
            confidence=confidence,
            usefulness=usefulness,
            visual_usefulness=visual_usefulness,
            animation_usefulness=animation_usefulness,
            tutor_usefulness=tutor_usefulness,
            recommendation_usefulness=recommendation_usefulness,
            overall_experience=overall_experience,
            qualitative_feedback=qualitative_feedback,
        )
        self._session.add(feedback)
        await self._session.flush()
        await self._session.refresh(feedback)
        return feedback

    async def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        presentation_id: uuid.UUID | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[UserFeedback], int]:
        filters = [UserFeedback.user_id == user_id]
        if presentation_id:
            filters.append(UserFeedback.presentation_id == presentation_id)

        count_stmt = select(func.count()).select_from(UserFeedback).where(*filters)
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = (
            select(UserFeedback)
            .where(*filters)
            .order_by(UserFeedback.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all()), total

    async def summary_for_presentation(
        self,
        presentation_id: uuid.UUID,
    ) -> dict[str, Any]:
        filters = [UserFeedback.presentation_id == presentation_id]
        stmt = select(UserFeedback).where(*filters)
        result = await self._session.execute(stmt)
        feedbacks = list(result.scalars().all())

        if not feedbacks:
            return {
                "total_count": 0,
                "avg_perceived_understanding": None,
                "avg_confidence": None,
                "avg_usefulness": None,
                "avg_visual_usefulness": None,
                "avg_animation_usefulness": None,
                "avg_tutor_usefulness": None,
                "avg_recommendation_usefulness": None,
                "avg_overall_experience": None,
            }

        def avg(field: str) -> float | None:
            vals = [getattr(f, field) for f in feedbacks if getattr(f, field) is not None]
            return round(sum(vals) / len(vals), 2) if vals else None

        return {
            "total_count": len(feedbacks),
            "avg_perceived_understanding": avg("perceived_understanding"),
            "avg_confidence": avg("confidence"),
            "avg_usefulness": avg("usefulness"),
            "avg_visual_usefulness": avg("visual_usefulness"),
            "avg_animation_usefulness": avg("animation_usefulness"),
            "avg_tutor_usefulness": avg("tutor_usefulness"),
            "avg_recommendation_usefulness": avg("recommendation_usefulness"),
            "avg_overall_experience": avg("overall_experience"),
        }
