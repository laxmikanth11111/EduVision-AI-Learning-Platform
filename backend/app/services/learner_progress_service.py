"""Learner Progress Dashboard service.

Composes existing, already-persisted learner intelligence into a single
learner-scoped progress view. This service does NOT introduce new analytics or
AI; it reuses:

  - ``educational_memory_service``  -> concept mastery (mastered/developing/weak)
  - ``recommendation_engine``       -> deterministic next-best actions
  - ``learning_sessions``           -> lesson progress + resume information
  - ``quiz_attempts``               -> assessment history + deterministic trend

Every query is learner-scoped by ``user_id`` (derived from the authenticated
user, never from the client) and bounded to avoid unbounded result sets and N+1
query patterns.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select

from app.database.unit_of_work import UnitOfWork
from app.models.concept import Concept
from app.models.generated_lesson import GeneratedLesson
from app.models.learning_session import LearningSession
from app.models.quiz import Quiz
from app.models.quiz_attempt import QuizAttempt
from app.schemas.learner_progress import (
    ConceptMasterySummary,
    LearnerProgressResponse,
    LessonProgressItem,
    RecentAttempt,
    RecommendationAction,
    Summary,
    TrendPoint,
)
from app.services.educational_memory_service import educational_memory_service
from app.services.recommendation_engine import generate_recommendations
from shared.constants import LearningSessionStatus

# Bounded result-set limits for the dashboard view.
_MAX_LESSONS = 50
_MAX_RECENT_ATTEMPTS = 10
_MAX_TREND_POINTS = 10
_MAX_CONCEPTS = 100
_MAX_ACTIONS = 5

# Mastery classification thresholds (aligned with educational_memory_service /
# recommendation_engine — do NOT redefine).
_MASTERED_THRESHOLD = 85.0
_WEAK_THRESHOLD = 50.0
_COMPLETED_PERCENTAGE = 100.0

_COMPLETED_STATUSES = {
    LearningSessionStatus.COMPLETED.value,
}


class LearnerProgressService:
    """Build the learner-scoped progress payload for the dashboard."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def get_progress(self, user_id: uuid.UUID) -> LearnerProgressResponse:
        """Return the deterministic progress view for a single learner."""
        session = self._uow.session
        user_str = str(user_id)

        # 1. Lesson progress (set-based join; one round trip).
        lesson_items, completed_count, in_progress_count = await self._lesson_progress(
            session, user_id
        )

        # 2. Assessment history + total attempts (set-based; one round trip).
        attempts, total_attempts = await self._attempt_history(session, user_id)

        # 3. Mastery (reuses educational memory exactly as the lesson player).
        memory = await educational_memory_service.load_from_db(session, user_str)
        summary = Summary(
            lessons_completed=completed_count,
            lessons_in_progress=in_progress_count,
            average_mastery=memory.profile.average_mastery,
            mastered_concepts=len(memory.mastered_concepts),
            developing_concepts=len(memory.developing_concepts),
            weak_concepts=len(memory.weak_concepts),
            attempts_total=total_attempts,
        )

        # 4. Deterministic recommendations (reuse the engine, no rewrite).
        recommendation = generate_recommendations(user_str, memory, max_actions=_MAX_ACTIONS)
        lesson_by_concept = await self._action_lesson_map(session, recommendation.actions)
        actions = [
            RecommendationAction(
                action_type=a.action_type.value,
                concept_id=a.concept_id,
                concept_name=a.concept_name,
                title=a.title,
                description=a.description,
                reason=a.reason,
                activity_type=a.activity_type.value,
                priority=a.priority.value,
                lesson_id=lesson_by_concept.get(a.concept_id),
            )
            for a in recommendation.actions
        ]

        concept_mastery = self._concept_mastery_summaries(memory.concept_records)
        weak = [
            {
                "concept_id": cid,
                "concept_name": _concept_name(memory, cid),
                "mastery_score": memory.concept_records[cid].mastery_score,
            }
            for cid in memory.weak_concepts[:_MAX_CONCEPTS]
        ]
        strong = [
            {
                "concept_id": cid,
                "concept_name": _concept_name(memory, cid),
                "mastery_score": memory.concept_records[cid].mastery_score,
            }
            for cid in memory.mastered_concepts[:_MAX_CONCEPTS]
        ]

        return LearnerProgressResponse(
            summary=summary,
            lesson_progress=lesson_items,
            concept_mastery=concept_mastery,
            weak_concepts=weak,
            strong_concepts=strong,
            recommendations=actions,
            recommendations_summary=recommendation.summary,
            recent_attempts=attempts,
            trend=self._build_trend(attempts),
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _lesson_progress(
        self, session: Any, user_id: uuid.UUID
    ) -> tuple[list[LessonProgressItem], int, int]:
        """Aggregate learner lesson progress from learning sessions + lessons.

        Uses a single join query (no N+1). Distinct lessons are summed from the
        learner's own sessions only.
        """
        stmt = (
            select(LearningSession, GeneratedLesson)
            .join(GeneratedLesson, LearningSession.lesson_id == GeneratedLesson.id)
            .where(LearningSession.user_id == user_id)
            .order_by(LearningSession.last_activity_at.desc().nulls_last())
        )
        rows = (await session.execute(stmt)).all()

        by_lesson: dict[uuid.UUID, dict[str, Any]] = {}
        for lsess, lesson in rows:
            entry = by_lesson.get(lesson.id)
            if entry is None:
                # Rows are newest-first, so the first session seen for a lesson
                # is the one the learner most recently stopped on: its slide
                # position drives the resume deep-link.
                resume_slide = int(lsess.current_slide_position or 0)
                resume_link = (
                    f"/frontend/player.html?lesson={lesson.public_id}&slide={resume_slide}"
                    if lesson.public_id
                    else ""
                )
                by_lesson[lesson.id] = {
                    "public_id": lesson.public_id,
                    "title": lesson.title or "Untitled lesson",
                    "completion": 0.0,
                    "status": "in_progress",
                    "last_activity_at": lsess.last_activity_at,
                    "resume_slide": resume_slide,
                    "resume_link": resume_link,
                }
            entry = by_lesson[lesson.id]
            entry["completion"] = max(
                entry["completion"], float(lsess.completion_percentage or 0.0)
            )
            if (
                lsess.status in _COMPLETED_STATUSES
                or float(lsess.completion_percentage or 0.0) >= _COMPLETED_PERCENTAGE
            ):
                entry["status"] = "completed"
            if entry["last_activity_at"] is None or (
                lsess.last_activity_at and lsess.last_activity_at > entry["last_activity_at"]
            ):
                entry["last_activity_at"] = lsess.last_activity_at

        lesson_items: list[LessonProgressItem] = []
        completed_count = 0
        in_progress_count = 0
        for lesson in by_lesson.values():
            is_completed = lesson["status"] == "completed"
            if is_completed:
                completed_count += 1
            else:
                in_progress_count += 1
            if len(lesson_items) < _MAX_LESSONS:
                lesson_items.append(
                    LessonProgressItem(
                        lesson_id=lesson["public_id"],
                        title=lesson["title"],
                        completion_percentage=round(lesson["completion"], 1),
                        status=lesson["status"],
                        last_activity_at=lesson["last_activity_at"],
                        resume_slide=lesson["resume_slide"],
                        resume_link=lesson["resume_link"],
                    )
                )
        return lesson_items, completed_count, in_progress_count

    async def _attempt_history(
        self, session: Any, user_id: uuid.UUID
    ) -> tuple[list[RecentAttempt], int]:
        """Return recent completed attempts + a bounded total count.

        Two set-based queries (no N+1): one count, one join to quiz metadata.
        """
        total = (
            await session.execute(
                select(func.count()).select_from(QuizAttempt).where(QuizAttempt.user_id == user_id)
            )
        ).scalar_one()

        stmt = (
            select(QuizAttempt, Quiz)
            .join(Quiz, QuizAttempt.quiz_id == Quiz.id)
            .where(QuizAttempt.user_id == user_id)
            .order_by(
                QuizAttempt.completed_at.desc().nulls_last(),
                QuizAttempt.created_at.desc(),
            )
            .limit(_MAX_RECENT_ATTEMPTS + _MAX_TREND_POINTS)
        )
        rows = (await session.execute(stmt)).all()

        attempts: list[RecentAttempt] = []
        for attempt, quiz in rows:
            passed: bool | None = None
            if attempt.percent_score is not None and quiz.passing_score is not None:
                passed = float(attempt.percent_score) >= float(quiz.passing_score)
            attempts.append(
                RecentAttempt(
                    attempt_id=attempt.public_id,
                    quiz_id=quiz.public_id,
                    lesson_id=str(quiz.lesson_id) if quiz.lesson_id else None,
                    title=quiz.title or "Assessment",
                    score=float(attempt.score) if attempt.score is not None else None,
                    max_score=float(attempt.max_score) if attempt.max_score is not None else None,
                    percent_score=float(attempt.percent_score)
                    if attempt.percent_score is not None
                    else None,
                    passed=passed,
                    completed_at=attempt.completed_at,
                )
            )
        return attempts, int(total)

    async def _action_lesson_map(self, session: Any, actions: list[Any]) -> dict[str, str | None]:
        """Resolve concept -> lesson public id for recommendation actions.

        A single set-based join (concept -> lesson) so deep-linking a dashboard
        action to the lesson player is O(1) per action with no N+1.
        """
        concept_ids = [a.concept_id for a in actions if a.concept_id]
        result: dict[str, str | None] = {}
        if not concept_ids:
            return result
        rows = (
            await session.execute(
                select(Concept.public_id, GeneratedLesson.public_id)
                .join(GeneratedLesson, Concept.lesson_id == GeneratedLesson.id)
                .where(Concept.public_id.in_(concept_ids))
            )
        ).all()
        for cid, lesson_public_id in rows:
            result[cid] = lesson_public_id
        for cid in concept_ids:
            result.setdefault(cid, None)
        return result

    def _concept_mastery_summaries(
        self, concept_records: dict[str, Any]
    ) -> list[ConceptMasterySummary]:
        result: list[ConceptMasterySummary] = []
        for cid in list(concept_records.keys())[:_MAX_CONCEPTS]:
            rec = concept_records[cid]
            score = float(rec.mastery_score)
            if score >= _MASTERED_THRESHOLD:
                status = "mastered"
            elif score >= _WEAK_THRESHOLD:
                status = "developing"
            else:
                status = "weak"
            result.append(
                ConceptMasterySummary(
                    concept_id=cid,
                    concept_name=rec.concept_name,
                    mastery_score=round(score, 1),
                    status=status,
                    review_count=int(rec.review_count),
                    trend=rec.trend,
                )
            )
        return result

    @staticmethod
    def _build_trend(attempts: list[RecentAttempt]) -> list[TrendPoint]:
        """Build a simple deterministic score-over-recent-attempts trend.

        Attempts arrive newest-first; return oldest->newest so the chart reads
        left-to-right over time. Bounded to ``_MAX_TREND_POINTS``.
        """
        points: list[TrendPoint] = []
        for attempt in reversed(attempts[:_MAX_TREND_POINTS]):
            points.append(
                TrendPoint(
                    label=attempt.completed_at.strftime("%Y-%m-%d") if attempt.completed_at else "",
                    value=attempt.percent_score,
                    source="quiz_attempt",
                )
            )
        return points


def _concept_name(memory: Any, concept_id: str) -> str:
    rec = memory.concept_records.get(concept_id)
    return rec.concept_name if rec else concept_id
