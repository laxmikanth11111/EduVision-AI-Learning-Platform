from __future__ import annotations

import pytest

from app.database.unit_of_work import UnitOfWork
from app.models.generated_block import GeneratedBlock
from app.models.generated_lesson import GeneratedLesson
from app.models.generated_lesson_version import GeneratedLessonVersion
from app.services.lesson_player_service import LessonPlayerService

pytestmark = pytest.mark.asyncio


async def _seed_lesson(
    db_session,
    presentation,
    *,
    block_count: int = 6,
) -> GeneratedLesson:
    lesson = GeneratedLesson(
        presentation_id=presentation.id,
        user_id=None,
        mode="slide",
        status="ready",
        title="Player Lesson",
        language="en",
        difficulty="beginner",
        latest_version=1,
    )
    db_session.add(lesson)
    await db_session.flush()
    version = GeneratedLessonVersion(
        lesson_id=lesson.id,
        version=1,
        status="succeeded",
        title="Player Lesson",
        summary="A summary",
        language="en",
        completed_at=None,
    )
    db_session.add(version)
    await db_session.flush()
    for i in range(block_count):
        db_session.add(
            GeneratedBlock(
                lesson_version_id=version.id,
                block_type="heading" if i % 3 == 0 else "paragraph",
                position=i,
                heading=f"Section {i}" if i % 3 == 0 else None,
                content=f"Body {i}",
            )
        )
    await db_session.flush()
    return lesson


def _player(db_session) -> LessonPlayerService:
    return LessonPlayerService(UnitOfWork(session=db_session))


class TestGetState:
    async def test_get_state_returns_full_payload(
        self, db_session, make_presentation
    ) -> None:
        presentation = await make_presentation()
        lesson = await _seed_lesson(db_session, presentation)

        state = await _player(db_session).get_state(lesson.public_id)

        assert state["lesson"]["id"] == lesson.public_id
        assert state["version"] is not None
        assert state["version"]["version"] == 1
        assert len(state["topics"]) >= 1
        assert state["session"] is None

    async def test_get_state_groups_blocks_into_topics(
        self, db_session, make_presentation
    ) -> None:
        presentation = await make_presentation()
        lesson = await _seed_lesson(db_session, presentation, block_count=6)

        state = await _player(db_session).get_state(lesson.public_id)

        assert len(state["topics"]) >= 2

    async def test_get_state_raises_for_missing_lesson(
        self, db_session,
    ) -> None:
        import uuid
        with pytest.raises(ValueError, match="not found"):
            await _player(db_session).get_state(str(uuid.uuid4()))


class TestStart:
    async def test_start_creates_session(
        self, db_session, make_presentation
    ) -> None:
        presentation = await make_presentation()
        lesson = await _seed_lesson(db_session, presentation)

        state = await _player(db_session).start(lesson.public_id)

        assert state["session"] is not None
        assert state["session"]["status"] == "active"
        assert state["session"]["topic_index"] == 0

    async def test_start_is_idempotent(
        self, db_session, make_presentation
    ) -> None:
        presentation = await make_presentation()
        lesson = await _seed_lesson(db_session, presentation)
        player = _player(db_session)

        first = await player.start(lesson.public_id)
        second = await player.start(lesson.public_id)

        assert first["session"]["session_id"] != second["session"]["session_id"]
