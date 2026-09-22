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
from app.observability.metrics import metrics
from shared.constants import LearningSessionStatus, PlayerMode

logger = get_logger(__name__)


def _as_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError):
        return None


def _validate_player_mode(value: str | None) -> str:
    """Coerce a completion mode string, raising on anything else."""
    return PlayerMode(value or PlayerMode.LEARNING.value).value


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
        player_mode: str = PlayerMode.LEARNING.value,
    ) -> LearningSession:
        """Return the existing session for ``user_id`` + ``lesson_id`` or create one.

        This makes start/resume idempotent: repeated calls for the same owner
        and lesson return the same persistent session (resuming its saved
        position) instead of stacking duplicate sessions.

        ``player_mode`` only applies to a freshly-created session; resuming
        keeps the representation the learner was last in.
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
            player_mode=_validate_player_mode(player_mode),
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

    async def set_slide_position(
        self,
        *,
        session_id: str,
        user_id: str,
        slide_index: int,
        total_slides: int,
        player_mode: str = PlayerMode.LEARNING.value,
        source_topic_map: list[int] | None = None,
    ) -> LearningSession | None:
        """Set the user's absolute slide position in a session.

        The slide index is clamped to ``[0, max(0, total_slides - 1)]``.

        The derived topic position and completion depend on ``player_mode``:
        - ``learning`` (default): each topic is a concept + visual pair, so the
          existing ``slide_index // 2`` mapping is preserved and a full deck of
          ``total_topics * 2`` slides completes at the last visual slide.
        - ``source``: slide indices count against the uploaded source deck; the
          caller supplies ``source_topic_map`` (one topic index per source
          slide, guaranteed to end at the last topic) so the FINAL source slide
          reaches 100% instead of capping at ~50%. A proportional fallback maps
          slides evenly when no outline is available.

        Returns None when the session is absent or belongs to another user.
        """
        session = await self.find_by_public_id(session_id, user_id=user_id)
        if session is None:
            return None
        session.player_mode = _validate_player_mode(player_mode)
        clamped = max(0, min(slide_index, max(0, total_slides - 1)))
        if session.player_mode == PlayerMode.SOURCE.value:
            self._apply_source_slide_position(session, clamped, total_slides, source_topic_map)
        else:
            self._apply_learning_slide_position(session, clamped, total_slides)
        session.resume_version = (session.resume_version or 0) + 1
        session.last_activity_at = datetime.now(UTC)
        await self._uow.flush()
        metrics.increment("p15_position_updates_total", outcome="applied")
        return session

    def to_player_session(
        self,
        session: LearningSession,
        total_topics: int,
        *,
        lesson_public_id: str | None = None,
        total_slides: int | None = None,
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
            "slide_index": max(
                0, min(int(session.current_slide_position or 0), max(0, total_slides - 1))
            )
            if total_slides is not None
            else int(session.current_slide_position or 0),
            "total_topics": total_topics,
            "status": status,
            "completion_percentage": round(float(session.completion_percentage or 0.0), 1),
            "player_mode": session.player_mode or PlayerMode.LEARNING.value,
        }

    @staticmethod
    def _apply_learning_slide_position(
        session: LearningSession,
        clamped: int,
        total_slides: int,
    ) -> None:
        total_topics = max(0, total_slides // 2)
        topic_index = (
            min(clamped // 2, max(0, total_topics - 1)) if total_topics else 0
        )
        session.current_slide_position = clamped
        session.current_block_position = topic_index
        session.completion_percentage = _progress_percentage(topic_index, total_topics)
        session.status = (
            LearningSessionStatus.COMPLETED.value
            if total_topics > 0 and topic_index >= total_topics - 1
            else LearningSessionStatus.ACTIVE.value
        )
        session.last_activity_at = datetime.now(UTC)

    @staticmethod
    def _apply_source_slide_position(
        session: LearningSession,
        clamped: int,
        total_slides: int,
        source_topic_map: list[int] | None,
    ) -> None:
        n = max(0, total_slides)
        if n <= 0:
            session.current_slide_position = 0
            session.current_block_position = 0
            session.completion_percentage = 0.0
            session.status = LearningSessionStatus.ACTIVE.value
            session.last_activity_at = datetime.now(UTC)
            return
        mapping = list(source_topic_map or [])
        if len(mapping) != n:
            # No (full) outline mapping available: even a proportionate split so
            # the deck completes at its final slide.
            total_topics = max(1, (max(mapping) + 1) if mapping else n)
            mapping = [min(int(i * total_topics / n), total_topics - 1) for i in range(n)]
        total_topics = max(1, max(mapping) + 1)
        topic_index = min(mapping[clamped], total_topics - 1)
        session.current_slide_position = clamped
        session.current_block_position = topic_index
        session.completion_percentage = _progress_percentage(topic_index, total_topics)
        session.status = (
            LearningSessionStatus.COMPLETED.value
            if topic_index >= total_topics - 1
            else LearningSessionStatus.ACTIVE.value
        )
        session.last_activity_at = datetime.now(UTC)

    @staticmethod
    def _apply_position(
        session: LearningSession,
        topic_index: int,
        total_topics: int,
    ) -> None:
        position = max(0, min(topic_index, max(0, total_topics - 1)))
        session.current_block_position = position
        session.current_slide_position = position * 2
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
