from __future__ import annotations

from typing import Any

import pytest

from app.database.unit_of_work import UnitOfWork
from app.models.generated_lesson import GeneratedLesson
from app.services.learning_session_service import LearningSessionService
from shared.constants import LearningSessionStatus

pytestmark = pytest.mark.asyncio


async def _make_lesson(db_session, presentation) -> GeneratedLesson:
    lesson = GeneratedLesson(
        presentation_id=presentation.id,
        user_id=None,
        mode="slide",
        status="ready",
        title="Service Lesson",
        language="en",
        difficulty="beginner",
        latest_version=1,
    )
    db_session.add(lesson)
    await db_session.flush()
    return lesson


def _service(db_session) -> LearningSessionService:
    return LearningSessionService(UnitOfWork(session=db_session))


class TestFindForLesson:
    async def test_returns_none_when_no_session(
        self, db_session, make_user, make_presentation
    ) -> None:
        user = await make_user()
        lesson = await _make_lesson(db_session, await make_presentation())
        result = await _service(db_session).find_for_lesson(
            user_id=str(user.id), lesson_id=lesson.id
        )
        assert result is None

    async def test_scoped_to_user(self, db_session, make_user, make_presentation) -> None:
        owner_a = await make_user()
        owner_b = await make_user()
        lesson = await _make_lesson(db_session, await make_presentation())
        svc = _service(db_session)

        created = await svc.get_or_create(
            user_id=str(owner_a.id),
            lesson_id=lesson.id,
            lesson_version_id=None,
            topic_index=0,
            total_topics=3,
        )

        assert await svc.find_for_lesson(user_id=str(owner_a.id), lesson_id=lesson.id) == created
        assert await svc.find_for_lesson(user_id=str(owner_b.id), lesson_id=lesson.id) is None


class TestGetOrCreate:
    async def test_creates_then_resumes_same_row(
        self, db_session, make_user, make_presentation
    ) -> None:
        user = await make_user()
        lesson = await _make_lesson(db_session, await make_presentation())
        svc = _service(db_session)

        first = await svc.get_or_create(
            user_id=str(user.id),
            lesson_id=lesson.id,
            lesson_version_id=None,
            topic_index=0,
            total_topics=4,
        )
        second = await svc.get_or_create(
            user_id=str(user.id),
            lesson_id=lesson.id,
            lesson_version_id=None,
            topic_index=0,
            total_topics=4,
        )

        assert first.id == second.id
        assert first.current_block_position == 0

    async def test_stores_initial_progress(self, db_session, make_user, make_presentation) -> None:
        user = await make_user()
        lesson = await _make_lesson(db_session, await make_presentation())
        session = await _service(db_session).get_or_create(
            user_id=str(user.id),
            lesson_id=lesson.id,
            lesson_version_id=None,
            topic_index=1,
            total_topics=3,
        )
        assert session.current_block_position == 1
        assert session.completion_percentage == round((2 / 3) * 100.0, 1)


class TestAdvanceSetTopic:
    async def test_advance_caps_at_last_topic(
        self, db_session, make_user, make_presentation
    ) -> None:
        user = await make_user()
        lesson = await _make_lesson(db_session, await make_presentation())
        svc = _service(db_session)
        session = await svc.get_or_create(
            user_id=str(user.id),
            lesson_id=lesson.id,
            lesson_version_id=None,
            topic_index=0,
            total_topics=2,
        )
        advanced = await svc.advance(
            session_id=session.public_id,
            user_id=str(user.id),
            total_topics=2,
        )
        assert advanced is not None
        assert advanced.current_block_position == 1
        assert advanced.status == LearningSessionStatus.COMPLETED.value

    async def test_set_topic_returns_none_for_foreign_session(
        self, db_session, make_user, make_presentation
    ) -> None:
        owner_a = await make_user()
        owner_b = await make_user()
        lesson = await _make_lesson(db_session, await make_presentation())
        svc = _service(db_session)
        session = await svc.get_or_create(
            user_id=str(owner_a.id),
            lesson_id=lesson.id,
            lesson_version_id=None,
            topic_index=0,
            total_topics=3,
        )
        result = await svc.set_topic(
            session_id=session.public_id,
            user_id=str(owner_b.id),
            topic_index=2,
            total_topics=3,
        )
        assert result is None


class TestSetSlidePosition:
    """P15: slide-accurate resume persistence."""

    async def _session(self, db_session, user, lesson, total_topics=3) -> Any:
        return await _service(db_session).get_or_create(
            user_id=str(user.id),
            lesson_id=lesson.id,
            lesson_version_id=None,
            topic_index=0,
            total_topics=total_topics,
        )

    async def test_persists_slide_and_derives_topic(
        self, db_session, make_user, make_presentation
    ) -> None:
        user = await make_user()
        lesson = await _make_lesson(db_session, await make_presentation())
        session = await self._session(db_session, user, lesson)
        svc = _service(db_session)
        assert session.resume_version == 1

        updated = await svc.set_slide_position(
            session_id=session.public_id,
            user_id=str(user.id),
            slide_index=3,
            total_slides=6,
        )
        assert updated is not None
        # Slide 3 == topic 1, visual slide (concept slide 2 + visual slide 3).
        assert updated.current_slide_position == 3
        assert updated.current_block_position == 1
        assert updated.completion_percentage == round((2 / 3) * 100.0, 1)
        assert updated.resume_version == 2

    async def test_clamps_out_of_range_slide(
        self, db_session, make_user, make_presentation
    ) -> None:
        user = await make_user()
        lesson = await _make_lesson(db_session, await make_presentation())
        session = await self._session(db_session, user, lesson)
        svc = _service(db_session)

        updated = await svc.set_slide_position(
            session_id=session.public_id,
            user_id=str(user.id),
            slide_index=999,
            total_slides=6,
        )
        assert updated is not None
        assert updated.current_slide_position == 5  # clamped to last slide
        assert updated.current_block_position == 2
        assert updated.status == LearningSessionStatus.COMPLETED.value

    async def test_negative_slide_floor_is_zero(
        self, db_session, make_user, make_presentation
    ) -> None:
        user = await make_user()
        lesson = await _make_lesson(db_session, await make_presentation())
        session = await self._session(db_session, user, lesson)
        updated = await _service(db_session).set_slide_position(
            session_id=session.public_id,
            user_id=str(user.id),
            slide_index=-5,
            total_slides=6,
        )
        assert updated is not None
        assert updated.current_slide_position == 0
        assert updated.current_block_position == 0

    async def test_foreign_session_returns_none(
        self, db_session, make_user, make_presentation
    ) -> None:
        owner_a = await make_user()
        owner_b = await make_user()
        lesson = await _make_lesson(db_session, await make_presentation())
        session = await self._session(db_session, owner_a, lesson)
        result = await _service(db_session).set_slide_position(
            session_id=session.public_id,
            user_id=str(owner_b.id),
            slide_index=2,
            total_slides=6,
        )
        assert result is None
        # Owner A's position is untouched by B's rejected attempt.
        row = await _service(db_session).find_by_public_id(
            session.public_id, user_id=str(owner_a.id)
        )
        assert row is not None
        assert row.current_slide_position == 0

    async def test_to_player_session_carries_resume_slide(
        self, db_session, make_user, make_presentation
    ) -> None:
        user = await make_user()
        lesson = await _make_lesson(db_session, await make_presentation())
        session = await self._session(db_session, user, lesson)
        svc = _service(db_session)
        await svc.set_slide_position(
            session_id=session.public_id,
            user_id=str(user.id),
            slide_index=4,
            total_slides=6,
        )
        serialized = svc.to_player_session(session, 3, total_slides=6)
        assert serialized["slide_index"] == 4
        assert serialized["topic_index"] == 2
        assert serialized["completion_percentage"] == 100.0
        assert serialized["total_topics"] == 3
