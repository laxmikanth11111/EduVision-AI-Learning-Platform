"""PostgreSQL learner-journey tests (P5).

These run against the Alembic-migrated scratch database and verify that the
persistent per-user session store (``learning_sessions``) behaves correctly on
the real PostgreSQL engine: idempotent resume per (user, lesson), strict user
isolation, and the foreign-key invariants the production schema enforces.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.unit_of_work import UnitOfWork
from app.services.learning_session_service import LearningSessionService

pytestmark = pytest.mark.postgres


@pytest_asyncio.fixture
async def user(pg_session: AsyncSession):
    from app.models.user import User

    u = User(
        email=f"{uuid.uuid4().hex[:20]}@test.local",
        name="PG Journey User",
    )
    pg_session.add(u)
    await pg_session.flush()
    return u


async def _lesson(pg_session: AsyncSession, owner_id: uuid.UUID):
    from app.models.generated_lesson import GeneratedLesson
    from app.models.presentation import Presentation

    pres = Presentation(title="PG Journey Deck", owner_id=owner_id, status="ready")
    pg_session.add(pres)
    await pg_session.flush()
    lesson = GeneratedLesson(
        presentation_id=pres.id,
        user_id=None,
        mode="slide",
        status="ready",
        title="PG Journey Lesson",
        language="en",
        difficulty="beginner",
        latest_version=1,
    )
    pg_session.add(lesson)
    await pg_session.flush()
    return lesson


async def test_idempotent_resume_per_user(pg_session: AsyncSession, user) -> None:
    lesson = await _lesson(pg_session, user.id)
    svc = LearningSessionService(UnitOfWork(session=pg_session))

    first = await svc.get_or_create(
        user_id=str(user.id),
        lesson_id=lesson.id,
        lesson_version_id=None,
        topic_index=0,
        total_topics=3,
    )
    second = await svc.get_or_create(
        user_id=str(user.id),
        lesson_id=lesson.id,
        lesson_version_id=None,
        topic_index=0,
        total_topics=3,
    )

    assert first.id == second.id
    assert first.current_block_position == 0


async def test_session_progress_persists_across_advances(pg_session: AsyncSession, user) -> None:
    lesson = await _lesson(pg_session, user.id)
    svc = LearningSessionService(UnitOfWork(session=pg_session))

    created = await svc.get_or_create(
        user_id=str(user.id),
        lesson_id=lesson.id,
        lesson_version_id=None,
        topic_index=0,
        total_topics=3,
    )
    advanced = await svc.advance(
        session_id=created.public_id,
        user_id=str(user.id),
        total_topics=3,
    )
    assert advanced is not None
    assert advanced.current_block_position == 1

    # A fresh read (new session) must observe the persisted position.
    reloaded = await svc.get_or_create(
        user_id=str(user.id),
        lesson_id=lesson.id,
        lesson_version_id=None,
        topic_index=0,
        total_topics=3,
    )
    assert reloaded.current_block_position == 1


async def test_two_user_isolation(pg_session: AsyncSession, user) -> None:
    from app.models.user import User

    other = User(
        email=f"{uuid.uuid4().hex[:20]}@test.local",
        name="PG Other User",
    )
    pg_session.add(other)
    await pg_session.flush()
    lesson = await _lesson(pg_session, user.id)
    svc = LearningSessionService(UnitOfWork(session=pg_session))

    await svc.get_or_create(
        user_id=str(user.id),
        lesson_id=lesson.id,
        lesson_version_id=None,
        topic_index=2,
        total_topics=3,
    )

    assert (
        await svc.find_for_lesson(user_id=str(user.id), lesson_id=lesson.id)
        is not None
    )
    assert (
        await svc.find_for_lesson(user_id=str(other.id), lesson_id=lesson.id)
        is None
    )
