"""Derived-progress goal service (P11).

Goals are learner-authored targets with *derived* progress: ``current_value``
is always recomputed from live state (never accepted from the client), and the
stored column is refreshed as a denormalised snapshot on read.

Supported goal types (deterministic derivations, no AI):
  - MASTERY_TARGET     -> memory.profile.average_mastery (0..100)
  - LESSON_COMPLETION  -> count of the learner's completed lessons
  - QUIZ_SCORE         -> best recent completed quiz percentage
  - STREAK_DAYS        -> memory.profile.streak_days

Completing a goal only succeeds when its target is actually met (progress
>= 100%); completion is idempotent once achieved. Everything is learner-scoped
from the authenticated user.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import func, select

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.database.unit_of_work import UnitOfWork
from app.models.generated_lesson import GeneratedLesson
from app.models.learning_goal import LearningGoal
from app.models.learning_session import LearningSession
from app.models.quiz_attempt import QuizAttempt
from app.observability.metrics import metrics
from app.repositories.learning_goal_repository import LearningGoalRepository
from app.schemas.plan import (
    GoalCompleteResponse,
    LearningGoalView,
)
from app.services.educational_memory_service import educational_memory_service
from shared.constants import LearningGoalType

logger = get_logger(__name__)

_GOAL_MASTERY = LearningGoalType.MASTERY_TARGET.value
_GOAL_LESSONS = LearningGoalType.LESSON_COMPLETION.value
_GOAL_QUIZ = LearningGoalType.QUIZ_SCORE.value
_GOAL_STREAK = LearningGoalType.STREAK_DAYS.value

_SUPPORTED = {_GOAL_MASTERY, _GOAL_LESSONS, _GOAL_QUIZ, _GOAL_STREAK}

_STATUS_ACTIVE = "active"
_STATUS_ACHIEVED = "achieved"

_UNIT_BY_TYPE = {
    _GOAL_MASTERY: "%",
    _GOAL_LESSONS: "lessons",
    _GOAL_QUIZ: "%",
    _GOAL_STREAK: "days",
}

# Completed lesson detection matches learner_progress_service.
_COMPLETED_PERCENTAGE = 100.0


class LearningGoalService:
    """CRUD + derived-progress for a learner's goals."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        self._repo = LearningGoalRepository(uow.session)

    async def create_goal(
        self,
        user_id: uuid.UUID,
        *,
        goal_type: str,
        title: str,
        description: str | None = None,
        target_value: float | None = None,
        unit: str | None = None,
        target_date: date | None = None,
        path_id: str | None = None,
    ) -> LearningGoalView:
        if goal_type not in _SUPPORTED:
            raise ValidationError(
                message="Goal type is not supported by the automatic progress engine",
                details={"goal_type": goal_type},
            )
        path_uuid = None
        if path_id and str(path_id).startswith("path_"):
            from app.repositories.learning_path_repository import LearningPathRepository
            path = await LearningPathRepository(self._uow.session).get_by_user_and_public_id(
                user_id, str(path_id)
            )
            if path is None:
                raise NotFoundError(
                    message="Learning path not found",
                    details={"path_id": path_id},
                )
            path_uuid = path.id

        goal = LearningGoal(
            user_id=user_id,
            path_id=path_uuid,
            goal_type=goal_type,
            title=title,
            description=description,
            target_value=target_value,
            current_value=0.0,
            unit=unit or _UNIT_BY_TYPE.get(goal_type),
            status=_STATUS_ACTIVE,
            target_date=target_date,
        )
        await self._repo.persist(goal)
        await self._refresh_goal(user_id, goal)
        metrics.increment("p11_goals_created_total", goal_type=goal_type)
        return self._to_view(goal)

    async def list_goals(
        self, user_id: uuid.UUID, *, status: str | None = None
    ) -> list[LearningGoalView]:
        goals = await self._repo.list_by_user(user_id, status=status)
        refreshed = []
        for goal in goals:
            refreshed.append(await self._refresh_goal(user_id, goal))
        metrics.increment("p11_goal_reads_total", outcome="list", count=str(len(refreshed)))
        return [self._to_view(g) for g in refreshed]

    async def get_goal(self, user_id: uuid.UUID, goal_public_id: str) -> LearningGoalView:
        goal = await self._repo.get_by_user_and_public_id(user_id, goal_public_id)
        if goal is None:
            raise NotFoundError(
                message="Goal not found",
                details={"goal_id": goal_public_id},
            )
        await self._refresh_goal(user_id, goal)
        metrics.increment("p11_goal_reads_total", outcome="get")
        return self._to_view(goal)

    async def complete_goal(
        self, user_id: uuid.UUID, goal_public_id: str
    ) -> GoalCompleteResponse:
        goal = await self._repo.get_by_user_and_public_id(user_id, goal_public_id)
        if goal is None:
            raise NotFoundError(
                message="Goal not found",
                details={"goal_id": goal_public_id},
            )
        await self._refresh_goal(user_id, goal)
        if goal.status == _STATUS_ACHIEVED:
            metrics.increment("p11_goals_completed_total", outcome="idempotent")
            return self._completion_view(goal)
        if goal.progress_percent < 100.0:
            metrics.increment("p11_goals_completed_total", outcome="conflict")
            raise ConflictError(
                message="Goal target not yet met",
                details={
                    "goal_id": goal_public_id,
                    "current_value": goal.current_value,
                    "target_value": goal.target_value,
                    "progress_percent": round(goal.progress_percent, 1),
                },
            )
        goal.status = _STATUS_ACHIEVED
        goal.achieved_at = datetime.now(UTC)
        await self._repo.persist(goal)
        metrics.increment("p11_goals_completed_total", outcome="achieved")
        return self._completion_view(goal)

    # ------------------------------------------------------------------
    # Derivation
    # ------------------------------------------------------------------

    async def _refresh_goal(self, user_id: uuid.UUID, goal: LearningGoal) -> LearningGoal:
        derived = await self._derive_current_value(user_id, goal.goal_type)
        previous = goal.current_value
        goal.current_value = derived
        goal.unit = goal.unit or _UNIT_BY_TYPE.get(goal.goal_type)
        auto_achieved = False
        if goal.status == _STATUS_ACTIVE and goal.progress_percent >= 100.0:
            goal.status = _STATUS_ACHIEVED
            goal.achieved_at = goal.achieved_at or datetime.now(UTC)
            auto_achieved = True
        if derived != previous or auto_achieved:
            await self._repo.persist(goal)
        return goal

    async def _derive_current_value(self, user_id: uuid.UUID, goal_type: str) -> float:
        session = self._uow.session
        if goal_type in (_GOAL_MASTERY, _GOAL_STREAK):
            memory = await educational_memory_service.load_from_db(session, str(user_id))
            if goal_type == _GOAL_MASTERY:
                return round(float(memory.profile.average_mastery or 0.0), 1)
            return float(memory.profile.streak_days or 0)

        if goal_type == _GOAL_LESSONS:
            completed = (
                await session.execute(
                    select(func.count(func.distinct(LearningSession.lesson_id)))
                    .join(GeneratedLesson, LearningSession.lesson_id == GeneratedLesson.id)
                    .where(
                        LearningSession.user_id == user_id,
                        LearningSession.status == "completed",
                    )
                )
            ).scalar_one()
            return float(completed or 0)

        if goal_type == _GOAL_QUIZ:
            best = (
                await session.execute(
                    select(func.max(QuizAttempt.percent_score)).where(
                        QuizAttempt.user_id == user_id,
                        QuizAttempt.completed_at.is_not(None),
                    )
                )
            ).scalar_one()
            return round(float(best or 0.0), 1)

        return 0.0

    @staticmethod
    def _to_view(goal: LearningGoal) -> LearningGoalView:
        return LearningGoalView(
            id=goal.public_id,
            path_id=goal.path_id and str(goal.path_id) or None,
            goal_type=goal.goal_type,
            title=goal.title,
            description=goal.description,
            target_value=goal.target_value,
            current_value=round(float(goal.current_value or 0.0), 1),
            unit=goal.unit,
            status=goal.status,
            target_date=goal.target_date,
            progress_percent=round(goal.progress_percent, 1),
            achieved_at=goal.achieved_at,
            created_at=goal.created_at,
            updated_at=goal.updated_at,
        )

    def _completion_view(self, goal: LearningGoal) -> GoalCompleteResponse:
        if goal.status != _STATUS_ACHIEVED:
            goal.status = _STATUS_ACHIEVED
        return GoalCompleteResponse(
            id=goal.public_id,
            status=goal.status,
            current_value=round(float(goal.current_value or 0.0), 1),
            target_value=goal.target_value,
            progress_percent=round(goal.progress_percent, 1),
            achieved_at=goal.achieved_at,
        )
