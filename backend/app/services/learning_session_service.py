"""Persistent per-user lesson progress (learner journey, C1).

Stores learner progress in the existing ``learning_sessions`` table
(migration 0009) so a learner's position survives a refresh or reopening the
lesson, and so progress is strictly scoped to the authenticated user.

Every read/write is filtered by ``user_id``; a missing row, an orphaned
lesson, or another user's session are reported identically (``None``) so the
caller surfaces the project's established 404 semantics without leaking
whether another user's resource exists.

The service is deliberately small: it only persists position/progress state.
It does not start/submit quizzes (reused via ``QuizAttemptService``) nor
compute mastery/recommendations (reused via ``educational_memory_service``
and ``recommendation_engine``).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.core.logging import get_logger
from app.database.unit_of_work import UnitOfWork
from app.models.learning_session import (
    PUBLIC_ID_PREFIX,
    LearningSession,
    generate_session_public_id,
)
from shared.constants import LearningSessionStatus

logger = get_logger(__name__)


def _as_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError):
        return None


class LearningSessionService:
    """Persist and read a learner's position/progress in a lesson."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def find_for_lesson(
        self,
        *,
        user_id: str,
        lesson_id: uuid.UUID,
    ) -> LearningSession | None:
        """Return the user's most recent session for a lesson, or None.

        Scoped to the authenticated user; another user's session is never
        returned (indistinguishable from "no session").
        """
        user_uuid = _as_uuid(user_id)
        if user_uuid is None:
            return None
        stmt = (
            select(LearningSession)
            .where(
                LearningSession.user_id == user_uuid,
                LearningSession.lesson_id == lesson_id,
            )
            .order_by(LearningSession.updated_at.desc())
            .limit(1)
        )
        result = await self._uow.session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_by_public_id(
        self,
        public_id: str,
        *,
        user_id: str,
    ) -> LearningSession | None:
        """Ownership-scoped lookup of a session by its public id."""
        user_uuid = _as_uuid(user_id)
        if user_uuid is None or not public_id.startswith(PUBLIC_ID_PREFIX):
            return None
        stmt = select(LearningSession).where(
            LearningSession.public_id == public_id,
            LearningSession.user_id == user_uuid,
        )
        result = await self._uow.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create(
        self,
        *,
        user_id: str,
        lesson_id: uuid.UUID,
        lesson_version_id: uuid.UUID | None,
        topic_index: int,
        total_topics: int,
        device_id: str | None = None,
        client_metadata: dict[str, Any] | None = None,
    ) -> LearningSession:
        """Return the existing session for ``user_id`` + ``lesson_id`` or create one.

        This makes start/resume idempotent: repeated calls for the same owner
        and lesson return the same persistent session (resuming its saved
        position) instead of stacking duplicate sessions.
        """
        user_uuid = _as_uuid(user_id)
        if user_uuid is None:
            raise ValueError(f"Invalid user {user_id}")

        existing = await self.find_for_lesson(user_id=user_id, lesson_id=lesson_id)
        if existing is not None:
            return existing

        now = datetime.now(UTC)
        session = LearningSession(
            public_id=generate_session_public_id(),
            user_id=user_uuid,
            lesson_id=lesson_id,
            lesson_version_id=lesson_version_id,
            status=LearningSessionStatus.STARTED.value,
            device_id=device_id,
            client_metadata=client_metadata,
            started_at=now,
            last_activity_at=now,
            current_block_position=max(0, topic_index),
            completion_percentage=_progress_percentage(topic_index, total_topics),
            total_time_seconds=0,
            resume_version=1,
        )
        self._uow.session.add(session)
        await self._uow.flush()
        return session

    async def set_topic(
        self,
        *,
        session_id: str,
        user_id: str,
        topic_index: int,
        total_topics: int,
    ) -> LearningSession | None:
        """Set the user's absolute topic position in a session.

        Returns None when the session is absent or belongs to another user.
        """
        session = await self.find_by_public_id(session_id, user_id=user_id)
        if session is None:
            return None
        self._apply_position(session, topic_index, total_topics)
        await self._uow.flush()
        return session

    async def advance(
        self,
        *,
        session_id: str,
        user_id: str,
        total_topics: int,
    ) -> LearningSession | None:
        """Advance the user's topic position by one (non-destructive, capped)."""
        session = await self.find_by_public_id(session_id, user_id=user_id)
        if session is None:
            return None
        self._apply_position(session, (session.current_block_position or 0) + 1, total_topics)
        await self._uow.flush()
        return session

    def to_player_session(
        self,
        session: LearningSession,
        total_topics: int,
        *,
        lesson_public_id: str | None = None,
    ) -> dict[str, Any]:
        """Serialize a persistent session into the player's session payload."""
        position = session.current_block_position or 0
        status = session.status
        if status == LearningSessionStatus.STARTED.value:
            status = LearningSessionStatus.ACTIVE.value
        return {
            "session_id": session.public_id,
            "lesson_id": lesson_public_id or str(session.lesson_id),
            "topic_index": position,
            "total_topics": total_topics,
            "status": status,
            "completion_percentage": round(float(session.completion_percentage or 0.0), 1),
        }

    @staticmethod
    def _apply_position(
        session: LearningSession,
        topic_index: int,
        total_topics: int,
    ) -> None:
        position = max(0, min(topic_index, max(0, total_topics - 1)))
        session.current_block_position = position
        session.completion_percentage = _progress_percentage(position, total_topics)
        session.status = (
            LearningSessionStatus.COMPLETED.value
            if total_topics > 0 and position >= total_topics - 1
            else LearningSessionStatus.ACTIVE.value
        )
        session.last_activity_at = datetime.now(UTC)


def _progress_percentage(topic_index: int, total_topics: int) -> float:
    if total_topics <= 0:
        return 0.0
    return round(((topic_index + 1) / total_topics) * 100.0, 1)
