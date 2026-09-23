from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.database.unit_of_work import UnitOfWork
from app.models.content_unit import ContentUnit
from app.models.generated_block import GeneratedBlock
from app.models.generated_lesson import GeneratedLesson
from app.models.generated_lesson_version import GeneratedLessonVersion
from app.models.quiz import Quiz
from app.models.quiz_attempt import QuizAttempt
from app.models.quiz_version import QuizVersion
from app.models.user import User
from app.services.lesson_player_service import LessonPlayerService
from shared.constants import ContentUnitType, PlayerMode

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


async def _seed_source_units(db_session, presentation, count: int = 6) -> None:
    """Attach ``count`` source ContentUnits to a presentation's deck."""
    for position in range(count):
        db_session.add(
            ContentUnit(
                presentation_id=presentation.id,
                unit_type=ContentUnitType.SLIDE.value,
                position=position,
                title=f"Source Unit {position}",
                raw_text=f"Raw text for source unit {position}.",
            )
        )
    await db_session.flush()


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


class TestPersistentResume:
    async def test_resumes_same_session_for_owner(
        self, db_session, make_user, make_presentation
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(owner_id=user.id)
        lesson = await _seed_lesson(db_session, presentation, block_count=3)
        player = _player(db_session)
        owner = str(user.id)

        start = await player.start(lesson.public_id, owner_id=owner)
        assert start["session"]["topic_index"] == 0

        advanced = await player.advance_topic(
            start["session"]["session_id"], owner_id=owner
        )
        assert advanced["topic_index"] == 1

        resumed = await player.start(lesson.public_id, owner_id=owner)
        assert resumed["session"]["session_id"] == start["session"]["session_id"]
        assert resumed["session"]["topic_index"] == 1

        state = await player.get_state(lesson.public_id, owner_id=owner)
        assert state["session"]["session_id"] == start["session"]["session_id"]
        assert state["session"]["topic_index"] == 1

    async def test_wont_resume_cross_owner_session(
        self, db_session, make_user, make_presentation
    ) -> None:
        owner_a = await make_user()
        owner_b = await make_user()
        presentation = await make_presentation(owner_id=owner_a.id)
        lesson = await _seed_lesson(db_session, presentation, block_count=3)
        player = _player(db_session)

        start = await player.start(lesson.public_id, owner_id=str(owner_a.id))

        # owner B cannot see or advance owner A's session.
        with pytest.raises(ValueError, match="not found"):
            await player.advance_topic(
                start["session"]["session_id"], owner_id=str(owner_b.id)
            )

        # owner B cannot even read owner A's lesson (ownership gate).
        with pytest.raises(PermissionError):
            await player.get_state(lesson.public_id, owner_id=str(owner_b.id))


async def _seed_checkpoint(
    db_session,
    lesson: GeneratedLesson,
    *,
    attempts: list[tuple[uuid.UUID, float]],
    passing_score: float = 70.0,
) -> Quiz:
    quiz = Quiz(
        presentation_id=lesson.presentation_id,
        lesson_id=lesson.id,
        user_id=None,
        mode="practice",
        status="ready",
        title="Checkpoint Quiz",
        description=None,
        passing_score=passing_score,
        question_count=3,
    )
    db_session.add(quiz)
    await db_session.flush()
    version = QuizVersion(quiz_id=quiz.id, version=1, status="published")
    db_session.add(version)
    await db_session.flush()
    for attempt_number, (user, percent) in enumerate(attempts, start=1):
        db_session.add(
            QuizAttempt(
                quiz_id=quiz.id,
                quiz_version_id=version.id,
                user_id=user,
                attempt_number=attempt_number,
                status="completed",
                percent_score=percent,
                score=percent,
                max_score=100.0,
                completed_at=datetime.now(UTC),
            )
        )
    await db_session.flush()
    return quiz


class TestCheckpoint:
    async def _make_owner(self, db_session) -> User:
        user = User(
            email=f"{uuid.uuid4().hex}@example.com",
            name="Checkpoint Owner",
        )
        db_session.add(user)
        await db_session.flush()
        return user

    async def test_reports_checkpoint_with_latest_attempt(
        self, db_session, make_presentation
    ) -> None:
        user = await self._make_owner(db_session)
        presentation = await make_presentation(owner_id=user.id)
        lesson = await _seed_lesson(db_session, presentation, block_count=3)
        await _seed_checkpoint(
            db_session, lesson, attempts=[(user.id, 85.0)]
        )

        result = await _player(db_session).get_checkpoint(
            lesson.public_id, owner_id=str(user.id)
        )

        assert result["has_checkpoint"] is True
        assert result["quiz"]["title"] == "Checkpoint Quiz"
        assert result["completed"] is True
        assert result["latest_attempt"]["percent_score"] == 85.0
        assert result["latest_attempt"]["passed"] is True

    async def test_reports_no_checkpoint_when_none_bound(
        self, db_session, make_presentation
    ) -> None:
        user = await self._make_owner(db_session)
        presentation = await make_presentation(owner_id=user.id)
        lesson = await _seed_lesson(db_session, presentation, block_count=3)

        result = await _player(db_session).get_checkpoint(
            lesson.public_id, owner_id=str(user.id)
        )

        assert result["has_checkpoint"] is False
        assert result["quiz"] is None

    async def test_checkpoint_blocks_foreign_owner(
        self, db_session, make_presentation
    ) -> None:
        owner_a = await self._make_owner(db_session)
        owner_b = await self._make_owner(db_session)
        presentation = await make_presentation(owner_id=owner_a.id)
        lesson = await _seed_lesson(db_session, presentation, block_count=3)
        await _seed_checkpoint(db_session, lesson, attempts=[(owner_a.id, 50.0)])

        with pytest.raises(PermissionError):
            await _player(db_session).get_checkpoint(
                lesson.public_id, owner_id=str(owner_b.id)
            )


class TestSessionTotalSlides:
    """F1: the mode-aware deck denominator that completion is indexed against.

    Verified against ``LessonPlayerService._session_total_slides`` so the
    regression is pinned at the unit boundary where the drift lived.
    """

    async def test_source_mode_uses_source_count(self) -> None:
        svc = LessonPlayerService._session_total_slides
        assert svc(PlayerMode.SOURCE.value, source_count=0, total_topics=3) == 1
        assert svc(PlayerMode.SOURCE.value, source_count=5, total_topics=3) == 5

    async def test_learning_mode_is_two_slides_per_topic(self) -> None:
        svc = LessonPlayerService._session_total_slides
        assert svc(PlayerMode.LEARNING.value, source_count=0, total_topics=3) == 6

    async def test_learning_mode_ignores_source_count_when_it_exceeds_deck(self) -> None:
        # A 3-topic lesson has a 6-slide learning deck. With 10 uploaded source
        # units the denominator previously inflated to 10, capping completion at
        # 60%. It must stay 6 regardless of how many source units exist.
        svc = LessonPlayerService._session_total_slides
        assert svc(PlayerMode.LEARNING.value, source_count=10, total_topics=3) == 6

    async def test_visual_and_animation_modes_follow_learning_deck(self) -> None:
        svc = LessonPlayerService._session_total_slides
        assert svc("visual", source_count=10, total_topics=3) == 6
        assert svc("animation", source_count=10, total_topics=3) == 6

    async def test_learning_mode_never_returns_zero_denominator(self) -> None:
        svc = LessonPlayerService._session_total_slides
        assert svc(PlayerMode.LEARNING.value, source_count=0, total_topics=0) == 1


class TestLearningCompletionIgnoresSourceCount:
    """F1: learning-mode completion is driven by the topic deck, not by how many
    uploaded source units outnumber 2 * topics (size-drift regression)."""

    async def test_final_learning_slide_reaches_100_with_surplus_source_units(
        self, db_session, make_user, make_presentation
    ) -> None:
        user = await make_user()
        presentation = await make_presentation(owner_id=user.id)
        lesson = await _seed_lesson(db_session, presentation, block_count=2)
        await _seed_source_units(db_session, presentation, count=6)
        player = _player(db_session)
        owner = str(user.id)

        start = await player.start(lesson.public_id, owner_id=owner)
        session_id = start["session"]["session_id"]

        # First topic (slide 0) == exactly 50% on a 2-topic deck. The 6 source
        # units must not dilute the bucket to 33.3%.
        mid = await player.set_position(
            session_id, 0, owner_id=owner, player_mode=PlayerMode.LEARNING.value
        )
        assert mid is not None
        assert mid["completion_percentage"] == 50.0

        # Final learning slide (3) must reach 100% even with 6 > 2 * 2 units.
        final = await player.set_position(
            session_id, 3, owner_id=owner, player_mode=PlayerMode.LEARNING.value
        )
        assert final is not None
        assert final["slide_index"] == 3
        assert final["topic_index"] == 1
        assert final["completion_percentage"] == 100.0

        # A cold resume serializes the same representation (no phantom slides).
        resumed = await player.start(lesson.public_id, owner_id=owner)
        assert resumed["session"]["slide_index"] == 3
        assert resumed["session"]["completion_percentage"] == 100.0

    async def test_readback_clamps_stale_inflated_denominator_phantom(
        self, db_session, make_user, make_presentation
    ) -> None:
        """A stale learning position persisted under the old inflated
        denominator (max(source_count, 2 * topics) == 6 slides, so slide 5 was
        "valid") must clamp back into the real 4-slide deck on resume. Before
        the fix the readback re-inflated the denominator from the 6 source
        units and kept surfacing the phantom slide 5."""
        from sqlalchemy import select

        from app.models.learning_session import LearningSession

        user = await make_user()
        presentation = await make_presentation(owner_id=user.id)
        lesson = await _seed_lesson(db_session, presentation, block_count=2)
        await _seed_source_units(db_session, presentation, count=6)
        player = _player(db_session)
        owner = str(user.id)

        start = await player.start(lesson.public_id, owner_id=owner)
        session_id = start["session"]["session_id"]

        row = (
            await db_session.execute(
                select(LearningSession).where(LearningSession.public_id == session_id)
            )
        ).scalar_one()
        row.current_slide_position = 5
        row.current_block_position = 2
        row.completion_percentage = round((3 / 5) * 100.0, 1)
        row.player_mode = PlayerMode.LEARNING.value
        await db_session.flush()

        # Resume via start: must clamp the phantom slide into the real deck.
        resumed = await player.start(lesson.public_id, owner_id=owner)
        assert resumed["session"]["slide_index"] == 3, (
            f"resume must clamp stale expanded-denominator slide into the real "
            f"deck, got {resumed['session']['slide_index']}"
        )
        assert resumed["session"]["completion_percentage"] == 60.0  # stored value

        # get_state applies the same clamp.
        state = await player.get_state(lesson.public_id, owner_id=owner)
        assert state["session"]["slide_index"] == 3
