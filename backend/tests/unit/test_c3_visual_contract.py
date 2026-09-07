"""C3.11 API contract — every layer agrees that topic_id/subtopic_id are titles.

The generation request carries outline-title hints (not UUIDs), the persisted
asset stores those titles on ``topic_id``/``subtopic_id``, and the API validates
the hint against the actual outline instead of silently generating nothing.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.unit_of_work import UnitOfWork, get_unit_of_work
from app.main import app
from app.models.presentation import Presentation
from app.models.topic_outline import TopicOutline
from app.models.topic_visual_asset import TopicVisualAsset
from app.repositories.topic_visual_asset_repository import TopicVisualAssetRepository
from app.schemas.c3_visual_intelligence import (
    VisualGenerationRequest,
    compute_visual_fingerprint,
)
from app.services.c3_visual_planning_pipeline import C3VisualPlanningPipeline
from tests.conftest import TEST_USER_ID

OUTLINE = [
    {
        "title": "TCP Handshake Process",
        "slide_ranges": [1, 2],
        "subtopics": [
            {
                "title": "Three-Way Handshake",
                "concepts": [
                    {"name": "SYN", "description": "synchronize"},
                    {"name": "SYN-ACK", "description": "ack sync"},
                    {"name": "ACK", "description": "acknowledge"},
                    {"name": "Sequence", "description": "ordering"},
                    {"name": "Window", "description": "flow control"},
                ],
            }
        ],
    }
]


async def _seed(db_session: AsyncSession) -> Presentation:
    pres = Presentation(title="C3 Contract Deck", owner_id=TEST_USER_ID, slide_count=2)
    db_session.add(pres)
    await db_session.flush()
    repo = TopicVisualAssetRepository(db_session)
    pipeline = C3VisualPlanningPipeline(asset_repo=repo)
    from app.schemas.topic_outline import Concept, OutlineTopic, Subtopic

    topic = OutlineTopic(
        title="TCP Handshake Process",
        slide_ranges=[1, 2],
        subtopics=[
            Subtopic(
                title="Three-Way Handshake",
                concepts=[
                    Concept(name=c["name"], description=c["description"])
                    for c in OUTLINE[0]["subtopics"][0]["concepts"]
                ],
            )
        ],
    )
    plan = await pipeline.plan_presentation_visuals(
        presentation_id=str(pres.id),
        user_id=TEST_USER_ID,
        topics=[topic],
    )
    for tp in plan.topic_plans:
        if tp.visual_needed and tp.specification:
            await pipeline.generate_and_persist_visual(
                plan=tp,
                presentation_id=str(pres.id),
                user_id=TEST_USER_ID,
            )
    await db_session.commit()
    return pres


def test_c3_contract_01_request_uses_titles_not_uuids():
    req = VisualGenerationRequest(
        presentation_id="pres-123",
        topic_id="TCP Handshake Process",
        subtopic_id="Three-Way Handshake",
    )
    assert req.topic_id == "TCP Handshake Process"
    assert req.subtopic_id == "Three-Way Handshake"
    assert req.force_regenerate is False


@pytest.mark.asyncio
async def test_c3_contract_02_persisted_asset_stores_titles(
    db_session: AsyncSession,
):
    pres = await _seed(db_session)

    rows = (
        (
            await db_session.execute(
                select(TopicVisualAsset).where(TopicVisualAsset.presentation_id == pres.id)
            )
        )
        .scalars()
        .all()
    )
    assert rows
    asset = rows[0]
    assert asset.topic_id == "TCP Handshake Process"
    assert asset.topic_title == "TCP Handshake Process"
    assert asset.subtopic_id == "Three-Way Handshake"
    assert asset.subtopic_title == "Three-Way Handshake"


@pytest.mark.asyncio
async def test_c3_contract_03_fingerprint_contract_matches_pipeline(
    db_session: AsyncSession,
):
    pres = await _seed(db_session)
    fingerprint = compute_visual_fingerprint(
        str(pres.id),
        "TCP Handshake Process",
        "Three-Way Handshake",
        [
            "TCP Handshake Process:SYN",
            "TCP Handshake Process:SYN-ACK",
            "TCP Handshake Process:ACK",
            "TCP Handshake Process:Sequence",
            "TCP Handshake Process:Window",
        ],
    )
    rows = (
        (
            await db_session.execute(
                select(TopicVisualAsset).where(TopicVisualAsset.presentation_id == pres.id)
            )
        )
        .scalars()
        .all()
    )
    assert any(r.fingerprint == fingerprint for r in rows)


@pytest.mark.asyncio
async def test_c3_contract_04_valid_outline_title_hint_dispatches(
    client: AsyncClient,
    db_session: AsyncSession,
):
    async def _get_uow_override():
        yield UnitOfWork(session=db_session)

    app.dependency_overrides[get_unit_of_work] = _get_uow_override
    try:
        pres = Presentation(title="C3 Contract Grid", owner_id=TEST_USER_ID, slide_count=2)
        db_session.add(pres)
        await db_session.flush()
        db_session.add(
            TopicOutline(
                presentation_id=pres.id,
                title="C3 Contract Grid",
                status="succeeded",
                topics=OUTLINE,
            )
        )
        await db_session.commit()

        with patch(
            "app.workers.tasks.safe_dispatch",
            new=MagicMock(),
        ) as dispatch_mock:
            res = await client.post(
                "/api/v1/c3/visuals/generate",
                json={
                    "presentation_id": pres.public_id,
                    "topic_id": "TCP Handshake Process",
                    "subtopic_id": "Three-Way Handshake",
                },
            )
            assert res.status_code == 202
            assert res.json()["success"] is True
            assert dispatch_mock.called
    finally:
        app.dependency_overrides.pop(get_unit_of_work, None)


@pytest.mark.asyncio
async def test_c3_contract_05_unknown_topic_title_hint_rejected(
    client: AsyncClient,
    db_session: AsyncSession,
):
    async def _get_uow_override():
        yield UnitOfWork(session=db_session)

    app.dependency_overrides[get_unit_of_work] = _get_uow_override
    try:
        pres = Presentation(title="C3 Contract Grid", owner_id=TEST_USER_ID, slide_count=2)
        db_session.add(pres)
        await db_session.flush()
        db_session.add(
            TopicOutline(
                presentation_id=pres.id,
                title="C3 Contract Grid",
                status="succeeded",
                topics=OUTLINE,
            )
        )
        await db_session.commit()

        with patch(
            "app.workers.tasks.safe_dispatch",
            new=MagicMock(),
        ) as dispatch_mock:
            res = await client.post(
                "/api/v1/c3/visuals/generate",
                json={
                    "presentation_id": pres.public_id,
                    "topic_id": "A UUID-Like Topic That Does Not Exist",
                },
            )
            assert res.status_code == 422
            assert "is not a topic title" in res.json()["error"]["message"]
            assert res.headers.get("x-c3-contract") == "topic_id-is-outline-title"
            assert not dispatch_mock.called
    finally:
        app.dependency_overrides.pop(get_unit_of_work, None)


@pytest.mark.asyncio
async def test_c3_contract_06_unknown_subtopic_title_hint_rejected(
    client: AsyncClient,
    db_session: AsyncSession,
):
    async def _get_uow_override():
        yield UnitOfWork(session=db_session)

    app.dependency_overrides[get_unit_of_work] = _get_uow_override
    try:
        pres = Presentation(title="C3 Contract Grid", owner_id=TEST_USER_ID, slide_count=2)
        db_session.add(pres)
        await db_session.flush()
        db_session.add(
            TopicOutline(
                presentation_id=pres.id,
                title="C3 Contract Grid",
                status="succeeded",
                topics=OUTLINE,
            )
        )
        await db_session.commit()

        res = await client.post(
            "/api/v1/c3/visuals/generate",
            json={
                "presentation_id": pres.public_id,
                "topic_id": "TCP Handshake Process",
                "subtopic_id": "Not a Real Subtopic",
            },
        )
        assert res.status_code == 422
        assert "is not a subtopic title" in res.json()["error"]["message"]
    finally:
        app.dependency_overrides.pop(get_unit_of_work, None)
