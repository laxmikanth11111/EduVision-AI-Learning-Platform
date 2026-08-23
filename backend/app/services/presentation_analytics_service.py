from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.core.logging import get_logger
from app.database.unit_of_work import UnitOfWork
from app.models.presentation_analytics import PresentationAnalytics
from app.repositories.presentation_analytics_repository import PresentationAnalyticsRepository

logger = get_logger(__name__)


class PresentationAnalyticsService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        self._repo = PresentationAnalyticsRepository(uow.session)

    async def _get_or_create(self, presentation_id: uuid.UUID) -> PresentationAnalytics:
        analytics = await self._repo.get_by_presentation(presentation_id)
        if analytics is None:
            analytics = await self._repo.create(presentation_id=presentation_id)
        return analytics

    async def ensure_exists(self, presentation_id: uuid.UUID) -> PresentationAnalytics:
        return await self._get_or_create(presentation_id)

    async def record_view(
        self,
        presentation_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
        is_new_viewer: bool = False,
    ) -> PresentationAnalytics:
        analytics = await self._get_or_create(presentation_id)
        analytics.view_count += 1
        analytics.last_viewed_at = datetime.now(UTC)
        if user_id is not None and is_new_viewer:
            analytics.unique_viewers += 1
        await self._uow.flush()
        logger.info(
            "presentation_view_recorded",
            presentation_id=str(presentation_id),
            user_id=str(user_id) if user_id else None,
        )
        return analytics

    async def record_quiz_attempt(
        self,
        presentation_id: uuid.UUID,
        score: float,
    ) -> PresentationAnalytics:
        analytics = await self._get_or_create(presentation_id)
        new_count = analytics.quiz_attempts + 1
        current_total = (analytics.avg_quiz_score or 0.0) * analytics.quiz_attempts
        analytics.avg_quiz_score = (current_total + score) / new_count
        analytics.quiz_attempts = new_count
        await self._uow.flush()
        return analytics

    async def record_publish(
        self,
        presentation_id: uuid.UUID,
    ) -> PresentationAnalytics:
        analytics = await self._get_or_create(presentation_id)
        analytics.publish_count += 1
        await self._uow.flush()
        logger.info(
            "presentation_publish_recorded",
            presentation_id=str(presentation_id),
            publish_count=analytics.publish_count,
        )
        return analytics

    async def record_learning_session(
        self,
        presentation_id: uuid.UUID,
    ) -> PresentationAnalytics:
        analytics = await self._get_or_create(presentation_id)
        analytics.learning_sessions += 1
        analytics.last_viewed_at = datetime.now(UTC)
        await self._uow.flush()
        logger.info(
            "learning_session_recorded",
            presentation_id=str(presentation_id),
            learning_sessions=analytics.learning_sessions,
        )
        return analytics

    async def get_analytics(
        self,
        presentation_id: uuid.UUID,
    ) -> dict[str, Any] | None:
        analytics = await self._repo.get_by_presentation(presentation_id)
        if analytics is None:
            return None
        return {
            "presentation_id": analytics.presentation_id,
            "view_count": analytics.view_count,
            "unique_viewers": analytics.unique_viewers,
            "quiz_attempts": analytics.quiz_attempts,
            "publish_count": analytics.publish_count,
            "learning_sessions": analytics.learning_sessions,
            "total_opens": analytics.view_count,
            "avg_quiz_score": analytics.avg_quiz_score,
            "completion_rate": analytics.completion_rate,
            "last_viewed_at": analytics.last_viewed_at,
        }

    async def recompute_aggregates(self) -> int:
        from sqlalchemy import select

        stmt = select(PresentationAnalytics)
        result = await self._uow.session.execute(stmt)
        rows = list(result.scalars().all())
        updated = 0
        for row in rows:
            new_rate: float | None = None
            if row.avg_quiz_score is not None:
                new_rate = max(0.0, min(1.0, row.avg_quiz_score / 100.0))
            if row.completion_rate != new_rate:
                row.completion_rate = new_rate
                updated += 1
        if updated:
            await self._uow.flush()
        logger.info(
            "analytics_aggregates_recomputed",
            rows=len(rows),
            updated=updated,
        )
        return updated
