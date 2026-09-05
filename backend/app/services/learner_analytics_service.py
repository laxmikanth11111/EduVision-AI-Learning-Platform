"""Learner Analytics service (P13) — "Know my trajectory".

Read-composes ONLY existing learner-scoped rows (``quiz_attempts``,
``score_summaries``, ``learning_sessions`` + the cache-backed educational
memory) into the deterministic trajectories exposed by ``/me/analytics/*``:

  * overview   — attempts/accuracy/mastery-band summary + trend + current focus
  * trend      — per-date accuracy trajectory (bounded window)
  * concepts   — per-concept band, up/flat/down arrow + actionable deep-links
  * effort     — attempts/sessions/time vs mastery gained, per concept

Design rules (mirroring ``learner_progress_service``):
  * every query filtered by ``user_id`` at the SQL layer (never client-supplied)
  * bounded result sets via module-level ``_MAX_*`` limits
  * anchors on SQLAlchemy aggregates (count/avg/sum) with explicit filters
  * bulk ``IN`` loads instead of per-concept subqueries (no N+1)
  * no writes anywhere — this service never persists anything

Mastery comes from ``educational_memory_service`` (cache-backed, one DB hit on
miss). ``delta_mastery``/``mastery_delta`` are NOT stored anywhere: the memory
blob persists only a categorical trend, so a numeric movement is derived
deterministically from the concept's own bounded attempt-percent series
(trend_delta over recent-vs-earlier percent) and reported only when at least
two completed attempts back it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.unit_of_work import UnitOfWork
from app.models.concept import Concept
from app.models.generated_lesson import GeneratedLesson
from app.models.learning_session import LearningSession
from app.models.quiz import Quiz
from app.models.quiz_attempt import QuizAttempt
from app.models.review_schedule import ReviewSchedule
from app.models.score_summary import ScoreSummary
from app.repositories.review_schedule_repository import ReviewScheduleRepository
from app.schemas.educational_memory import ConceptMasteryRecord, EducationalMemory
from app.schemas.learner_analytics import (
    AnalyticsOverview,
    ConceptAnalytic,
    ConceptFocus,
    ConceptsResponse,
    EffortAnalytic,
    EffortResponse,
    RetentionConcept,
    RetentionResponse,
    RetentionSummary,
    TrendPoint,
    TrendResponse,
)
from app.services import retention
from app.services.educational_memory_service import educational_memory_service
from app.services.learner_analytics import (
    band,
    band_rank,
    clamp_window,
    classify_trend,
    gain_per_attempt,
    trend_delta,
)

# Bounded result-set limits (hard caps — see P13 section 15).
_MAX_TREND_ATTEMPTS_SCAN = 60  # attempts that may feed the daily trend buckets
_MAX_ATTEMPTS_SCAN = 500       # attempts that may feed concept deltas/effort
_MAX_CONCEPTS = 100            # concepts surfaced by /concepts and /effort
_MAX_EFFORT_ROWS = 100         # effort rows surfaced (same bound as concepts)

# A completed quiz attempt is the only row treated as a measurement point.
_ATTEMPT_COMPLETED = "completed"
_COMPLETED_SESSION_STATUSES = {"completed"}


class LearnerAnalyticsService:
    """Deterministic, learner-scoped analytics read service."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    @property
    def session(self) -> AsyncSession:
        return self._uow.session

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_overview(self, user_id: uuid.UUID) -> AnalyticsOverview:
        session = self.session
        user_str = str(user_id)

        count, avg_percent = (
            await session.execute(
                select(func.count(), func.avg(QuizAttempt.percent_score))
                .select_from(QuizAttempt)
                .where(
                    QuizAttempt.user_id == user_id,
                    QuizAttempt.status == _ATTEMPT_COMPLETED,
                )
            )
        ).one()
        attempts_taken = int(count or 0)
        avg = round(float(avg_percent), 1) if avg_percent is not None else None

        session_count = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(LearningSession)
                    .where(
                        LearningSession.user_id == user_id,
                        LearningSession.status.in_(_COMPLETED_SESSION_STATUSES),
                    )
                )
            ).scalar_one()
            or 0
        )

        memory = await self._load_memory(session, user_str)
        mastered_count = len(memory.mastered_concepts)
        developing_count = len(memory.developing_concepts)
        weak_count = len(memory.weak_concepts)

        trend_percent: float | None = None
        if attempts_taken > 0:
            rows = await self._completed_attempt_rows(
                session, user_id, limit=_MAX_TREND_ATTEMPTS_SCAN
            )
            percents = [row["percent"] for row in rows if row["percent"] is not None]
            percents_oldest_first = list(reversed(percents))
            trend_percent = _rounded(trend_delta(percents_oldest_first))

        current_focus = await self._current_focus(session, user_id, memory)

        return AnalyticsOverview(
            attempts_taken=attempts_taken,
            avg_percent=avg,
            mastered_count=mastered_count,
            developing_count=developing_count,
            weak_count=weak_count,
            session_count=session_count,
            trend_percent=trend_percent,
            current_focus=current_focus,
        )

    async def get_trend(self, user_id: uuid.UUID, window: int | None) -> TrendResponse:
        """Per-date accuracy trajectory, bounded and clamped to ``[1, 30]``."""
        session = self.session
        window = clamp_window(window)

        rows = await self._completed_attempt_rows(
            session, user_id, limit=_MAX_TREND_ATTEMPTS_SCAN
        )
        buckets: dict[str, dict[str, Any]] = {}
        for row in rows:
            attempted_at = row["attempted_at"]
            day = attempted_at.date().isoformat() if attempted_at else "unknown"
            bucket = buckets.setdefault(
                day,
                {
                    "correct": 0,
                    "incorrect": 0,
                    "attempts": 0,
                    "percent_sum": 0.0,
                    "percent_n": 0,
                },
            )
            bucket["correct"] = int(bucket["correct"]) + row["correct"]
            bucket["incorrect"] = int(bucket["incorrect"]) + row["incorrect"]
            bucket["attempts"] = int(bucket["attempts"]) + 1
            if row["percent"] is not None:
                bucket["percent_sum"] = float(bucket["percent_sum"]) + row["percent"]
                bucket["percent_n"] = int(bucket["percent_n"]) + 1

        ordered_days = list(buckets)  # newest-first thanks to row ordering
        ordered_days.reverse()  # oldest -> newest
        recent_days = ordered_days[-window:] if window else []

        points = [
            TrendPoint(
                date=day,
                correct=int(bucket["correct"]),
                incorrect=int(bucket["incorrect"]),
                percent=(
                    round(float(bucket["percent_sum"]) / int(bucket["percent_n"]), 1)
                    if int(bucket["percent_n"])
                    else None
                ),
                attempts=int(bucket["attempts"]),
            )
            for day, bucket in ((d, buckets[d]) for d in recent_days)
        ]
        return TrendResponse(points=points, window=window)

    async def get_concepts(self, user_id: uuid.UUID) -> ConceptsResponse:
        session = self.session
        memory = await self._load_memory(session, str(user_id))

        records = list(memory.concept_records.items())[:_MAX_CONCEPTS]
        concept_ids = [cid for cid, _ in records]
        activity = await self._load_concept_activity(session, user_id, concept_ids)

        entries: list[tuple[tuple[int, float, str], ConceptAnalytic]] = []
        for cid, rec in records:
            score = float(rec.mastery_score)
            act = activity[cid]
            delta = _rounded(trend_delta(act["percent_series"]))
            analytic = ConceptAnalytic(
                concept_public_id=cid,
                name=rec.concept_name or cid,
                band=band(score),
                trend=classify_trend(rec.trend),
                current_mastery=round(score, 1),
                delta_mastery=delta,
                review_count=int(rec.review_count),
                deep_link_practice=(
                    f"/frontend/player.html?lesson={act['lesson_public']}"
                    if act["lesson_public"]
                    else None
                ),
                deep_link_tutor=f"/frontend/tutor.html?concept={cid}",
            )
            key = (band_rank(analytic.band), -score, cid)
            entries.append((key, analytic))

        entries.sort(key=lambda pair: pair[0])
        return ConceptsResponse(
            concepts=[analytic for _, analytic in entries],
            max=_MAX_CONCEPTS,
        )

    async def get_effort(self, user_id: uuid.UUID) -> EffortResponse:
        session = self.session
        memory = await self._load_memory(session, str(user_id))

        records = list(memory.concept_records.items())[:_MAX_CONCEPTS]
        concept_ids = [cid for cid, _ in records]
        activity = await self._load_concept_activity(session, user_id, concept_ids)

        entries: list[tuple[tuple[int, int, str], EffortAnalytic]] = []
        for cid, rec in records:
            act = activity[cid]
            score = float(rec.mastery_score)
            delta = _rounded(trend_delta(act["percent_series"]))
            analytic = EffortAnalytic(
                concept_public_id=cid,
                name=rec.concept_name or cid,
                attempts=act["attempts"],
                sessions=act["sessions"],
                time_seconds=act["time_seconds"],
                mastery_delta=delta,
                efficiency=_rounded2(gain_per_attempt(delta, act["attempts"])),
            )
            key = (band_rank(band(score)), -act["attempts"], cid)
            entries.append((key, analytic))

        entries.sort(key=lambda pair: pair[0])
        return EffortResponse(
            effort=[anal for _, anal in entries][:_MAX_EFFORT_ROWS],
            max=_MAX_EFFORT_ROWS,
        )

    async def get_retention(self, user_id: uuid.UUID) -> RetentionResponse:
        """Deterministic, learner-scoped retention/recall surface (P14).

        Composes the learner's own review schedules + recall-outcome history
        into an overdue-first list of concept signals. Read-only: it never
        rewrites mastery or review state.
        """
        session = self.session
        now = datetime.now(UTC)
        memory = await self._load_memory(session, str(user_id))

        records = list(memory.concept_records.items())[:_MAX_CONCEPTS]
        concept_ids = [cid for cid, _ in records]
        if not concept_ids:
            return RetentionResponse(
                summary=RetentionSummary(
                    retention_average=None,
                    on_track_count=0,
                    at_risk_count=0,
                    overdue_count=0,
                    new_count=0,
                ),
                concepts=[],
                max=_MAX_CONCEPTS,
            )

        links = await self._resolve_lessons(session, concept_ids, user_id)
        schedules = await ReviewScheduleRepository(session).list_due(
            user_id, limit=_MAX_CONCEPTS
        )
        by_concept: dict[str, ReviewSchedule] = {}
        for sched_row in schedules:
            if sched_row.concept is not None and sched_row.concept.public_id:
                by_concept.setdefault(sched_row.concept.public_id, sched_row)
        rows: list[RetentionConcept] = []
        for cid, rec in records:
            schedule = by_concept.get(cid)
            history = (
                retention.history_outcomes(schedule.review_metadata)
                if schedule is not None
                else []
            )
            days_since = _retention_days_since(rec, schedule, now)
            is_due = False
            due_dt: datetime | None = None
            if schedule is not None:
                due_dt = _aware(schedule.due_at)
                is_due = due_dt is None or due_dt <= now

            signal = retention.retention_signal(
                mastery=float(rec.mastery_score),
                days_since_review=days_since,
                is_due=is_due,
                history=history,
            )
            score = float(rec.mastery_score)
            rows.append(
                RetentionConcept(
                    concept_public_id=cid,
                    name=rec.concept_name or cid,
                    band=band(score),
                    mastery_score=round(score, 1),
                    retained_strength=signal["retained_strength"],
                    status=signal["status"],
                    due_at=due_dt,
                    days_since_review=days_since,
                    review_count=int(rec.review_count),
                    review_accuracy=retention.review_accuracy(history),
                    deep_link_practice=(
                        f"/frontend/player.html?lesson={links[cid]['lesson_public']}"
                        if links[cid]["lesson_public"]
                        else None
                    ),
                    deep_link_tutor=f"/frontend/tutor.html?concept={cid}",
                )
            )

        rows.sort(
            key=lambda row: (
                retention.status_sort_key(row.status),
                -_strength_rank(row.retained_strength),
                row.concept_public_id,
            )
        )
        bounded = rows[:_MAX_CONCEPTS]

        summary = retention.retention_summary(
            strengths=[row.retained_strength for row in bounded],
            statuses=[row.status for row in bounded],
        )
        return RetentionResponse(
            summary=RetentionSummary(
                retention_average=summary["retention_average"],
                on_track_count=summary["on_track_count"],
                at_risk_count=summary["at_risk_count"],
                overdue_count=summary["overdue_count"],
                new_count=summary["new_count"],
            ),
            concepts=bounded,
            max=_MAX_CONCEPTS,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _load_memory(self, session: AsyncSession, user_str: str) -> EducationalMemory:
        return await educational_memory_service.load_from_db(session, user_str)

    async def _completed_attempt_rows(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Completed attempts (newest first) with optional score summary.

        LEFT-joins ``score_summaries`` so legacy attempts without a summary row
        still contribute a date/percent measurement with zero correct/incorrect.
        """
        rows = (
            await session.execute(
                select(QuizAttempt, ScoreSummary)
                .outerjoin(ScoreSummary, ScoreSummary.attempt_id == QuizAttempt.id)
                .where(
                    QuizAttempt.user_id == user_id,
                    QuizAttempt.status == _ATTEMPT_COMPLETED,
                )
                .order_by(
                    QuizAttempt.completed_at.desc().nulls_last(),
                    QuizAttempt.created_at.desc(),
                )
                .limit(limit)
            )
        ).all()
        return [
            {
                "percent": float(attempt.percent_score)
                if attempt.percent_score is not None
                else None,
                "correct": int(summary.correct_count) if summary else 0,
                "incorrect": int(summary.incorrect_count) if summary else 0,
                "attempted_at": attempt.completed_at or attempt.created_at,
            }
            for attempt, summary in rows
        ]

    async def _resolve_lessons(
        self,
        session: AsyncSession,
        concept_public_ids: list[str],
        user_id: uuid.UUID,
    ) -> dict[str, dict[str, Any]]:
        """Map concept public id -> its lesson (internal uuid + public id).

        Direct ``Concept.lesson_id`` when present; otherwise the learner's own
        most-recently-created lesson for the concept's presentation. Batched so
        the fixed ``<=100`` concept window costs at most three queries.
        """
        result: dict[str, dict[str, Any]] = {}
        if not concept_public_ids:
            return result
        for cid in concept_public_ids:
            result[cid] = {"lesson_uuid": None, "lesson_public": None}

        concept_rows = (
            await session.execute(
                select(Concept.public_id, Concept.lesson_id, Concept.presentation_id)
                .where(Concept.public_id.in_(concept_public_ids))
            )
        ).all()
        concept_info: dict[str, tuple[uuid.UUID | None, uuid.UUID | None]] = {}
        for public, lesson_id, presentation_id in concept_rows:
            concept_info[public] = (lesson_id, presentation_id)

        direct_ids: set[uuid.UUID] = set()
        for cid in concept_public_ids:
            lesson_id, _ = concept_info.get(cid, (None, None))
            if lesson_id is not None:
                result[cid]["lesson_uuid"] = lesson_id
                direct_ids.add(lesson_id)

        fallback_ids = [
            cid for cid in concept_public_ids if result[cid]["lesson_uuid"] is None
        ]
        presentation_ids = [
            concept_info[cid][1]
            for cid in fallback_ids
            if concept_info.get(cid) and concept_info[cid][1] is not None
        ]
        if presentation_ids:
            lesson_rows = (
                await session.execute(
                    select(
                        GeneratedLesson.presentation_id,
                        GeneratedLesson.id,
                        GeneratedLesson.public_id,
                    )
                    .where(
                        GeneratedLesson.presentation_id.in_(presentation_ids),
                        GeneratedLesson.user_id == user_id,
                    )
                    .order_by(
                        GeneratedLesson.created_at.desc(),
                        GeneratedLesson.id.desc(),
                    )
                )
            ).all()
            lesson_by_presentation: dict[
                uuid.UUID, tuple[uuid.UUID, str]
            ] = {}
            for presentation_id, lesson_id, lesson_public in lesson_rows:
                lesson_by_presentation.setdefault(
                    presentation_id, (lesson_id, lesson_public)
                )
            for cid in fallback_ids:
                _, presentation_id = concept_info.get(cid, (None, None))
                if (
                    presentation_id is not None
                    and presentation_id in lesson_by_presentation
                ):
                    lesson_id, lesson_public = lesson_by_presentation[presentation_id]
                    result[cid]["lesson_uuid"] = lesson_id
                    result[cid]["lesson_public"] = lesson_public

        if direct_ids:
            public_rows = (
                await session.execute(
                    select(GeneratedLesson.id, GeneratedLesson.public_id).where(
                        GeneratedLesson.id.in_(direct_ids)
                    )
                )
            ).all()
            public_by_id: dict[uuid.UUID, str] = {}
            for lesson_id, lesson_public in public_rows:
                public_by_id[lesson_id] = lesson_public
            for cid in concept_public_ids:
                lesson_id = result[cid]["lesson_uuid"]
                if lesson_id is not None:
                    result[cid]["lesson_public"] = public_by_id.get(lesson_id)
        return result

    async def _load_concept_activity(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        concept_public_ids: list[str],
    ) -> dict[str, dict[str, Any]]:
        """Per-concept effort/accuracy inputs via batched joins (no N+1)."""
        activity: dict[str, dict[str, Any]] = {}
        for cid in concept_public_ids:
            activity[cid] = {
                "lesson_uuid": None,
                "lesson_public": None,
                "attempts": 0,
                "time_seconds": 0,
                "sessions": 0,
                "percent_series": [],
            }
        if not concept_public_ids:
            return activity

        links = await self._resolve_lessons(session, concept_public_ids, user_id)
        for cid in concept_public_ids:
            activity[cid]["lesson_uuid"] = links[cid]["lesson_uuid"]
            activity[cid]["lesson_public"] = links[cid]["lesson_public"]

        lesson_ids = [
            links[cid]["lesson_uuid"]
            for cid in concept_public_ids
            if links[cid]["lesson_uuid"]
        ]
        if not lesson_ids:
            return activity

        session_rows = (
            await session.execute(
                select(LearningSession.lesson_id, func.count())
                .where(
                    LearningSession.user_id == user_id,
                    LearningSession.lesson_id.in_(lesson_ids),
                    LearningSession.status.in_(_COMPLETED_SESSION_STATUSES),
                )
                .group_by(LearningSession.lesson_id)
            )
        ).all()
        sessions_by_lesson = {lesson_id: int(count) for lesson_id, count in session_rows}

        attempt_rows = (
            await session.execute(
                select(
                    QuizAttempt.percent_score,
                    QuizAttempt.time_spent_seconds,
                    Quiz.lesson_id,
                )
                .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
                .where(
                    QuizAttempt.user_id == user_id,
                    QuizAttempt.status == _ATTEMPT_COMPLETED,
                    Quiz.lesson_id.in_(lesson_ids),
                )
                .order_by(
                    QuizAttempt.completed_at.desc().nulls_last(),
                    QuizAttempt.created_at.desc(),
                )
                .limit(_MAX_ATTEMPTS_SCAN)
            )
        ).all()

        per_lesson: dict[uuid.UUID, dict[str, Any]] = {}
        for percent, time_spent, lesson_id in attempt_rows:
            bucket = per_lesson.setdefault(
                lesson_id, {"attempts": 0, "seconds": 0, "percents": []}
            )
            bucket["attempts"] = int(bucket["attempts"]) + 1
            bucket["seconds"] = int(bucket["seconds"]) + int(time_spent or 0)
            if percent is not None:
                bucket["percents"].append(float(percent))

        for cid in concept_public_ids:
            lesson_id = activity[cid]["lesson_uuid"]
            if lesson_id is None:
                continue
            bucket = per_lesson.get(lesson_id, {})
            activity[cid]["attempts"] = int(bucket.get("attempts", 0))
            activity[cid]["time_seconds"] = int(bucket.get("seconds", 0))
            activity[cid]["sessions"] = int(
                sessions_by_lesson.get(lesson_id, 0)
            )
            percents: list[float] = bucket.get("percents", [])
            if len(percents) > 1:
                activity[cid]["percent_series"] = list(reversed(percents))
        return activity

    async def _current_focus(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        memory: EducationalMemory,
    ) -> ConceptFocus | None:
        """Weakest actionable concept (weak band first, then lowest mastery)."""
        focus_ids = [
            cid
            for cid in (
                list(memory.weak_concepts[:_MAX_CONCEPTS])
                + list(memory.developing_concepts[:_MAX_CONCEPTS])
            )
            if cid in memory.concept_records
        ]
        if not focus_ids:
            return None
        ranked = sorted(
            (
                (
                    (
                        band_rank(
                            band(float(memory.concept_records[cid].mastery_score))
                        ),
                        float(memory.concept_records[cid].mastery_score),
                        cid,
                    ),
                    cid,
                )
                for cid in focus_ids
            ),
            key=lambda pair: pair[0],
        )
        _, cid = ranked[0]
        rec = memory.concept_records[cid]
        links = await self._resolve_lessons(session, [cid], user_id)
        lesson_public = links[cid]["lesson_public"]
        deep_link = (
            f"/frontend/player.html?lesson={lesson_public}"
            if lesson_public
            else f"/frontend/tutor.html?concept={cid}"
        )
        return ConceptFocus(
            concept_public_id=cid,
            name=rec.concept_name or cid,
            band=band(float(rec.mastery_score)),
            deep_link=deep_link,
        )


def _rounded(value: float | None, digits: int = 1) -> float | None:
    return round(value, digits) if value is not None else None


def _rounded2(value: float | None) -> float | None:
    return _rounded(value, digits=2)


def _aware(dt: datetime | None) -> datetime | None:
    """Treat a naive stored datetime as UTC (SQLite drops tzinfo on read)."""
    if dt is None or dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=UTC)


def _strength_rank(strength: float | None) -> float:
    """Deterministic sort helper: ``None`` sorts behind any real strength."""
    return strength if strength is not None else -1.0


def _retention_days_since(
    record: ConceptMasteryRecord,
    schedule: ReviewSchedule | None,
    now: datetime,
) -> float | None:
    """Days since a concept was last reviewed (None means never reviewed).

    A concept only enters the retention loop once it has a review schedule;
    unscheduled concepts are ``new`` (no fabricated strength). Prefers the
    educational-memory anchor (same precedence as the review scheduler's decay
    signal), then the schedule's own review clock.
    """
    if schedule is None:
        return None
    anchor = None
    if record.last_reviewed_at or record.first_learned_at:
        anchor = float(record.last_reviewed_at or record.first_learned_at)
    elif schedule.last_reviewed_at is not None:
        aware = _aware(schedule.last_reviewed_at)
        if aware is not None:
            anchor = aware.timestamp()
    if anchor is None:
        return None
    return max(0.0, (now.timestamp() - anchor) / 86400.0)
