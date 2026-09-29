"""P16 video project runtime on real PostgreSQL.

Runs against the Alembic-migrated scratch database (postgres:16-alpine) so the
persistence layer exercises the production schema lineage: ``video_projects`` is
created by migration ``0036_c4_topic_animation_assets`` (single head after ``0034``), with
the ``ck_video_projects_status`` check, ``ix_video_projects_user_status`` index
and the JSONB ``project_data`` column.

It drives ``VideoProjectService`` against the real engine: create → render →
ready round-trip survives a DB reload, cross-user reads 404-equalize, and the
check constraint rejects an unknown status.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.video_project import VideoProjectRecord, VideoRenderStatus
from app.services.video_project_builder import build_visual_learning_model, compose_project
from app.services.video_project_service import VideoProjectService
from app.services.video_render_backend import MockRenderBackend
from tests.postgres.conftest import expected_migration_head

pytestmark = pytest.mark.postgres


@pytest_asyncio.fixture
async def pg_owner(pg_session: AsyncSession) -> User:
    user = User(
        email=f"{uuid.uuid4().hex[:20]}@test.local",
        name="P16 PG Learner",
    )
    pg_session.add(user)
    await pg_session.flush()
    return user


async def _compose_blueprint(topic: str) -> dict[str, Any]:
    model = await build_visual_learning_model(topic=topic, description=None, components=[])
    return compose_project(topic=topic, model=model).model_dump(mode="json")


async def test_p16_migration_head_is_0034(pg_session: AsyncSession) -> None:
    head = (await pg_session.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
    assert head == expected_migration_head()


async def test_p16_video_projects_table_and_constraints(pg_session: AsyncSession) -> None:
    table_row = (
        await pg_session.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_name = 'video_projects'"
            )
        )
    ).scalar_one_or_none()
    assert table_row == "video_projects"

    columns = {
        row[0]
        for row in await pg_session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'video_projects'"
            )
        )
    }
    assert {
        "public_id",
        "user_id",
        "video_id",
        "topic",
        "status",
        "progress_percentage",
        "playable_url",
        "error",
        "project_data",
    }.issubset(columns)

    data_type = (
        await pg_session.execute(
            text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name='video_projects' AND column_name='project_data'"
            )
        )
    ).scalar_one()
    assert data_type == "jsonb"

    index_exists = (
        await pg_session.execute(
            text(
                "SELECT 1 FROM pg_indexes WHERE indexname = "
                "'ix_video_projects_user_status'"
            )
        )
    ).scalar_one_or_none()
    assert index_exists == 1


async def test_p16_pg_check_constraint_rejects_unknown_status(
    pg_session: AsyncSession, pg_owner: User
) -> None:
    """The DB constraint (not the ORM) is the last line of defence for status."""
    record = VideoProjectRecord(
        user_id=pg_owner.id,
        video_id="video_invalidstatus",
        topic="Check constraint",
        status="flying",
    )
    pg_session.add(record)
    with pytest.raises(IntegrityError):
        await pg_session.flush()
    await pg_session.rollback()


async def test_p16_lifecycle_round_trip_on_migrated_schema(
    pg_session: AsyncSession, pg_owner: User
) -> None:
    blueprint = await _compose_blueprint("PG P16 Lifecycle")
    service = VideoProjectService(pg_session)
    record = await service.create(
        user_id=pg_owner.id,
        video_id=blueprint["video_id"],
        topic="PG P16 Lifecycle",
        project_data=blueprint,
        dispatch_render=False,
    )
    assert record.public_id.startswith("vproj_")
    assert record.status == VideoRenderStatus.QUEUED

    await service.render_now(record, backend=MockRenderBackend())
    assert record.status == VideoRenderStatus.READY
    assert record.progress_percentage == 100.0
    assert record.playable_url == f"/uploads/videos/{blueprint['video_id']}.mp4"

    stored = (
        await pg_session.execute(
            select(VideoProjectRecord)
            .where(VideoProjectRecord.public_id == record.public_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert stored.status == VideoRenderStatus.READY
    assert stored.topic == "PG P16 Lifecycle"
    assert stored.project_data["topic"] == "PG P16 Lifecycle"

    jsonb_topic = (
        await pg_session.execute(
            text(
                "SELECT project_data->>'topic' FROM video_projects "
                "WHERE public_id = :pid"
            ),
            {"pid": record.public_id},
        )
    ).scalar_one()
    assert jsonb_topic == "PG P16 Lifecycle"


async def test_p16_cross_user_404_equalizes_on_pg(
    pg_session: AsyncSession, pg_owner: User
) -> None:
    blueprint = await _compose_blueprint("PG P16 Private")
    service = VideoProjectService(pg_session)
    record = await service.create(
        user_id=pg_owner.id,
        video_id=blueprint["video_id"],
        topic="PG P16 Private",
        project_data=blueprint,
        dispatch_render=False,
    )

    other = User(
        email=f"{uuid.uuid4().hex[:20]}@test.local",
        name="P16 PG Other Learner",
    )
    pg_session.add(other)
    await pg_session.flush()

    assert await service.get_owned(other.id, record.public_id) is None
    assert await service.get_owned(other.id, "vproj_doesnotexist") is None

    owner_rows = await service.list_owned(pg_owner.id)
    other_rows = await service.list_owned(other.id)
    assert record.public_id in [r.public_id for r in owner_rows]
    assert other_rows == []


async def test_p16_cap_and_conflict_on_pg(
    pg_session: AsyncSession, pg_owner: User
) -> None:
    from app.core.exceptions import ConflictError

    service = VideoProjectService(pg_session)
    first = await service.create(
        user_id=pg_owner.id,
        video_id=(await _compose_blueprint("PG Cap One"))["video_id"],
        topic="PG Cap One",
        project_data=await _compose_blueprint("PG Cap One"),
        dispatch_render=False,
    )
    second = await service.create(
        user_id=pg_owner.id,
        video_id=(await _compose_blueprint("PG Cap Two"))["video_id"],
        topic="PG Cap Two",
        project_data=await _compose_blueprint("PG Cap Two"),
        dispatch_render=False,
    )
    assert await service.repo.count_active(pg_owner.id) == 2

    with pytest.raises(ConflictError):
        await service.request_render(pg_owner.id, first.public_id)

    # Marking one READY frees the slot, but the active project still conflicts.
    await service.render_now(first, backend=MockRenderBackend())
    with pytest.raises(ConflictError):
        await service.request_render(pg_owner.id, second.public_id)

    await service.render_now(second, backend=MockRenderBackend())
    re_render = await service.request_render(pg_owner.id, first.public_id, force=True)
    assert re_render.status == VideoRenderStatus.QUEUED
