"""Simplified lesson player — tracks which topic index we're on.

No quiz sessions, no bookmarks, no notes, no progress tracking, no user
association. Just reads the generated lesson and its versions, and
manages a lightweight in-memory topic index pointer per session.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.core.logging import get_logger
from app.database.unit_of_work import UnitOfWork
from app.models.generated_lesson import GeneratedLesson
from app.models.generated_lesson_version import GeneratedLessonVersion
from app.models.presentation import Presentation
from app.repositories.generated_lesson_repository import (
    GeneratedLessonRepository,
    GeneratedLessonVersionRepository,
)

logger = get_logger(__name__)

# In-memory session state: session_id -> { owner_id, lesson_id, topic_index, ... }
_SESSIONS: dict[str, dict[str, Any]] = {}


class LessonPlayerService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        session = uow.session
        self._lesson_repo = GeneratedLessonRepository(session)
        self._version_repo = GeneratedLessonVersionRepository(session)

    async def _assert_lesson_ownership(self, lesson_public_id: str, owner_id: str) -> GeneratedLesson:
        """Verify the user owns the presentation that contains this lesson."""
        from sqlalchemy import select

        lesson = await self._lesson_repo.get_by_public_id(lesson_public_id)
        if lesson is None:
            raise ValueError(f"Lesson {lesson_public_id} not found")
        result = await self._uow.session.execute(
            select(Presentation).where(Presentation.id == lesson.presentation_id)
        )
        presentation = result.scalar_one_or_none()
        if presentation is None or str(presentation.owner_id) != owner_id:
            raise PermissionError("You do not have access to this lesson")
        return lesson

    async def get_state(self, lesson_public_id: str, *, owner_id: str | None = None) -> dict[str, Any]:
        if owner_id:
            lesson = await self._assert_lesson_ownership(lesson_public_id, owner_id)
        else:
            lesson = await self._lesson_repo.get_by_public_id(lesson_public_id)
            if lesson is None:
                raise ValueError(f"Lesson {lesson_public_id} not found")
        version = await self._resolve_version(lesson)
        topics = self._extract_topics(version)

        # Find an active session for this lesson owned by the requesting user
        active_session = None
        for _sid, state in _SESSIONS.items():
            if str(state["lesson_id"]) == str(lesson.public_id):
                if owner_id is not None and state.get("owner_id") != owner_id:
                    continue
                active_session = state
                break

        return {
            "lesson": self._serialize_lesson(lesson),
            "version": self._serialize_version(version, lesson.public_id) if version else None,
            "topics": topics,
            "session": active_session,
        }

    async def start(
        self,
        lesson_public_id: str,
        *,
        owner_id: str | None = None,
        device_id: str | None = None,
        client_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if owner_id:
            lesson = await self._assert_lesson_ownership(lesson_public_id, owner_id)
        else:
            lesson = await self._lesson_repo.get_by_public_id(lesson_public_id)
            if lesson is None:
                raise ValueError(f"Lesson {lesson_public_id} not found")
        version = await self._resolve_version(lesson)
        topics = self._extract_topics(version)

        session_id = str(uuid.uuid4())
        session_state = {
            "session_id": session_id,
            "owner_id": owner_id,
            "lesson_id": lesson.public_id,
            "topic_index": 0,
            "total_topics": len(topics),
            "status": "active",
        }
        _SESSIONS[session_id] = session_state

        return {
            "lesson": self._serialize_lesson(lesson),
            "version": self._serialize_version(version, lesson.public_id) if version else None,
            "topics": topics,
            "session": session_state,
        }

    async def advance_topic(self, session_id: str, *, owner_id: str | None = None) -> dict[str, Any]:
        state = _SESSIONS.get(session_id)
        if state is None:
            raise ValueError(f"Session {session_id} not found")
        if owner_id is not None and state.get("owner_id") != owner_id:
            raise ValueError(f"Session {session_id} not found")
        state["topic_index"] = min(state["topic_index"] + 1, state["total_topics"] - 1)
        if state["topic_index"] >= state["total_topics"] - 1:
            state["status"] = "completed"
        return state

    async def set_topic(self, session_id: str, topic_index: int, *, owner_id: str | None = None) -> dict[str, Any]:
        state = _SESSIONS.get(session_id)
        if state is None:
            raise ValueError(f"Session {session_id} not found")
        if owner_id is not None and state.get("owner_id") != owner_id:
            raise ValueError(f"Session {session_id} not found")
        if topic_index < 0 or topic_index >= state["total_topics"]:
            raise ValueError(f"Invalid topic_index {topic_index}")
        state["topic_index"] = topic_index
        state["status"] = "active"
        return state

    # ── Internals ─────────────────────────────────────────────────────────────

    async def _resolve_version(self, lesson: GeneratedLesson) -> GeneratedLessonVersion | None:
        version = await self._version_repo.get_latest_succeeded_for_lesson(lesson.id)
        if version is None and lesson.latest_version > 0:
            version = await self._version_repo.get_by_lesson_and_version(
                lesson.id, lesson.latest_version
            )
        return version

    def _extract_topics(self, version: GeneratedLessonVersion | None) -> list[dict[str, Any]]:
        if version is None:
            return []
        topics = []
        for block in version.blocks:
            topics.append({
                "index": block.position,
                "title": block.heading or f"Topic {block.position + 1}",
                "description": block.content or "",
                "block_id": block.public_id,
            })
        return topics

    def _serialize_lesson(self, lesson: GeneratedLesson) -> dict[str, Any]:
        pres_public_id = None
        if hasattr(lesson, "presentation") and lesson.presentation is not None:
            pres_public_id = getattr(lesson.presentation, "public_id", None)
        return {
            "id": lesson.public_id,
            "presentation_id": pres_public_id,
            "mode": lesson.mode,
            "status": lesson.status,
            "title": lesson.title,
            "language": lesson.language,
            "difficulty": lesson.difficulty,
            "latest_version": lesson.latest_version,
        }

    def _serialize_version(
        self, version: GeneratedLessonVersion, lesson_public_id: str
    ) -> dict[str, Any]:
        return {
            "id": version.public_id,
            "lesson_id": lesson_public_id,
            "version": version.version,
            "status": version.status,
            "title": version.title,
            "summary": version.summary,
            "language": version.language,
            "difficulty": version.difficulty,
            "model": version.model,
            "completed_at": version.completed_at,
        }
