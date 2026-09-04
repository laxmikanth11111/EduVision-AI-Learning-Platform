"""Deterministic learning-path service (P11).

Builds the learner's single active path as a read-composition over live
mastery/session state — no AI, no ML, no second scheduler. The path is an
ordered lesson sequence where the learner's weakest-anchored unfinished
lessons lead and completed lessons trail, so "what's next" is always a
concrete, deep-linkable lesson.

Invariants:
  - Exactly one active path per learner (auto-created on first read;
    creating a new path archives any prior active path).
  - The ordered ``sequence`` is deterministic for a given learner state:
    unfinished lessons before completed, weakest mastery first, then
    ``created_at`` for stability, then ``public_id`` for full determinism.
  - Every element is learner-scoped (``user_id`` from auth, never the client).
  - Bounded set-based queries only (≤ 5 logical queries incl. memory load).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.core.logging import get_logger
from app.database.unit_of_work import UnitOfWork
from app.models.concept import Concept
from app.models.generated_lesson import GeneratedLesson
from app.models.learning_path import LearningPath
from app.models.learning_session import LearningSession
from app.observability.metrics import metrics
from app.repositories.learning_path_repository import LearningPathRepository
from app.schemas.plan import LearningPathView, PathLesson
from app.services.educational_memory_service import educational_memory_service

logger = get_logger(__name__)

_STATUS_ACTIVE = "active"
_STATUS_ARCHIVED = "archived"
_STATUS_COMPLETED = "completed"
_STATUS_IN_PROGRESS = "in_progress"
_STATUS_NOT_STARTED = "not_started"

_COMPLETED_PERCENTAGE = 100.0

# Mastery sentinel so lessons without concept data order deterministically
# after lessons with known (weak) mastery.
_UNKNOWN_MASTERY = 101.0


@dataclass(frozen=True)
class _LessonState:
    """Live, bounded per-lesson state resolved for the path view."""

    public_id: str
    title: str
    status: str
    completion: float
    mastery: float | None
    created_at: datetime | None


class LearningPathService:
    """Create/accommodate and expose a learner's ordered learning path."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        session = uow.session
        self._path_repo = LearningPathRepository(session)

    async def get_path(
        self,
        user_id: uuid.UUID,
        *,
        title: str | None = None,
        description: str | None = None,
    ) -> LearningPathView:
        """Return the learner's path view, auto-creating/reconciling it.

        The sequence is recomputed from live state on every read so the model
        never drifts from mastery/session truth; the stored ``sequence`` is a
        snapshot of the deterministic order used for history/position.
        """
        active = await self._path_repo.find_active(user_id)
        if active is None:
            active = LearningPath(
                user_id=user_id,
                title=title or "My Learning Path",
                description=description,
                status=_STATUS_ACTIVE,
                context_version="1",
                started_at=datetime.now(UTC),
            )
            await self._path_repo.persist(active)

        states = await self._resolve_lesson_states(user_id)
        ordered = sorted(states, key=self._ordering_key)

        ordered_public = [st.public_id for st in ordered]
        if ordered_public:
            active.sequence = ordered_public
        completed_count = sum(1 for st in ordered if st.status == _STATUS_COMPLETED)
        total = len(ordered)
        active.current_position = self._current_position(ordered)
        active.progress_percent = round(
            (completed_count / total * 100.0), 1
        ) if total else 0.0
        if total and completed_count >= total:
            active.completed_at = active.completed_at or datetime.now(UTC)
        else:
            active.completed_at = None
        await self._path_repo.persist(active)

        metrics.increment("p11_path_reads_total", outcome="ok", lessons=str(total))
        return self._build_view(active, ordered)

    async def create_path(
        self,
        user_id: uuid.UUID,
        *,
        title: str,
        description: str | None = None,
    ) -> LearningPathView:
        """Create a new active path, archiving any prior active one."""
        active = await self._path_repo.find_active(user_id)
        if active is not None:
            active.status = _STATUS_ARCHIVED
            await self._path_repo.persist(active)
        return await self.get_path(user_id, title=title, description=description)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _resolve_lesson_states(self, user_id: uuid.UUID) -> list[_LessonState]:
        """Resolve the learner's lessons and their live per-lesson state.

        Four bounded set-based queries (no N+1):
          1. lessons owned by the user OR started by the user
          2. that user's learning sessions for those lessons
          3. concept -> lesson public-id mapping for mastery attribution
          4. educational memory load (project-ut�d bounded cache)
        """
        session = self._uow.session

        owned = (
            await session.execute(
                select(GeneratedLesson).where(GeneratedLesson.user_id == user_id)
            )
        ).scalars().all()
        sessioned = (
            await session.execute(
                select(GeneratedLesson)
                .join(LearningSession, LearningSession.lesson_id == GeneratedLesson.id)
                .where(LearningSession.user_id == user_id)
                .distinct()
            )
        ).scalars().all()

        by_id: dict[uuid.UUID, GeneratedLesson] = {}
        for lesson in [*owned, *sessioned]:
            by_id.setdefault(lesson.id, lesson)
        if not by_id:
            return []
        lesson_ids = list(by_id.keys())

        session_rows = (
            await session.execute(
                select(LearningSession).where(
                    LearningSession.user_id == user_id,
                    LearningSession.lesson_id.in_(lesson_ids),
                )
            )
        ).scalars().all()
        sessions_by_lesson: dict[uuid.UUID, list[LearningSession]] = {}
        for lsess in session_rows:
            sessions_by_lesson.setdefault(lsess.lesson_id, []).append(lsess)

        # lesson public id -> weakest concept mastery (single batched join).
        concept_rows = (
            await session.execute(
                select(Concept.public_id, GeneratedLesson.public_id)
                .join(GeneratedLesson, Concept.lesson_id == GeneratedLesson.id)
                .where(GeneratedLesson.public_id.in_([lesson.public_id for lesson in by_id.values()]))
            )
        ).all()
        concepts_by_lesson: dict[str, list[str]] = {}
        for concept_public_id, lesson_public_id in concept_rows:
            concepts_by_lesson.setdefault(lesson_public_id, []).append(concept_public_id)

        memory = await educational_memory_service.load_from_db(session, str(user_id))

        states: list[_LessonState] = []
        for lesson in by_id.values():
            public_id = lesson.public_id
            lsesses = sessions_by_lesson.get(lesson.id, [])
            status = self._lesson_status(lsesses)
            completion = self._max_completion(lsesses)
            mastery = self._weakest_mastery(
                memory, concepts_by_lesson.get(public_id, [])
            )
            states.append(
                _LessonState(
                    public_id=public_id,
                    title=lesson.title or "Untitled lesson",
                    status=status,
                    completion=round(completion, 1),
                    mastery=mastery,
                    created_at=lesson.created_at,
                )
            )
        return states

    @staticmethod
    def _ordering_key(state: _LessonState) -> tuple[int, float, float, str]:
        tier = (
            _TIER_NOT_STARTED
            if state.status == _STATUS_NOT_STARTED
            else _TIER_IN_PROGRESS
            if state.status == _STATUS_IN_PROGRESS
            else _TIER_COMPLETED
        )
        mastery = float(state.mastery) if state.mastery is not None else _UNKNOWN_MASTERY
        created_ts = (
            state.created_at.timestamp() if state.created_at else 0.0
        )
        return (tier, mastery, created_ts, state.public_id)

    @staticmethod
    def _current_position(ordered: list[_LessonState]) -> int:
        """1-based position of the first unfinished lesson (0 when none)."""
        for idx, state in enumerate(ordered, start=1):
            if state.status != _STATUS_COMPLETED:
                return idx
        return 0

    @staticmethod
    def _build_view(
        path: LearningPath, ordered: list[_LessonState]
    ) -> LearningPathView:
        sequence = [st.public_id for st in ordered]
        current: PathLesson | None = None
        view_seq: list[PathLesson] = []
        for st in ordered:
            item = PathLesson(
                lesson_id=st.public_id,
                title=st.title,
                status=st.status,
                completion_percentage=st.completion,
                mastery_score=st.mastery,
                deep_link=f"/frontend/player.html?lesson={st.public_id}",
            )
            view_seq.append(item)
            if current is None and st.status != _STATUS_COMPLETED:
                current = item
        if sequence:
            path.sequence = sequence
        return LearningPathView(
            id=path.public_id,
            title=path.title,
            status=path.status,
            position=path.current_position,
            lesson_count=len(view_seq),
            progress_percent=round(float(path.progress_percent or 0.0), 1),
            current_lesson=current,
            sequence=view_seq,
        )

    @staticmethod
    def _lesson_status(sessions: list[LearningSession]) -> str:
        if not sessions:
            return _STATUS_NOT_STARTED
        for lsess in sessions:
            if lsess.status == _STATUS_COMPLETED or float(
                lsess.completion_percentage or 0.0
            ) >= _COMPLETED_PERCENTAGE:
                return _STATUS_COMPLETED
        return _STATUS_IN_PROGRESS

    @staticmethod
    def _max_completion(sessions: list[LearningSession]) -> float:
        return max(
            [float(lsess.completion_percentage or 0.0) for lsess in sessions],
            default=0.0,
        )

    @staticmethod
    def _weakest_mastery(memory: Any, concept_public_ids: list[str]) -> float | None:
        scores = [
            float(memory.concept_records[cid].mastery_score)
            for cid in concept_public_ids
            if memory.concept_records.get(cid) is not None
            and memory.concept_records[cid].mastery_score is not None
        ]
        return min(scores) if scores else None


_TIER_NOT_STARTED = 0
_TIER_IN_PROGRESS = 1
_TIER_COMPLETED = 2
