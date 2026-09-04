"""Deterministic dated study-plan service (P11).

Builds the learner's "Today" plan as a read-composition over live mastery and
review state — no AI, no ML, no second scheduler. The plan reuses the
authoritative sources:

  - ``ReviewScheduleService.list_due`` for due/overdue reviews (the single
    authoritative spaced-repetition queue, including its lazy seeding).
  - educational memory for practice candidates (weak/developing concepts that
    are not already covered by a due review today).
  - ``LearningPathService.get_path`` for the current lesson to continue.

Composition order (fixed and documented): overdue reviews, reviews due today,
weak-concept practice, current lesson, developing-concept practice. Each item
is deep-linkable to an existing validated destination (lesson player or AI
tutor), mirroring the P10 actionability contract.

Plan items are persisted per day in the ``days`` JSONB of a single-day
``study_plans`` row (``start_date == end_date == that day``). Items are
recomposed fresh on every read so the plan never drifts from learner truth;
user "Mark done" actions on practice/lesson items are honoured as sticky
completion marks. Completing a ``review`` item routes through the real P10
completion loop.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time
from typing import Any

from sqlalchemy import select

from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.database.unit_of_work import UnitOfWork
from app.models.concept import Concept
from app.models.generated_lesson import GeneratedLesson
from app.models.study_plan import StudyPlan
from app.observability.metrics import metrics
from app.repositories.study_plan_repository import StudyPlanRepository
from app.schemas.plan import (
    PlanItem,
    PlanItemCompleteResponse,
    TodayPlanResponse,
)
from app.services.educational_memory_service import educational_memory_service
from app.services.learning_path_service import LearningPathService
from app.services.review_schedule_service import ReviewScheduleService

logger = get_logger(__name__)

_ITEM_REVIEW = "review"
_ITEM_PRACTICE = "practice"
_ITEM_LESSON = "lesson"

_STATUS_PENDING = "pending"
_STATUS_COMPLETED = "completed"

_MAX_REVIEWS = 100
_MAX_PRACTICE = 5

# Mastery thresholds mirroring educational_memory_service (do NOT redefine).
_THRESHOLD_WEAK = 50.0
_THRESHOLD_DEVELOPING = 85.0


class StudyPlanService:
    """Compose and complete the learner's deterministic Today plan."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        self._plan_repo = StudyPlanRepository(uow.session)
        self._review_service = ReviewScheduleService(uow)
        self._path_service = LearningPathService(uow)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_today(
        self, user_id: uuid.UUID, *, on_date: date | None = None
    ) -> TodayPlanResponse:
        session = self._uow.session
        user_str = str(user_id)
        day = on_date or datetime.now(UTC).date()

        memory = await educational_memory_service.load_from_db(session, user_str)
        items = await self._compose_day_items(user_id, session, memory, day)

        stored = await self._plan_repo.find_active_for_date(user_id, day)
        done = self._completed_keys(stored, day)
        for item in items:
            if item.item_key in done:
                item.status = _STATUS_COMPLETED

        total = len(items)
        completed = sum(1 for it in items if it.status == _STATUS_COMPLETED)
        now = datetime.now(UTC)

        if stored is None:
            stored = StudyPlan(
                user_id=user_id,
                status="active",
                start_date=day,
                end_date=day,
                timezone="UTC",
                generated_at=now,
            )
        stored.title = f"Today's Plan · {day.isoformat()}"
        stored.days = {
            day.isoformat(): [_plan_item_dict(it) for it in items]
        }
        stored.days_count = 1
        stored.total_items = total
        stored.completed_items = completed
        stored.generated_at = stored.generated_at or now
        await self._plan_repo.persist(stored)

        metrics.increment("p11_plan_reads_total", outcome="ok", items=str(total))
        return TodayPlanResponse(
            plan_id=stored.public_id,
            date=day,
            items=items,
            completed_items=completed,
            total_items=total,
            summary=self._summarize(items),
        )

    async def complete_item(
        self,
        user_id: uuid.UUID,
        item_key: str,
        *,
        on_date: date | None = None,
    ) -> PlanItemCompleteResponse:
        """Complete a plan item, routing review items through the P10 loop.

        Idempotent: completing an already-completed practice/lesson item is a
        no-op success; completing a review item replays the (already safe)
        review completion.
        """
        day = on_date or datetime.now(UTC).date()
        self._validate_item_key(item_key)

        stored = await self._plan_repo.find_active_for_date(user_id, day)
        if stored is None:
            raise NotFoundError(
                message="No plan found for this day",
                details={"date": day.isoformat()},
            )

        kind = self._item_kind(item_key)
        if kind == _ITEM_REVIEW:
            schedule_id = item_key[len(f"{_ITEM_REVIEW}."):]
            result = await self._review_service.complete(user_id, schedule_id)
            self._mark_done(stored, day, item_key, {
                "status": _STATUS_COMPLETED,
                "completed_at": datetime.now(UTC).isoformat(),
            })
            metrics.increment("p11_plan_items_completed_total", item_type=kind)
            next_price = result.next_interval_days
            message = (
                f"Review recorded — next review in {next_price} day"
                + ("s" if next_price != 1 else "")
            )
            return PlanItemCompleteResponse(
                plan_id=stored.public_id,
                item_key=item_key,
                status=_STATUS_COMPLETED,
                routed_review=True,
                next_due_at=result.next_due_at,
                next_interval_days=result.next_interval_days,
                message=message,
            )

        # lesson / practice: sticky completion mark on the stored day.
        entry = self._day_item(stored, day, item_key)
        if entry is None:
            raise NotFoundError(
                message="Plan item not found",
                details={"item_key": item_key, "date": day.isoformat()},
            )
        if entry.get("status") == _STATUS_COMPLETED:
            metrics.increment("p11_plan_items_completed_total", item_type=kind, idempotent="true")
            return PlanItemCompleteResponse(
                plan_id=stored.public_id,
                item_key=item_key,
                status=_STATUS_COMPLETED,
                routed_review=False,
                message="Already completed",
            )
        self._mark_done(stored, day, item_key, {
            "status": _STATUS_COMPLETED,
            "completed_at": datetime.now(UTC).isoformat(),
        })
        metrics.increment("p11_plan_items_completed_total", item_type=kind)
        return PlanItemCompleteResponse(
            plan_id=stored.public_id,
            item_key=item_key,
            status=_STATUS_COMPLETED,
            routed_review=False,
            message="Marked complete",
        )

    # ------------------------------------------------------------------
    # Composition
    # ------------------------------------------------------------------

    async def _compose_day_items(
        self,
        user_id: uuid.UUID,
        session: Any,
        memory: Any,
        day: date,
    ) -> list[PlanItem]:
        today_start = datetime.combine(day, time.min, tzinfo=UTC)

        # 1. Authoritative due reviews (includes lazy schedule seeding).
        queue = await self._review_service.list_due(user_id, limit=_MAX_REVIEWS)
        covered_concepts = {it.concept_id for it in queue.items if it.concept_id}
        reviews: list[PlanItem] = []
        for it in queue.items:
            due_dt = it.due_at
            overdue = due_dt is not None and due_dt < today_start
            reviews.append(
                PlanItem(
                    item_key=f"{_ITEM_REVIEW}.{it.schedule_id}",
                    item_type=_ITEM_REVIEW,
                    title=f"Review: {it.concept_name or it.concept_id or 'concept'}",
                    reason="Overdue — solidify it now"
                    if overdue
                    else "Due today — spaced repetition keeps it sharp",
                    priority=str(it.priority or "medium"),
                    deep_link=self._review_deep_link(it.lesson_id, it.concept_id),
                    schedule_id=it.schedule_id,
                    concept_id=it.concept_id,
                    concept_name=it.concept_name,
                    lesson_id=it.lesson_id,
                    due_at=it.due_at,
                )
            )

        # 2/4. Practice candidates from memory (weak first, then developing).
        concept_links = await self._concept_lesson_map(session, list(memory.concept_records.keys()))
        weak_practice, developing_practice = self._practice_items(
            memory, covered_concepts, concept_links
        )

        # 3. Current lesson to continue (single authoritative path read).
        lesson_item: list[PlanItem] = []
        try:
            path_view = await self._path_service.get_path(user_id)
        except Exception as exc:  # path composition must never break the plan
            logger.warning("plan_path_compose_failed", user_id=str(user_id), error=str(exc))
            path_view = None
        if path_view is not None and path_view.current_lesson is not None:
            current = path_view.current_lesson
            lesson_item = [
                PlanItem(
                    item_key=f"{_ITEM_LESSON}.{current.lesson_id}",
                    item_type=_ITEM_LESSON,
                    title=f"Continue: {current.title}",
                    reason=(
                        f"{current.completion_percentage:.0f}% complete — pick up where you left off"
                        if current.completion_percentage > 0
                        else "Next lesson in your learning path"
                    ),
                    priority="high",
                    deep_link=current.deep_link,
                    lesson_id=current.lesson_id,
                )
            ]

        items = [*reviews, *weak_practice, *lesson_item, *developing_practice]
        return items[:_MAX_REVIEWS + _MAX_PRACTICE + _MAX_PRACTICE + 1]

    def _practice_items(
        self,
        memory: Any,
        covered_concepts: set[str],
        concept_links: dict[str, str | None],
    ) -> tuple[list[PlanItem], list[PlanItem]]:
        """Weak/developing concepts not already in today's due review queue."""
        weak: list[PlanItem] = []
        developing: list[PlanItem] = []
        for cid in list(memory.concept_records.keys()):
            if cid in covered_concepts:
                continue
            record = memory.concept_records[cid]
            mastery = float(record.mastery_score)
            if mastery >= _THRESHOLD_DEVELOPING:
                continue
            lesson_id = concept_links.get(cid)
            lesson_public = lesson_id if lesson_id else None
            name = record.concept_name or cid
            item = PlanItem(
                item_key=f"{_ITEM_PRACTICE}.{cid}",
                item_type=_ITEM_PRACTICE,
                title=f"Practice: {name}",
                reason="Weak concept — practise to build strength"
                if mastery < _THRESHOLD_WEAK
                else "Developing — keep it sharp",
                priority="high" if mastery < _THRESHOLD_WEAK else "medium",
                deep_link=(
                    f"/frontend/player.html?lesson={lesson_public}"
                    if lesson_public
                    else f"/frontend/tutor.html?concept={cid}"
                ),
                concept_id=cid,
                concept_name=name,
                lesson_id=lesson_public,
            )
            (weak if mastery < _THRESHOLD_WEAK else developing).append(item)

        weak.sort(key=lambda it: _mastery_rank(memory, it.concept_id))
        developing.sort(key=lambda it: _mastery_rank(memory, it.concept_id))
        return weak[:_MAX_PRACTICE], developing[:_MAX_PRACTICE]

    async def _concept_lesson_map(
        self, session: Any, concept_public_ids: list[str]
    ) -> dict[str, str | None]:
        """Map concept public id -> lesson public id (single batched join)."""
        result: dict[str, str | None] = {}
        if not concept_public_ids:
            return result
        rows = (
            await session.execute(
                select(Concept.public_id, GeneratedLesson.public_id)
                .join(GeneratedLesson, Concept.lesson_id == GeneratedLesson.id)
                .where(Concept.public_id.in_(concept_public_ids))
            )
        ).all()
        for cid, lesson_public_id in rows:
            result[cid] = lesson_public_id
        for cid in concept_public_ids:
            result.setdefault(cid, None)
        return result

    # ------------------------------------------------------------------
    # Stored-plan helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _item_kind(item_key: str) -> str:
        return str(item_key).split(".", 1)[0]

    @staticmethod
    def _validate_item_key(item_key: str) -> None:
        kind = StudyPlanService._item_kind(item_key)
        if kind not in {_ITEM_REVIEW, _ITEM_PRACTICE, _ITEM_LESSON}:
            raise NotFoundError(
                message="Unsupported plan item type",
                details={"item_key": item_key},
            )

    def _completed_keys(
        self, stored: StudyPlan | None, day: date
    ) -> set[str]:
        if stored is None or not stored.days:
            return set()
        entry = stored.days.get(day.isoformat())
        if not isinstance(entry, list):
            return set()
        return {
            str(item.get("item_key"))
            for item in entry
            if isinstance(item, dict) and item.get("status") == _STATUS_COMPLETED
        }

    def _day_item(
        self, stored: StudyPlan, day: date, item_key: str
    ) -> dict[str, Any] | None:
        entry = stored.days.get(day.isoformat()) if stored.days else None
        if not isinstance(entry, list):
            return None
        for item in entry:
            if isinstance(item, dict) and item.get("item_key") == item_key:
                return item
        return None

    def _mark_done(
        self,
        stored: StudyPlan,
        day: date,
        item_key: str,
        update: dict[str, Any],
    ) -> None:
        stored.days = dict(stored.days or {})
        entry = list(stored.days.get(day.isoformat(), []))
        replaced = False
        for i, item in enumerate(entry):
            if isinstance(item, dict) and item.get("item_key") == item_key:
                entry[i] = {**item, **update}
                replaced = True
                break
        if not replaced:
            entry.append({"item_key": item_key, **update})
        stored.days[day.isoformat()] = entry
        stored.completed_items = sum(
            1 for item in entry if item.get("status") == _STATUS_COMPLETED
        )
        stored.total_items = max(stored.total_items, len(entry))

    @staticmethod
    def _summarize(items: list[PlanItem]) -> str:
        counts: dict[str, int] = {}
        for it in items:
            if it.status == _STATUS_PENDING:
                counts[it.item_type] = counts.get(it.item_type, 0) + 1
        parts = [
            f"{v} {'reviews' if k == 'review' else 'concepts to practice' if k == 'practice' else 'lessons'} due"
            for k, v in counts.items()
        ]
        return " · ".join(parts) if parts else "All caught up — nothing pending today"

    @staticmethod
    def _review_deep_link(lesson_id: str | None, concept_id: str | None) -> str:
        if lesson_id:
            return f"/frontend/player.html?lesson={lesson_id}"
        if concept_id:
            return f"/frontend/tutor.html?concept={concept_id}"
        return ""


def _mastery_rank(memory: Any, concept_id: str | None) -> int:
    if not concept_id:
        return 999
    record = memory.concept_records.get(concept_id)
    if record is None or record.mastery_score is None:
        return 999
    # Low mastery first within the same bucket.
    return int(float(record.mastery_score) * 100)


def _plan_item_dict(item: PlanItem) -> dict[str, Any]:
    """Serialise a PlanItem for JSONB storage (datetimes -> ISO strings)."""
    data = item.model_dump()
    if data.get("due_at") is not None:
        data["due_at"] = data["due_at"].isoformat()
    return data
