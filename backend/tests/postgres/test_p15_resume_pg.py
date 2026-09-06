"""P15 slide-accurate resume on real PostgreSQL.

Runs against the Alembic-migrated scratch database (postgres:16-alpine) so the
resume path exercises the *production schema lineage*: ``learning_sessions`` was
created by migration ``0009`` (``current_slide_position``, ``current_block_position``,
``completion_percentage``, ``resume_version``) and P15 reuses those columns —
adding NO migration. The head is ``0034_video_projects`` (P16 added the
``video_projects`` table after P15).

It drives ``LearningSessionService`` / ``LearnerProgressService`` directly against
the real engine: slide position + derived topic/completion/resume_version round-
trip, cross-user writes 404-equalize (return None, no leak), and the dashboard
progress payload advertises ``resume_slide``/``resume_link`` from the same row.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.unit_of_work import UnitOfWork
from app.models.generated_block import GeneratedBlock
from app.models.generated_lesson import GeneratedLesson
from app.models.generated_lesson_version import GeneratedLessonVersion
from app.models.presentation import Presentation
from app.models.user import User
from app.services.learner_progress_service import LearnerProgressService
from app.services.learning_session_service import LearningSessionService

pytestmark = pytest.mark.postgres


@pytest_asyncio.fixture
async def resume_seed(pg_session: AsyncSession) -> dict[str, Any]:
    """A user-owned lesson with a succeeded 2-topic version (4 slides)."""
    user = User(
        email=f"{uuid.uuid4().hex[:20]}@test.local",
        name="P15 PG Learner",
    )
    pg_session.add(user)
    await pg_session.flush()

    pres = Presentation(title="P15 Resume Deck", owner_id=user.id, status="published")
    pg_session.add(pres)
    await pg_session.flush()

    lesson = GeneratedLesson(
        presentation_id=pres.id,
        user_id=user.id,
        mode="slide",
        status="ready",
        title="P15 Resume Lesson",
        latest_version=1,
    )
    pg_session.add(lesson)
    await pg_session.flush()

    lv = GeneratedLessonVersion(
        lesson_id=lesson.id,
        version=1,
        status="succeeded",
        title=lesson.title,
        language="en",
        difficulty="beginner",
    )
    pg_session.add(lv)
    await pg_session.flush()
    for pos, heading in enumerate(["Resume PG: First Topic", "Resume PG: Second Topic"]):
        pg_session.add(
            GeneratedBlock(
                lesson_version_id=lv.id,
                block_type="paragraph",
                position=pos,
                heading=heading,
                content=f"Body for {heading}.",
            )
        )
    await pg_session.commit()

    return {
        "user": user,
        "lesson_public_id": str(lesson.public_id),
        "lesson_id": lesson.id,
    }


async def test_p15_no_new_migration_head_unchanged(pg_session: AsyncSession) -> None:
    """P15 adds no migration; the Alembic head is 0034 (P16 added it afterwards)."""
    head = (await pg_session.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
    assert head == "0034_video_projects"


async def test_p15_position_persists_on_migrated_schema(
    pg_session: AsyncSession, resume_seed: dict[str, Any]
) -> None:
    """Slide position + derived topic/completion/resume_version round-trip."""
    uow = UnitOfWork(pg_session, retry_on_transient=False)
    service = LearningSessionService(uow)
    user = resume_seed["user"]

    session = await service.get_or_create(
        user_id=str(user.id),
        lesson_id=resume_seed["lesson_id"],
        lesson_version_id=None,
        topic_index=0,
        total_topics=2,
    )
    assert session.current_slide_position == 0
    assert session.resume_version == 1

    updated = await service.set_slide_position(
        session_id=session.public_id,
        user_id=str(user.id),
        slide_index=3,
        total_slides=4,
    )
    assert updated is not None
    # Slide 3 == topic 1, visual slide of the second topic -> completed lesson.
    assert updated.current_slide_position == 3
    assert updated.current_block_position == 1
    assert updated.completion_percentage == 100.0
    assert updated.resume_version == 2
    assert updated.status == "completed"

    # DB-reloaded row (identity-map expiry) reflects the persisted value.
    from app.models.learning_session import LearningSession  # noqa: PLC0415

    row = (
        await pg_session.execute(
            select(LearningSession)
            .where(LearningSession.id == session.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert row.current_slide_position == 3
    assert row.current_block_position == 1
    assert row.completion_percentage == 100.0
    assert row.resume_version == 2

    # Serialization exposes the slide-accurate resume anchor.
    payload = service.to_player_session(row, 2, total_slides=4)
    assert payload["slide_index"] == 3
    assert payload["topic_index"] == 1
    assert payload["completion_percentage"] == 100.0


async def test_p15_cross_user_position_404_equalizes_on_pg(
    pg_session: AsyncSession, resume_seed: dict[str, Any]
) -> None:
    uow = UnitOfWork(pg_session, retry_on_transient=False)
    service = LearningSessionService(uow)
    owner = resume_seed["user"]

    session = await service.get_or_create(
        user_id=str(owner.id),
        lesson_id=resume_seed["lesson_id"],
        lesson_version_id=None,
        topic_index=0,
        total_topics=2,
    )

    other = User(
        email=f"{uuid.uuid4().hex[:20]}@test.local",
        name="P15 PG Other Learner",
    )
    pg_session.add(other)
    await pg_session.flush()

    # B cannot move A's session: indistinguishable from "no session".
    result = await service.set_slide_position(
        session_id=session.public_id,
        user_id=str(other.id),
        slide_index=3,
        total_slides=4,
    )
    assert result is None

    # A's position stays at slide 0.
    from app.models.learning_session import LearningSession  # noqa: PLC0415

    row = (
        await pg_session.execute(
            select(LearningSession)
            .where(LearningSession.id == session.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert row.current_slide_position == 0
    assert row.current_block_position == 0


async def test_p15_progress_resume_fields_on_pg(
    pg_session: AsyncSession, resume_seed: dict[str, Any]
) -> None:
    uow = UnitOfWork(pg_session, retry_on_transient=False)
    service = LearningSessionService(uow)
    user = resume_seed["user"]

    session = await service.get_or_create(
        user_id=str(user.id),
        lesson_id=resume_seed["lesson_id"],
        lesson_version_id=None,
        topic_index=0,
        total_topics=2,
    )
    await service.set_slide_position(
        session_id=session.public_id,
        user_id=str(user.id),
        slide_index=2,
        total_slides=4,
    )
    await pg_session.commit()

    progress = await LearnerProgressService(uow).get_progress(user.id)
    items = progress.lesson_progress
    assert len(items) == 1, "the seeded lesson must appear as a progress row"
    item = items[0]
    assert item.lesson_id == resume_seed["lesson_public_id"]
    assert item.resume_slide == 2
    assert item.resume_link == (
        f"/frontend/player.html?lesson={resume_seed['lesson_public_id']}&slide=2"
    )
