"""Unit tests for the P16 video project service and render lifecycle.

Exercises persistence, ownership scoping, the render lifecycle
(queued → rendering → ready|failed), re-render conflicts and the per-user
concurrency cap — without any HTTP layer or background dispatch.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.user import User
from app.models.video_project import VideoProjectRecord, VideoRenderStatus
from app.services.video_project_builder import build_visual_learning_model, compose_project
from app.services.video_project_service import VideoProjectService
from app.services.video_render_backend import MockRenderBackend
from tests.conftest import TEST_USER_ID

pytestmark = pytest.mark.asyncio

_OTHER_USER_ID = uuid.UUID("00000000-0000-0000-0000-0000000000ff")


@pytest.fixture(autouse=True)
async def _cleanup_video_projects(db_session: AsyncSession) -> Any:
    """Service writes commit across tests; remove rows so counts stay hermetic."""
    yield
    await db_session.execute(delete(VideoProjectRecord))
    await db_session.commit()


async def _reset_projects(session: AsyncSession) -> None:
    await session.execute(delete(VideoProjectRecord))
    await session.commit()


@pytest.fixture
async def other_user(db_session: AsyncSession) -> uuid.UUID:
    from app.core.security import hash_password

    existing = await db_session.execute(
        select(User).where(User.id == _OTHER_USER_ID)
    )
    if existing.scalar_one_or_none() is None:
        db_session.add(
            User(
                id=_OTHER_USER_ID,
                email="p16_other@test.com",
                name="P16 Other",
                password_hash=hash_password("testpassword123"),
            )
        )
        await db_session.commit()
    return _OTHER_USER_ID


async def _compose_blueprint(topic: str = "P16 CPU Pipelining") -> dict[str, Any]:
    model = await build_visual_learning_model(topic=topic, description=None, components=[])
    project = compose_project(topic=topic, model=model)
    return project.model_dump(mode="json")


class _FailingBackend:
    def render(self, project: Any, progress: Any) -> Any:
        raise RuntimeError("renderer exploded")


async def _make_project(
    session: AsyncSession,
    *,
    topic: str = "P16 CPU Pipelining",
    user_id: uuid.UUID = TEST_USER_ID,
    dispatch: bool = False,
) -> VideoProjectRecord:
    blueprint = await _compose_blueprint(topic)
    service = VideoProjectService(session)
    return await service.create(
        user_id=user_id,
        video_id=blueprint["video_id"],
        topic=topic,
        project_data=blueprint,
        dispatch_render=dispatch,
    )


async def test_create_persists_owned_queued_row(db_session: AsyncSession) -> None:
    record = await _make_project(db_session)
    assert record.public_id.startswith("vproj_")
    assert record.user_id == TEST_USER_ID
    assert record.status == VideoRenderStatus.QUEUED
    assert record.progress_percentage == 0.0
    assert record.project_data is not None
    assert record.project_data["topic"] == "P16 CPU Pipelining"


async def test_list_owned_isolation(
    db_session: AsyncSession, other_user: uuid.UUID
) -> None:
    service = VideoProjectService(db_session)
    await _make_project(db_session, topic="Mine A")
    await _make_project(db_session, topic="Mine B")
    await _make_project(db_session, user_id=other_user, topic="Theirs")

    mine = await service.list_owned(TEST_USER_ID)
    theirs = await service.list_owned(other_user)

    assert [r.topic for r in mine] == ["Mine B", "Mine A"]
    assert [r.topic for r in theirs] == ["Theirs"]


async def test_get_owned_missing_and_foreign(
    db_session: AsyncSession, other_user: uuid.UUID
) -> None:
    service = VideoProjectService(db_session)
    theirs = await _make_project(db_session, user_id=other_user, topic="Theirs")

    assert await service.get_owned(TEST_USER_ID, "vproj_doesnotexist") is None
    assert await service.get_owned(TEST_USER_ID, theirs.public_id) is None
    assert await service.get_owned(other_user, theirs.public_id) is not None


async def test_render_now_reaches_ready_with_mock_backend(
    db_session: AsyncSession,
) -> None:
    record = await _make_project(db_session)
    service = VideoProjectService(db_session)

    await service.render_now(record, backend=MockRenderBackend())

    assert record.status == VideoRenderStatus.READY
    assert record.progress_percentage == 100.0
    assert record.playable_url, "ready project must have a playable URL"
    assert record.playable_url.endswith(f"{record.video_id}.mp4")
    rendered_path = os.path.join("uploads", "videos", f"{record.video_id}.mp4")
    assert os.path.exists(rendered_path)

    refreshed = await service.get_owned(TEST_USER_ID, record.public_id)
    assert refreshed is not None
    assert refreshed.status == VideoRenderStatus.READY
    assert refreshed.playable_url == record.playable_url


async def test_render_now_marks_failed_on_backend_exception(
    db_session: AsyncSession,
) -> None:
    record = await _make_project(db_session)
    service = VideoProjectService(db_session)

    await service.render_now(record, backend=_FailingBackend())

    assert record.status == VideoRenderStatus.FAILED
    assert record.error, "failed render must record an error"
    assert "renderer exploded" in record.error


async def test_request_render_missing_raises_not_found(db_session: AsyncSession) -> None:
    service = VideoProjectService(db_session)
    with pytest.raises(NotFoundError):
        await service.request_render(TEST_USER_ID, "vproj_nope")


async def test_request_render_conflicts_when_active(db_session: AsyncSession) -> None:
    record = await _make_project(db_session)
    record.status = VideoRenderStatus.RENDERING
    await db_session.commit()

    service = VideoProjectService(db_session)
    with pytest.raises(ConflictError):
        await service.request_render(TEST_USER_ID, record.public_id)


async def test_request_render_allows_force_on_active(db_session: AsyncSession) -> None:
    record = await _make_project(db_session)
    record.status = VideoRenderStatus.RENDERING
    db_session.add(record)
    await db_session.commit()

    service = VideoProjectService(db_session)
    updated = await service.request_render(TEST_USER_ID, record.public_id, force=True)
    assert updated.status == VideoRenderStatus.QUEUED


async def test_per_user_concurrency_cap(
    db_session: AsyncSession, other_user: uuid.UUID
) -> None:
    await _reset_projects(db_session)
    service = VideoProjectService(db_session)
    one = await _make_project(db_session, topic="Cap One")
    two = await _make_project(db_session, topic="Cap Two")
    one.status = VideoRenderStatus.QUEUED
    two.status = VideoRenderStatus.QUEUED
    await db_session.commit()

    with pytest.raises(ConflictError) as exc_info:
        await service.request_render(TEST_USER_ID, one.public_id)
    assert exc_info.value.status_code == 409

    # Another user is unaffected by the cap.
    await _make_project(db_session, user_id=other_user, topic="Their cap")
    assert await service.repo.count_active(TEST_USER_ID) == 2
    assert await service.repo.count_active(other_user) == 1


async def test_re_render_ready_project_is_allowed(db_session: AsyncSession) -> None:
    await _reset_projects(db_session)
    record = await _make_project(db_session)
    service = VideoProjectService(db_session)
    await service.render_now(record, backend=MockRenderBackend())
    assert record.status == VideoRenderStatus.READY

    updated = await service.request_render(TEST_USER_ID, record.public_id, force=True)
    assert updated.status == VideoRenderStatus.QUEUED


async def test_record_to_dict_shape(db_session: AsyncSession) -> None:
    from app.services.video_project_service import record_to_dict

    record = await _make_project(db_session)
    dto = record_to_dict(record)
    assert set(dto) == {
        "public_id",
        "video_id",
        "topic",
        "status",
        "progress_percentage",
        "playable_url",
        "error",
        "created_at",
        "updated_at",
    }
