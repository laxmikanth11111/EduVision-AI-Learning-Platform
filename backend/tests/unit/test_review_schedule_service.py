"""P10 review-schedule service + API integration tests.

Exercises the learner-scoped adaptive review engine against the seeded test
database: lazy schedule seeding from educational memory, the due-only review
queue, interval advancement on completion, skip, and cross-user isolation
(ownership 404-equalized).
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.database.unit_of_work import UnitOfWork
from app.models.educational_memory import EducationalMemoryRecord
from app.models.generated_lesson import GeneratedLesson
from app.models.presentation import Presentation
from app.models.review_schedule import ReviewSchedule
from app.models.user import User
from app.services.educational_memory_service import educational_memory_service
from app.services.review_schedule_service import ReviewScheduleService
from tests.learner_progress_helpers import seed_user


@pytest.fixture(autouse=True)
def _reset_memory_cache() -> None:
    educational_memory_service._memories.clear()  # noqa: SLF001
    return


async def _seed_owner_chain(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    concept_name: str,
    mastery: float,
    email: str,
) -> tuple[str, str, uuid.UUID]:
    """Create user + presentation + lesson + concept owned by user_id.

    Returns ``(concept_public_id, lesson_public_id, concept_row_id)``. The
    concept public id is unique per call so multiple tests can share the
    session-scoped database without violating the unique constraint.
    """
    from app.core.security import hash_password
    from app.models.concept import Concept

    concept_public_id = f"concept_{uuid.uuid4().hex[:10]}"

    existing = await session.execute(select(User).where(User.id == user_id))
    if existing.scalar_one_or_none() is None:
        session.add(
            User(
                id=user_id,
                email=email,
                name="Review Learner",
                password_hash=hash_password("testpassword123"),
            )
        )

    pres = Presentation(title="Review Deck", owner_id=user_id, status="published")
    session.add(pres)
    await session.flush()

    lesson = GeneratedLesson(
        presentation_id=pres.id,
        user_id=user_id,
        mode="slide",
        status="ready",
        title="Review Lesson",
        latest_version=1,
    )
    session.add(lesson)
    await session.flush()

    concept = Concept(
        public_id=concept_public_id,
        presentation_id=pres.id,
        lesson_id=lesson.id,
        name=concept_name,
        difficulty_level="intermediate",
    )
    session.add(concept)
    await session.flush()

    now = time.time()
    existing_mem = await session.execute(
        select(EducationalMemoryRecord).where(EducationalMemoryRecord.user_id == user_id)
    )
    if existing_mem.scalar_one_or_none() is None:
        session.add(
            EducationalMemoryRecord(
                user_id=user_id,
                memory_data={
                    "user_id": str(user_id),
                    "concept_records": {
                        concept_public_id: {
                            "concept_id": concept_public_id,
                            "concept_name": concept_name,
                            "first_learned_at": now - 3600,
                            "last_reviewed_at": now,
                            "mastery_score": mastery,
                            "review_count": 1,
                            "trend": "stable",
                            "confidence_score": 0.5,
                        },
                    },
                    "mastered_concepts": [],
                    "developing_concepts": [],
                    "weak_concepts": [concept_public_id] if mastery < 50.0 else [],
                    "profile": {"user_id": str(user_id)},
                    "preferences": {},
                    "revision_queue": [],
                    "milestones": [],
                    "created_at": now - 3600,
                    "updated_at": now,
                },
            )
        )
    await session.commit()
    return concept_public_id, lesson.public_id, concept.id


async def _make_due_schedule(
    session: AsyncSession,
    user_id: uuid.UUID,
    concept_id: uuid.UUID,
    *,
    due_in_past_days: float = 1.0,
) -> ReviewSchedule:
    from app.repositories.review_schedule_repository import (
        ReviewScheduleRepository,
    )

    now = datetime.now(UTC)
    schedule = ReviewSchedule(
        user_id=user_id,
        concept_id=concept_id,
        topic="Review Concept",
        status="scheduled",
        scheduled_date=now.date(),
        interval_days=1,
        mastery_at_schedule=30.0,
        due_at=now - timedelta(days=due_in_past_days),
        review_metadata={"step": 0},
    )
    repo = ReviewScheduleRepository(session)
    await repo.persist(schedule)
    await session.commit()
    return schedule


@pytest.mark.asyncio
async def test_list_due_seeds_weak_schedule(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    await _seed_owner_chain(
        db_session, uid, concept_name="Weak Concept", mastery=20.0, email="review_a@example.com",
    )
    service = ReviewScheduleService(UnitOfWork(session=db_session))
    queue = await service.list_due(uid)
    # A schedule is seeded (total active), but it is not yet due, so no items.
    assert queue.total >= 1
    assert queue.due_count == 0
    assert queue.items == []


@pytest.mark.asyncio
async def test_list_due_does_not_seed_mastered(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    await _seed_owner_chain(
        db_session, uid, concept_name="Mastered Concept", mastery=95.0, email="review_b@example.com",
    )
    service = ReviewScheduleService(UnitOfWork(session=db_session))
    queue = await service.list_due(uid)
    assert queue.total == 0
    assert queue.items == []


@pytest.mark.asyncio
async def test_due_item_returns_and_complete_advances(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    concept_public_id, _, concept_id = await _seed_owner_chain(
        db_session, uid, concept_name="Weak Concept", mastery=20.0, email="review_c@example.com",
    )
    concept_row = (
        await db_session.execute(
            select(ReviewSchedule)
            .where(ReviewSchedule.user_id == uid, ReviewSchedule.status == "scheduled")
            .order_by(ReviewSchedule.created_at.desc())
        )
    ).scalars().first()
    # Remove the lazily-created (future-due) schedule and seed a due one.
    if concept_row is not None:
        await db_session.delete(concept_row)
        await db_session.commit()
    await _make_due_schedule(db_session, uid, concept_id, due_in_past_days=1.0)

    service = ReviewScheduleService(UnitOfWork(session=db_session))
    queue = await service.list_due(uid)
    assert queue.due_count == 1
    assert len(queue.items) == 1
    item = queue.items[0]
    assert item.concept_id == concept_public_id
    assert item.priority == "high"

    # Complete -> interval advances (1d -> 3d) and due_at moves to the future.
    result = await service.complete(uid, item.schedule_id)
    assert result.next_interval_days == 3
    assert result.next_due_at is not None
    assert result.next_due_at > datetime.now(UTC)

    # Now it is no longer due.
    queue2 = await service.list_due(uid)
    assert queue2.due_count == 0
    assert queue2.items == []


@pytest.mark.asyncio
async def test_skip_postpones_without_advancing(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    _, _, concept_id = await _seed_owner_chain(
        db_session, uid, concept_name="Weak Concept", mastery=20.0, email="review_d@example.com",
    )
    schedule_row = await _make_due_schedule(db_session, uid, concept_id)
    before_interval = schedule_row.interval_days

    service = ReviewScheduleService(UnitOfWork(session=db_session))
    result = await service.skip(uid, schedule_row.public_id)
    assert result.next_interval_days == before_interval
    assert result.next_due_at is not None
    assert result.next_due_at > datetime.now(UTC)


@pytest.mark.asyncio
async def test_cross_user_complete_is_404(db_session: AsyncSession) -> None:
    owner = uuid.uuid4()
    other = uuid.uuid4()
    _, _, concept_id = await _seed_owner_chain(
        db_session, owner, concept_name="Weak Concept", mastery=20.0, email="review_e@example.com",
    )
    schedule_row = await _make_due_schedule(db_session, owner, concept_id)
    await seed_user(db_session, other, email="review_other@example.com")

    service = ReviewScheduleService(UnitOfWork(session=db_session))
    with pytest.raises(NotFoundError):
        await service.complete(other, schedule_row.public_id)
