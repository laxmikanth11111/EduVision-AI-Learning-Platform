"""Interactive lesson player — reads a lesson and tracks persistent progress.

Reads the generated lesson and its versions and manages the learner's
position via an existing persistent ``LearningSession`` row (per authenticated
user + lesson, migration 0009), so progress survives refresh and is strictly
user-scoped. Assessment checkpoints (a ``Quiz`` bound to the lesson) and the
learner's mastery + next learning action are surfaced through the same
service, reusing the existing quiz attempt, ``educational_memory_service``
and ``recommendation_engine`` machinery.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from app.core.logging import get_logger
from app.database.unit_of_work import UnitOfWork
from app.models.generated_lesson import GeneratedLesson
from app.models.generated_lesson_version import GeneratedLessonVersion
from app.models.presentation import Presentation
from app.repositories.generated_lesson_repository import (
    GeneratedLessonRepository,
    GeneratedLessonVersionRepository,
)
from app.repositories.quiz_repository import QuizAttemptRepository, QuizRepository
from app.services.learning_session_service import LearningSessionService
from app.utils.bounded_cache import BoundedCache

logger = get_logger(__name__)

# Transient in-memory session state for the anonymous/tooling player path
# (session_id -> state). Bounded + TTL'd (WS4 contract). Authenticated users
# otherwise persist their position through the ``learning_sessions`` table via
# ``LearningSessionService``, so this cache never holds per-user progress.
_SESSIONS: BoundedCache[str, dict[str, Any]] = BoundedCache(
    max_size=2048,
    ttl=3600,
)


class LessonPlayerService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        session = uow.session
        self._lesson_repo = GeneratedLessonRepository(session)
        self._version_repo = GeneratedLessonVersionRepository(session)
        self._progress = LearningSessionService(uow)

    async def _assert_lesson_ownership(
        self, lesson_public_id: str, owner_id: str
    ) -> GeneratedLesson:
        """Load a lesson and verify the user owns its presentation."""
        return await self._load_accessible_lesson(lesson_public_id, owner_id)

    async def _load_accessible_lesson(
        self,
        lesson_public_id: str,
        owner_id: str | None,
    ) -> GeneratedLesson:
        """Load a lesson, enforcing ownership when ``owner_id`` is given."""
        lesson = await self._lesson_repo.get_by_public_id(lesson_public_id)
        if lesson is None:
            raise ValueError(f"Lesson {lesson_public_id} not found")
        if owner_id is not None:
            result = await self._uow.session.execute(
                select(Presentation).where(Presentation.id == lesson.presentation_id)
            )
            presentation = result.scalar_one_or_none()
            if presentation is None or str(presentation.owner_id) != owner_id:
                raise PermissionError("You do not have access to this lesson")
        return lesson

    async def get_state(
        self,
        lesson_public_id: str,
        *,
        owner_id: str | None = None,
    ) -> dict[str, Any]:
        lesson = await self._load_accessible_lesson(lesson_public_id, owner_id)
        version = await self._resolve_version(lesson)
        topics = self._extract_topics(version)
        total_topics = len(topics)

        active_session = None
        if owner_id:
            session = await self._progress.find_for_lesson(user_id=owner_id, lesson_id=lesson.id)
            if session is not None:
                active_session = self._progress.to_player_session(
                    session,
                    total_topics,
                    lesson_public_id=lesson.public_id,
                    total_slides=total_topics * 2,
                )
                resumed_slide = int(active_session.get("slide_index") or 0)
                if resumed_slide > 0:
                    logger.info(
                        "lesson_resume_restored",
                        lesson=lesson.public_id,
                        slide_index=resumed_slide,
                        total_slides=total_topics * 2,
                    )
        else:
            # Anonymous path: surface an existing transient session for this lesson.
            for _sid, state in _SESSIONS.items():
                if str(state.get("lesson_id")) == str(lesson.public_id):
                    if state.get("owner_id") not in (None, ""):
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
        lesson = await self._load_accessible_lesson(lesson_public_id, owner_id)
        version = await self._resolve_version(lesson)
        topics = self._extract_topics(version)
        total_topics = len(topics)

        if owner_id:
            # Idempotent resume: same owner + lesson -> same persistent session,
            # restoring its saved position.
            session = await self._progress.get_or_create(
                user_id=owner_id,
                lesson_id=lesson.id,
                lesson_version_id=version.id if version else None,
                topic_index=0,
                total_topics=total_topics,
                device_id=device_id,
                client_metadata=client_metadata,
            )
        else:
            # Anonymous/tooling path: a short-lived, bound in-memory session.
            session_id = str(uuid.uuid4())
            session_state = {
                "session_id": session_id,
                "lesson_id": lesson.public_id,
                "topic_index": 0,
                "slide_index": 0,
                "total_topics": total_topics,
                "status": "active",
                "completion_percentage": (
                    round(((0 + 1) / total_topics) * 100.0, 1) if total_topics > 0 else 0.0
                ),
            }
            _SESSIONS.set(session_id, session_state)
            return {
                "lesson": self._serialize_lesson(lesson),
                "version": self._serialize_version(version, lesson.public_id) if version else None,
                "topics": topics,
                "session": session_state,
            }

        return {
            "lesson": self._serialize_lesson(lesson),
            "version": self._serialize_version(version, lesson.public_id) if version else None,
            "topics": topics,
            "session": self._progress.to_player_session(
                session,
                total_topics,
                lesson_public_id=lesson.public_id,
                total_slides=total_topics * 2,
            ),
        }

    async def set_position(
        self,
        session_id: str,
        slide_index: int,
        *,
        owner_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Set the user's absolute slide position in a persistent session.

        Slide-accurate resume: each topic renders as two slides (concept then
        visual), so ``slide_index = topic_index * 2 (+0 | +1)``. The persisted
        session therefore restores the exact slide the learner was on. Returns
        None when the session is absent or belongs to another user.
        """
        if owner_id is None:
            return None
        lesson_id = await self._lesson_id_for_session(session_id, owner_id)
        if lesson_id is None:
            return None
        total = await self._topic_count_for_lesson(lesson_id)
        total_slides = max(0, total * 2)
        updated = await self._progress.set_slide_position(
            session_id=session_id,
            user_id=owner_id,
            slide_index=slide_index,
            total_slides=total_slides,
        )
        if updated is None:
            return None
        return self._progress.to_player_session(updated, total, total_slides=total_slides)

    async def advance_topic(
        self,
        session_id: str,
        *,
        owner_id: str | None = None,
    ) -> dict[str, Any] | None:
        if owner_id:
            lesson_id = await self._lesson_id_for_session(session_id, owner_id)
            if lesson_id is None:
                raise ValueError(f"Session {session_id} not found")
            total = await self._topic_count_for_lesson(lesson_id)
            updated = await self._progress.advance(
                session_id=session_id,
                user_id=owner_id,
                total_topics=total,
            )
            if updated is None:
                raise ValueError(f"Session {session_id} not found")
            return self._progress.to_player_session(updated, total, total_slides=total * 2)

        # Anonymous path: mutate in-memory transient session
        state = _SESSIONS.get(session_id)
        if state is None:
            raise ValueError(f"Session {session_id} not found")
        idx = state.get("topic_index", 0) + 1
        total = state.get("total_topics", 0)
        capped = max(0, min(idx, max(0, total - 1)))
        state["topic_index"] = capped
        state["completion_percentage"] = (
            round(((capped + 1) / total) * 100.0, 1) if total > 0 else 0.0
        )
        state["status"] = "completed" if total > 0 and capped >= total - 1 else "active"
        _SESSIONS.set(session_id, state)
        return state

    async def set_topic(
        self,
        session_id: str,
        topic_index: int,
        *,
        owner_id: str | None = None,
    ) -> dict[str, Any] | None:
        if owner_id:
            lesson_id = await self._lesson_id_for_session(session_id, owner_id)
            if lesson_id is None:
                raise ValueError(f"Session {session_id} not found")
            total = await self._topic_count_for_lesson(lesson_id)
            updated = await self._progress.set_topic(
                session_id=session_id,
                user_id=owner_id,
                topic_index=topic_index,
                total_topics=total,
            )
            if updated is None:
                raise ValueError(f"Session {session_id} not found")
            return self._progress.to_player_session(updated, total, total_slides=total * 2)

        # Anonymous path: mutate in-memory transient session
        state = _SESSIONS.get(session_id)
        if state is None:
            raise ValueError(f"Session {session_id} not found")
        total = state.get("total_topics", 0)
        capped = max(0, min(topic_index, max(0, total - 1)))
        state["topic_index"] = capped
        state["completion_percentage"] = (
            round(((capped + 1) / total) * 100.0, 1) if total > 0 else 0.0
        )
        state["status"] = "completed" if total > 0 and capped >= total - 1 else "active"
        _SESSIONS.set(session_id, state)
        return state

    # ── Assessment checkpoint ─────────────────────────────────────────────────

    async def get_checkpoint(
        self,
        lesson_public_id: str,
        *,
        owner_id: str,
    ) -> dict[str, Any]:
        """Return the assessment checkpoint for a lesson, if one exists.

        The checkpoint is the existing ``Quiz`` bound to the lesson (``lesson_id``).
        Ownership of the lesson is asserted first; the learner's own attempt
        history (scoped to ``owner_id``) is aggregated to report completion
        without exposing another user's attempts.
        """
        lesson = await self._assert_lesson_ownership(lesson_public_id, owner_id)
        quiz_repo = QuizRepository(self._uow.session)
        quizzes = await quiz_repo.list_by_lesson(lesson.id)
        if not quizzes:
            return {
                "has_checkpoint": False,
                "quiz": None,
                "completed": False,
                "latest_attempt": None,
                "available_attempts": 0,
            }

        quiz = quizzes[0]
        attempt_repo = QuizAttemptRepository(self._uow.session)
        attempts = await attempt_repo.list_by_quiz_and_user(quiz.id, uuid.UUID(str(owner_id)))
        completed = [a for a in attempts if a.status == "completed"]
        latest = completed[0] if completed else None
        latest_summary = None
        if latest is not None:
            passing = quiz.passing_score
            percent = float(latest.percent_score) if latest.percent_score is not None else None
            passed = None
            if passing is not None and percent is not None:
                passed = percent >= float(passing)
            latest_summary = {
                "attempt_id": latest.public_id,
                "attempt_number": latest.attempt_number,
                "percent_score": percent,
                "passed": passed,
                "score": float(latest.score) if latest.score is not None else None,
                "max_score": float(latest.max_score) if latest.max_score is not None else None,
                "completed_at": latest.completed_at,
            }

        return {
            "has_checkpoint": True,
            "quiz": {
                "id": quiz.public_id,
                "title": quiz.title,
                "description": quiz.description,
                "mode": quiz.mode,
                "status": quiz.status,
                "question_count": quiz.question_count,
                "passing_score": float(quiz.passing_score) if quiz.passing_score else None,
                "max_attempts_per_user": quiz.max_attempts_per_user,
            },
            "completed": len(completed) > 0,
            "latest_attempt": latest_summary,
            "available_attempts": max(0, (quiz.max_attempts_per_user or 0) - len(attempts)),
        }

    # ── Mastery + next learning action ───────────────────────────────────────

    async def get_mastery_and_next_action(
        self,
        lesson_public_id: str,
        *,
        owner_id: str,
    ) -> dict[str, Any]:
        """Surface the learner's mastery and a deterministic next action.

        Reuses ``educational_memory_service`` (DB-backed concept mastery) and
        ``recommendation_engine.generate_recommendations`` (deterministic,
        mastery-driven NextAction) — no new algorithm is introduced.
        """
        await self._assert_lesson_ownership(lesson_public_id, owner_id)

        from app.services.educational_memory_service import (
            educational_memory_service,
        )
        from app.services.recommendation_engine import generate_recommendations

        user_str = str(owner_id)
        memory = await educational_memory_service.load_from_db(self._uow.session, user_str)
        recommendation = generate_recommendations(user_str, memory)

        top_action = recommendation.actions[0] if recommendation.actions else None
        return {
            "average_mastery": memory.profile.average_mastery,
            "mastered_count": len(recommendation.mastered_concepts),
            "developing_count": len(recommendation.developing_concepts),
            "weak_count": len(recommendation.weak_concepts),
            "concept_mastery": recommendation.concept_mastery,
            "summary": recommendation.summary,
            "next_action": (
                {
                    "action_type": top_action.action_type.value,
                    "concept_id": top_action.concept_id,
                    "concept_name": top_action.concept_name,
                    "title": top_action.title,
                    "description": top_action.description,
                    "reason": top_action.reason,
                    "activity_type": top_action.activity_type.value,
                    "priority": top_action.priority.value,
                }
                if top_action is not None
                else None
            ),
        }

    # ── Internals ─────────────────────────────────────────────────────────────

    async def _lesson_id_for_session(self, session_id: str, owner_id: str) -> uuid.UUID | None:
        session = await self._progress.find_by_public_id(session_id, user_id=owner_id)
        if session is None:
            return None
        return session.lesson_id

    async def _topic_count_for_lesson(self, lesson_id: uuid.UUID) -> int:
        version = await self._version_repo.get_latest_succeeded_for_lesson(lesson_id)
        if version is None:
            return 0
        return len(version.blocks)

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
            topics.append(
                {
                    "index": block.position,
                    "title": block.heading or f"Topic {block.position + 1}",
                    "description": block.content or "",
                    "block_id": block.public_id,
                }
            )
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
