"""P11 plan / goal / path service integration tests.

Exercises the deterministic personalised-planning services against the seeded
test database: learning-path auto-creation and deterministic ordering, derived
goal progress (incl. the conflict/achieved complete path), and the Today plan
composition with item completion routing through the P10 review loop.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.database.unit_of_work import UnitOfWork
from app.models.concept import Concept
from app.models.educational_memory import EducationalMemoryRecord
from app.models.generated_lesson import GeneratedLesson
from app.models.learning_goal import LearningGoal
from app.models.learning_path import LearningPath
from app.models.learning_session import LearningSession
from app.models.presentation import Presentation
from app.models.review_schedule import ReviewSchedule
from app.models.study_plan import StudyPlan
from app.models.user import User
from app.services.educational_memory_service import educational_memory_service
from app.services.learning_goal_service import LearningGoalService
from app.services.learning_path_service import LearningPathService
from app.services.study_plan_service import StudyPlanService


@pytest.fixture(autouse=True)
def _reset_memory_cache() -> None:
    educational_memory_service._memories.clear()  # noqa: SLF001
    return


async def _seed_chain(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    concept_name: str,
    mastery: float,
    email: str,
    lesson_title: str = "P11 Lesson",
) -> tuple[str, str, uuid.UUID]:
    """User + presentation + lesson + concept + memory, all owned by user_id."""
    from app.core.security import hash_password

    concept_public_id = f"concept_{uuid.uuid4().hex[:10]}"
    lesson_public_id = f"lesson_{uuid.uuid4().hex[:10]}"

    existing = await session.execute(select(User).where(User.id == user_id))
    if existing.scalar_one_or_none() is None:
        session.add(
            User(
                id=user_id,
                email=email,
                name="P11 Learner",
                password_hash=hash_password("testpassword123"),
            )
        )

    pres = Presentation(title="P11 Deck", owner_id=user_id, status="published")
    session.add(pres)
    await session.flush()

    lesson = GeneratedLesson(
        public_id=lesson_public_id,
        presentation_id=pres.id,
        user_id=user_id,
        mode="slide",
        status="ready",
        title=lesson_title,
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
                    "developing_concepts": [concept_public_id] if mastery >= 50 else [],
                    "weak_concepts": [concept_public_id] if mastery < 50 else [],
                    "profile": {
                        "user_id": str(user_id),
                        "average_mastery": mastery,
                    },
                    "preferences": {},
                    "revision_queue": [],
                    "milestones": [],
                    "created_at": now - 3600,
                    "updated_at": now,
                },
            )
        )
    await session.commit()
    return concept_public_id, lesson_public_id, concept.id


async def _make_due_schedule(
    session: AsyncSession,
    user_id: uuid.UUID,
    concept_id: uuid.UUID,
    lesson_id: uuid.UUID,
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
        lesson_id=lesson_id,
        topic="Review Concept",
        status="scheduled",
        scheduled_date=now.date(),
        interval_days=1,
        mastery_at_schedule=30.0,
        due_at=now - timedelta(days=due_in_past_days),
        review_metadata={"step": 0},
    )
    await ReviewScheduleRepository(session).persist(schedule)
    await session.commit()
    return schedule


async def _complete_lesson(session: AsyncSession, user_id: uuid.UUID, lesson_id) -> None:
    session.add(
        LearningSession(
            user_id=user_id,
            lesson_id=lesson_id,
            status="completed",
            completion_percentage=100.0,
        )
    )
    await session.commit()


# ---------------------------------------------------------------------------
# Learning path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_path_auto_creates_and_orders_weak_first(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    await _seed_chain(
        db_session, uid, concept_name="Weak", mastery=25.0, email="path_a@example.com",
        lesson_title="Weak Lesson",
    )
    service = LearningPathService(UnitOfWork(session=db_session))
    view = await service.get_path(uid)
    assert view.id.startswith("path_")
    assert view.lesson_count == 1
    assert view.current_lesson is not None
    assert view.current_lesson.status == "not_started"
    assert view.progress_percent == 0.0

    # Persisted sequence holds the lesson public id.
    row = (await db_session.execute(select(LearningPath))).scalars().first()
    assert list(row.sequence) == [view.sequence[0].lesson_id]


@pytest.mark.asyncio
async def test_path_orders_in_progress_then_not_started(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    _, first_lesson, _ = await _seed_chain(
        db_session, uid, concept_name="Alpha", mastery=90.0, email="path_b@example.com",
        lesson_title="Completed Lesson",
    )
    await _complete_lesson(db_session, uid, (await db_session.execute(
        select(GeneratedLesson).where(GeneratedLesson.public_id == first_lesson)
    )).scalar_one().id)

    # A second lesson with no session yet.
    _, second_lesson, _ = await _seed_chain(
        db_session, uid, concept_name="Beta", mastery=90.0, email="path_b2@example.com",
        lesson_title="Fresh Lesson",
    )
    service = LearningPathService(UnitOfWork(session=db_session))
    view = await service.get_path(uid)
    titles = [s.title for s in view.sequence]
    assert titles[0] == "Fresh Lesson"
    assert titles[1] == "Completed Lesson"
    assert view.progress_percent == 50.0
    assert view.current_lesson.lesson_id == second_lesson


@pytest.mark.asyncio
async def test_create_path_archives_prior_active(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    await _seed_chain(
        db_session, uid, concept_name="Weak", mastery=25.0, email="path_c@example.com",
    )
    service = LearningPathService(UnitOfWork(session=db_session))
    first = await service.get_path(uid)

    second = await service.create_path(uid, title="Focused Path")
    assert first.id != second.id

    row = (await db_session.execute(
        select(LearningPath).where(LearningPath.public_id == first.id)
    )).scalar_one()
    assert row.status == "archived"
    assert second.status == "active"


# ---------------------------------------------------------------------------
# Goals
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_goal_lesson_completion_derives_and_achieves(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    _, lesson_public, _ = await _seed_chain(
        db_session, uid, concept_name="Quiz", mastery=20.0, email="goal_a@example.com",
    )
    service = LearningGoalService(UnitOfWork(session=db_session))

    created = await service.create_goal(
        uid,
        goal_type="lesson_completion",
        title="Finish a lesson",
        target_value=1.0,
    )
    assert created.current_value == 0.0
    assert created.progress_percent == 0.0

    with pytest.raises(ConflictError):
        await service.complete_goal(uid, created.id)

    lesson_uuid = (await db_session.execute(
        select(GeneratedLesson).where(GeneratedLesson.public_id == lesson_public)
    )).scalar_one().id
    await _complete_lesson(db_session, uid, lesson_uuid)
    achieved = await service.complete_goal(uid, created.id)
    assert achieved.status == "achieved"
    assert achieved.current_value == 1.0
    assert achieved.progress_percent == 100.0

    # Idempotent once achieved.
    again = await service.complete_goal(uid, created.id)
    assert again.status == "achieved"


@pytest.mark.asyncio
async def test_goal_rejects_unsupported_type_and_unknown(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    await _seed_chain(db_session, uid, concept_name="W", mastery=20.0, email="goal_b@example.com")
    service = LearningGoalService(UnitOfWork(session=db_session))

    from app.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        await service.create_goal(uid, goal_type="study_time", title="Bad")
    with pytest.raises(NotFoundError):
        await service.complete_goal(uid, "goal_nope")


@pytest.mark.asyncio
async def test_goal_mastery_target_uses_average(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    await _seed_chain(
        db_session, uid, concept_name="Mastered", mastery=99.0, email="goal_c@example.com",
    )
    service = LearningGoalService(UnitOfWork(session=db_session))
    view = await service.create_goal(
        uid, goal_type="mastery_target", title="Mastery 100", target_value=100.0,
    )
    assert view.goal_type == "mastery_target"
    assert view.current_value == 99.0
    assert round(view.progress_percent, 1) == 99.0


@pytest.mark.asyncio
async def test_goal_streak_uses_profile(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    await _seed_chain(
        db_session, uid, concept_name="Streak", mastery=20.0, email="goal_d@example.com",
    )
    service = LearningGoalService(UnitOfWork(session=db_session))
    view = await service.create_goal(
        uid, goal_type="streak_days", title="7 day streak", target_value=7.0,
    )
    assert view.unit == "days"
    assert isinstance(view.current_value, float)
    assert view.current_value >= 1.0


# ---------------------------------------------------------------------------
# Today plan
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_today_plan_empty_for_fresh_learner(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    await _seed_chain(
        db_session, uid, concept_name="Fresh", mastery=90.0, email="plan_a@example.com",
    )
    service = StudyPlanService(UnitOfWork(session=db_session))
    plan = await service.get_today(uid)
    assert plan.date == datetime.now(UTC).date()
    assert isinstance(plan.items, list)
    row = (await db_session.execute(select(StudyPlan))).scalars().first()
    assert row.user_id == uid
    assert row.total_items == len(plan.items)


@pytest.mark.asyncio
async def test_today_plan_has_due_review_and_lesson_item(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    concept_public, lesson_public, concept_uuid = await _seed_chain(
        db_session, uid, concept_name="Due", mastery=30.0, email="plan_b@example.com",
    )
    lesson_uuid = (await db_session.execute(
        select(GeneratedLesson).where(GeneratedLesson.public_id == lesson_public)
    )).scalar_one().id
    due = await _make_due_schedule(db_session, uid, concept_uuid, lesson_uuid)

    service = StudyPlanService(UnitOfWork(session=db_session))
    plan = await service.get_today(uid)
    keys = [it.item_key for it in plan.items]
    assert f"review.{due.public_id}" in keys
    review = next(it for it in plan.items if it.item_key.startswith("review."))
    assert review.deep_link == f"/frontend/player.html?lesson={lesson_public}"
    assert any(it.item_key == f"lesson.{lesson_public}" for it in plan.items)


@pytest.mark.asyncio
async def test_today_plan_completes_lesson_item_idempotently(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    _, lesson_public, _ = await _seed_chain(
        db_session, uid, concept_name="Item", mastery=30.0, email="plan_c@example.com",
    )
    service = StudyPlanService(UnitOfWork(session=db_session))
    plan = await service.get_today(uid)
    lesson_item = next(it for it in plan.items if it.item_type == "lesson")

    result = await service.complete_item(uid, lesson_item.item_key)
    assert result.routed_review is False
    assert result.status == "completed"

    again = await service.complete_item(uid, lesson_item.item_key)
    assert again.status == "completed"
    assert again.message == "Already completed"


@pytest.mark.asyncio
async def test_today_plan_review_item_routes_through_p10(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    _, _, concept_uuid = await _seed_chain(
        db_session, uid, concept_name="Due", mastery=30.0, email="plan_d@example.com",
    )
    lesson_uuid = (await db_session.execute(select(GeneratedLesson).where(
        GeneratedLesson.user_id == uid
    ))).scalars().first().id
    due = await _make_due_schedule(db_session, uid, concept_uuid, lesson_uuid)

    service = StudyPlanService(UnitOfWork(session=db_session))
    plan = await service.get_today(uid)
    review_item = next(it for it in plan.items if it.item_type == "review")

    result = await service.complete_item(uid, review_item.item_key)
    assert result.routed_review is True
    assert result.next_due_at is not None
    assert result.next_due_at > datetime.now(UTC)

    row = (await db_session.execute(select(ReviewSchedule).where(
        ReviewSchedule.public_id == due.public_id
    ))).scalar_one()
    assert row.completed_at is not None
    assert row.interval_days == 3


@pytest.mark.asyncio
async def test_today_plan_complete_unknown_item_is_404(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    await _seed_chain(
        db_session, uid, concept_name="Item", mastery=30.0, email="plan_e@example.com",
    )
    service = StudyPlanService(UnitOfWork(session=db_session))
    await service.get_today(uid)
    with pytest.raises(NotFoundError):
        await service.complete_item(uid, "lesson.unknown_id")
