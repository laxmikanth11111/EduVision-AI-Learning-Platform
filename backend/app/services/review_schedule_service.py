"""Learner-scoped adaptive review engine service (P10).

Coordinates the deterministic spaced-repetition scheduler (``review_scheduler``)
with the ``review_schedules`` persistence layer and the learner's educational
memory, exposing a time-aware, actionable review queue.

Every operation is learner-scoped and ownership 404-equalized:
  - ``user_id`` comes from the authenticated user, never the client.
  - Review schedules are resolved against the owning user and the resolved
    concept belongs to that user's presentation/lesson chain.

The service is deterministic — no AI, no ML. It never rewrites persisted
mastery; it only schedules reviews and resets the review clock.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.core.exceptions import NotFoundError
from app.database.unit_of_work import UnitOfWork
from app.models.concept import Concept
from app.models.review_schedule import ReviewSchedule
from app.repositories.concept_repository import ConceptRepository
from app.repositories.review_schedule_repository import ReviewScheduleRepository
from app.schemas.educational_memory import ConceptMasteryRecord, EducationalMemory
from app.schemas.review import (
    ReviewCompleteResponse,
    ReviewQueueItem,
    ReviewQueueResponse,
)
from app.services import retention, review_scheduler
from app.services.educational_memory_service import educational_memory_service
from app.services.review_scheduler import (
    compute_decay_signal,
    initial_step,
    interval_at_step,
    priority_bucket,
)

_STATUS_SCHEDULED = "scheduled"
_STATUS_COMPLETED = "completed"

# A concept is treated as needing ongoing review while its mastery is below the
# mastered threshold; mastered concepts are not auto-rescheduled.
_THRESHOLD_MASTERED = 85.0

_DEFAULT_QUEUE_LIMIT = 100


def _aware(dt: datetime | None) -> datetime | None:
    """Treat a naive stored datetime as UTC (SQLite drops tzinfo on read).

    PostgreSQL preserves the tz-aware value; either way the result is an
    aware UTC datetime suitable for comparison and serialization.
    """
    if dt is None or dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=UTC)


class ReviewScheduleService:
    """Deterministic spaced-repetition review scheduling for a learner."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        self._repo = ReviewScheduleRepository(uow.session)
        self._concept_repo = ConceptRepository(uow.session)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def list_due(
        self,
        user_id: uuid.UUID,
        *,
        limit: int = _DEFAULT_QUEUE_LIMIT,
        now: datetime | None = None,
    ) -> ReviewQueueResponse:
        """Return the learner's bounded, time-aware review queue.

        Lazily seeds schedules for weak/developing concepts from the learner's
        educational memory, then returns only items that are currently due
        (plus the total number of active schedules).
        """
        user_str = str(user_id)
        session = self._uow.session
        now = now or datetime.now(UTC)
        memory = await educational_memory_service.load_from_db(session, user_str)
        await self._ensure_schedules(memory, user_id, user_str, now)

        active = await self._repo.list_due(user_id, limit=limit)
        items: list[ReviewQueueItem] = []
        due_count = 0
        for schedule in active:
            due_dt = _aware(schedule.due_at)
            is_due = due_dt is None or due_dt <= now
            if is_due:
                due_count += 1
            item = self._build_queue_item(schedule, memory, now)
            if is_due:
                items.append(item)
        items.sort(key=lambda i: _priority_rank(i.priority))
        return ReviewQueueResponse(
            items=items[:limit],
            total=len(active),
            due_count=due_count,
        )

    async def complete(
        self,
        user_id: uuid.UUID,
        schedule_public_id: str,
        *,
        outcome: str = retention.DEFAULT_OUTCOME,
        now: datetime | None = None,
    ) -> ReviewCompleteResponse:
        """Mark a review schedule complete, advancing its spaced interval.

        The routine uses the learner's self-reported recall outcome (P14) to
        drive the next step: ``again`` -> tightest interval, ``hard`` -> hold,
        ``good`` -> +1 (identical to legacy), ``easy`` -> +2 (capped). The
        outcome and the resulting retention signal are recorded in the
        ``review_metadata`` JSONB (bounded history). It never changes mastery;
        it resets the review clock on the learner's educational memory and
        advances the interval ladder.
        """
        outcome = retention.validate_outcome(outcome)
        user_str = str(user_id)
        session = self._uow.session
        now = now or datetime.now(UTC)

        schedule = await self._repo.get_by_user_and_public_id(
            user_id, schedule_public_id
        )
        if schedule is None:
            raise NotFoundError(
                message="Review schedule not found",
                details={"schedule_id": schedule_public_id},
            )

        memory = await educational_memory_service.load_from_db(session, user_str)
        step = int((schedule.review_metadata or {}).get("step", 0) or 0)
        next_step = retention.outcome_next_step(step, outcome)
        next_interval_days = retention.outcome_interval_days(step, outcome)

        schedule.last_reviewed_at = now
        schedule.completed_at = now
        schedule.interval_days = int(next_interval_days)
        schedule.review_metadata = retention.apply_outcome_to_metadata(
            schedule.review_metadata, outcome, at=now
        )
        schedule.review_metadata["step"] = next_step
        schedule.review_metadata["last_pressure"] = None

        concept_public_id = _concept_public_id(schedule, memory)
        current_mastery = _memory_mastery(memory, concept_public_id)

        # Close the loop: once a concept is mastered at the max interval it no
        # longer needs active review and leaves the queue.
        if (
            current_mastery is not None
            and current_mastery >= _THRESHOLD_MASTERED
            and next_step >= review_scheduler.MAX_STEP
        ):
            schedule.status = _STATUS_COMPLETED
            schedule.due_at = None
        else:
            schedule.due_at = now + timedelta(days=next_interval_days)
            schedule.status = _STATUS_SCHEDULED

        await self._repo.persist(schedule)

        # Reset the review clock in educational memory (no mastery rewrite).
        educational_memory_service.record_review_activity(
            user_str,
            concept_public_id or schedule.public_id,
            concept_name=_concept_name(schedule, memory) or "",
        )
        await educational_memory_service.save_to_db(session, user_str)

        # Retention signal after this completion (fresh review, not yet due).
        history = retention.history_outcomes(schedule.review_metadata)
        signal = retention.retention_signal(
            mastery=current_mastery,
            days_since_review=0.0,
            is_due=False,
            history=history,
        )

        return ReviewCompleteResponse(
            schedule_id=schedule.public_id,
            concept_id=concept_public_id or "",
            concept_name=_concept_name(schedule, memory) or "",
            status=schedule.status,
            next_due_at=_aware(schedule.due_at),
            next_interval_days=next_interval_days,
            mastery_score=current_mastery,
            outcome=outcome,
            retained_strength=signal["retained_strength"],
            review_accuracy=retention.review_accuracy(history),
        )

    async def skip(
        self,
        user_id: uuid.UUID,
        schedule_public_id: str,
        *,
        now: datetime | None = None,
    ) -> ReviewCompleteResponse:
        """Postpone a due review without counting a full completion.

        The interval stays the same; the due date is pushed back by the current
        interval so the learner is not nagged on this visit.
        """
        user_str = str(user_id)
        session = self._uow.session
        now = now or datetime.now(UTC)

        schedule = await self._repo.get_by_user_and_public_id(
            user_id, schedule_public_id
        )
        if schedule is None:
            raise NotFoundError(
                message="Review schedule not found",
                details={"schedule_id": schedule_public_id},
            )

        interval = int(schedule.interval_days) or 1
        schedule.due_at = now + timedelta(days=interval)
        schedule.status = _STATUS_SCHEDULED
        schedule.review_metadata = dict(schedule.review_metadata or {})
        schedule.review_metadata["skipped_at"] = now.isoformat()
        await self._repo.persist(schedule)

        memory = await educational_memory_service.load_from_db(session, user_str)
        concept_public_id = _concept_public_id(schedule, memory)
        return ReviewCompleteResponse(
            schedule_id=schedule.public_id,
            concept_id=concept_public_id or "",
            concept_name=_concept_name(schedule, memory) or "",
            status=schedule.status,
            next_due_at=_aware(schedule.due_at),
            next_interval_days=int(schedule.interval_days),
            mastery_score=_memory_mastery(memory, concept_public_id),
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _ensure_schedules(
        self,
        memory: EducationalMemory,
        user_id: uuid.UUID,
        user_str: str,
        now: datetime,
    ) -> None:
        """Seed review schedules for weak/developing concepts without one yet.

        Deterministic and lazy: creates at most one schedule per
        learner+concept (existing active schedules are respected). This turns
        latent mastery into a timed review plan without rewriting mastery.
        """
        active = await self._repo.list_due(user_id, limit=10000)
        active_concept_uuids = {
            s.concept_id for s in active if s.concept_id is not None
        }

        # Candidate memory records that still need a schedule (weak/developing).
        needed_public: dict[str, float] = {}
        for cid, record in memory.concept_records.items():
            if record.mastery_score is None or record.mastery_score >= _THRESHOLD_MASTERED:
                continue
            needed_public[cid] = float(record.mastery_score)
        if not needed_public:
            return

        # Resolve concept public_ids -> ORM concepts (single batched query).
        concepts = await self._concept_repo.list_by_public_ids(list(needed_public.keys()))
        by_public: dict[str, Concept] = {c.public_id: c for c in concepts}

        for cid, mastery in needed_public.items():
            concept = by_public.get(cid)
            if concept is None:
                continue
            if concept.id in active_concept_uuids:
                continue
            step = initial_step(mastery)
            interval = interval_at_step(step)
            await self._repo.persist(
                ReviewSchedule(
                    user_id=user_id,
                    concept_id=concept.id,
                    lesson_id=concept.lesson_id,
                    topic=concept.name or cid,
                    status=_STATUS_SCHEDULED,
                    scheduled_date=now.date(),
                    interval_days=interval,
                    mastery_at_schedule=float(mastery),
                    due_at=now + timedelta(days=interval),
                    review_metadata={"step": step},
                )
            )

    def _build_queue_item(
        self,
        schedule: ReviewSchedule,
        memory: EducationalMemory,
        now: datetime,
    ) -> ReviewQueueItem:
        concept_public_id = _concept_public_id(schedule, memory)
        mastery = _memory_mastery(memory, concept_public_id)
        record = _memory_record(memory, concept_public_id)

        pressure = compute_decay_signal(
            record,
            now=now,
            interval_override_days=int(schedule.interval_days) or 1,
        ) if record else {"days_since_review": 0.0, "pressure": 0.0}
        due_dt = _aware(schedule.due_at)
        is_due = due_dt is None or due_dt <= now
        priority = priority_bucket(float(pressure["pressure"]), due=is_due)

        history = retention.history_outcomes(schedule.review_metadata)
        signal = retention.retention_signal(
            mastery=mastery,
            days_since_review=_days_since_review(record, schedule, now),
            is_due=is_due,
            history=history,
        )

        return ReviewQueueItem(
            schedule_id=schedule.public_id,
            concept_id=concept_public_id or "",
            concept_name=_concept_name(schedule, memory) or "",
            lesson_id=_lesson_public_id(schedule),
            mastery_score=mastery,
            status=schedule.status,
            interval_days=int(schedule.interval_days),
            due_at=_aware(schedule.due_at),
            last_reviewed_at=_aware(schedule.last_reviewed_at),
            scheduled_date=schedule.scheduled_date,
            review_count=int(record.review_count) if record else 0,
            priority=priority,
            retention_status=signal["status"],
            review_accuracy=retention.review_accuracy(history),
        )


# ---------------------------------------------------------------------------
# Module helpers
# ---------------------------------------------------------------------------


def _priority_rank(priority: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(str(priority), 3)


def _concept_public_id(schedule: ReviewSchedule, memory: EducationalMemory) -> str | None:
    if schedule.concept is not None and schedule.concept.public_id:
        return schedule.concept.public_id
    # Fall back to matching memory record by shared topic.
    for cid, record in memory.concept_records.items():
        if record.concept_name and record.concept_name == schedule.topic:
            return str(cid)
    return None


def _concept_name(schedule: ReviewSchedule, memory: EducationalMemory) -> str | None:
    if schedule.concept is not None and schedule.concept.name:
        return schedule.concept.name
    cid = _concept_public_id(schedule, memory)
    if cid:
        rec = _memory_record(memory, cid)
        if rec:
            return rec.concept_name
    return schedule.topic


def _lesson_public_id(schedule: ReviewSchedule) -> str | None:
    if schedule.lesson is not None and schedule.lesson.public_id:
        return schedule.lesson.public_id
    return None


def _memory_record(
    memory: EducationalMemory, concept_public_id: str | None
) -> ConceptMasteryRecord | None:
    if not concept_public_id:
        return None
    return memory.concept_records.get(concept_public_id)


def _memory_mastery(memory: EducationalMemory, concept_public_id: str | None) -> float | None:
    rec = _memory_record(memory, concept_public_id)
    return float(rec.mastery_score) if rec and rec.mastery_score is not None else None


def _days_since_review(
    record: ConceptMasteryRecord | None,
    schedule: ReviewSchedule,
    now: datetime,
) -> float | None:
    """Days since the last review touchpoint, tolerant of missing/legacy rows.

    Prefers the educational-memory anchor (same precedence as
    ``compute_decay_signal``), then the schedule's own review clock. ``None``
    means the concept has never been reviewed.
    """
    anchor = None
    if record is not None and (record.last_reviewed_at or record.first_learned_at):
        anchor = float(record.last_reviewed_at or record.first_learned_at)
    elif schedule.last_reviewed_at is not None:
        aware = _aware(schedule.last_reviewed_at)
        if aware is not None:
            anchor = aware.timestamp()
    if anchor is None:
        return None
    return max(0.0, (now.timestamp() - anchor) / 86400.0)
