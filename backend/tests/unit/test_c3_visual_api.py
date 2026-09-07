"""Integration tests for the C3 Visual API — ownership, lifecycle, and download."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.unit_of_work import UnitOfWork, get_unit_of_work
from app.main import app
from app.models.presentation import Presentation
from app.repositories.presentation_repository import PresentationRepository
from app.repositories.topic_visual_asset_repository import TopicVisualAssetRepository
from app.schemas.topic_outline import (
    Concept,
    EducationalExample,
    OutlineTopic,
    SourceReference,
    Subtopic,
)
from app.services.c3_visual_planning_pipeline import C3VisualPlanningPipeline
from tests.conftest import TEST_USER_ID

OTHER_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000099")


def _make_topics() -> list[OutlineTopic]:
    return [
        OutlineTopic(
            title="TCP Handshake Process",
            slide_ranges=[1, 2],
            source_references=[SourceReference(slide_number=1, preview="Handshake")],
            learning_objectives=["Explain the TCP three-way handshake sequence"],
            subtopics=[
                Subtopic(
                    title="SYN-ACK Exchange",
                    learning_order=1,
                    source_references=[SourceReference(slide_number=2, preview="Exchange")],
                    concepts=[
                        Concept(name="SYN", description="synchronize"),
                        Concept(name="SYN-ACK", description="ack sync"),
                        Concept(name="ACK", description="acknowledge"),
                    ],
                    examples=[
                        EducationalExample(
                            content=(
                                "The connection setup process advances through sequential "
                                "stages: the client transmits a SYN packet first, the "
                                "server then replies with a SYN-ACK, and the client "
                                "completes the handshake with an ACK packet to finish "
                                "the connection establishment procedure."
                            ),
                            type="source_example",
                        )
                    ],
                )
            ],
        )
    ]


@pytest.mark.asyncio
async def test_c3_api_01_generated_asset_flow(client: AsyncClient, db_session: AsyncSession):
    async def _get_uow_override():
        yield UnitOfWork(session=db_session)

    app.dependency_overrides[get_unit_of_work] = _get_uow_override
    try:
        pres = Presentation(title="C3 API Test", owner_id=TEST_USER_ID, slide_count=2)
        db_session.add(pres)
        await db_session.flush()

        repo = TopicVisualAssetRepository(db_session)
        pipeline = C3VisualPlanningPipeline(asset_repo=repo)
        plan = await pipeline.plan_presentation_visuals(
            presentation_id=str(pres.id),
            user_id=TEST_USER_ID,
            topics=_make_topics(),
        )
        asset = None
        for tp in plan.topic_plans:
            if tp.visual_needed and tp.specification:
                asset = await pipeline.generate_and_persist_visual(
                    plan=tp,
                    presentation_id=str(pres.id),
                    user_id=TEST_USER_ID,
                )
                if asset:
                    break
        assert asset is not None, "expected at least one generated visual"
        await db_session.commit()

        asset_id = asset.id

        # List
        res = await client.get(f"/api/v1/c3/visuals/presentation/{pres.public_id}")
        assert res.status_code == 200
        assert res.json()["data"]

        # Ready (player consumption)
        ready = await client.get(f"/api/v1/c3/visuals/presentation/{pres.public_id}/ready")
        assert ready.status_code == 200
        payload = ready.json()["data"][0]
        assert payload["svg_content"].startswith("<svg")
        assert payload["topic_title"]
        assert payload["purpose"]
        assert payload["learning_objective"]
        assert payload["specification"]
        assert payload["explanation"]
        assert any(
            expl["what_you_see"] for expl in [payload["explanation"]] if "what_you_see" in expl
        )
        assert payload["concepts"]
        assert all(
            any(cid.endswith(f":{c}") for cid in payload["concept_ids"])
            for c in payload["concepts"]
        )

        # Single get
        one = await client.get(f"/api/v1/c3/visuals/{asset_id}")
        assert one.status_code == 200
        assert one.json()["data"]["title"]

        # SVG inline
        svg = await client.get(f"/api/v1/c3/visuals/{asset_id}/svg")
        assert svg.status_code == 200
        assert svg.text.startswith("<svg")
        assert svg.headers["content-type"].startswith("image/svg+xml")

        # Download
        download = await client.get(f"/api/v1/c3/visuals/{asset_id}/download")
        assert download.status_code == 200
        assert "attachment" in download.headers["content-disposition"]

        # Soft delete
        deleted = await client.delete(f"/api/v1/c3/visuals/{asset_id}")
        assert deleted.status_code == 204
        await db_session.commit()

        after = await client.get(f"/api/v1/c3/visuals/{asset_id}")
        assert after.status_code == 404
    finally:
        app.dependency_overrides.pop(get_unit_of_work, None)


@pytest.mark.asyncio
async def test_c3_api_02_cross_user_ownership_denied(
    client: AsyncClient,
    db_session: AsyncSession,
):
    async def _get_uow_override():
        yield UnitOfWork(session=db_session)

    app.dependency_overrides[get_unit_of_work] = _get_uow_override
    try:
        pres = Presentation(title="C3 Other User", owner_id=OTHER_USER_ID, slide_count=2)
        db_session.add(pres)
        await db_session.flush()
        await db_session.commit()

        repo = TopicVisualAssetRepository(db_session)
        asset = await repo.create(
            presentation_id=pres.id,
            user_id=OTHER_USER_ID,
            topic_id="topic_x",
            topic_title="Topic X",
            visual_type="concept_map",
            status="ready",
            fingerprint="fp-x",
            asset_format="svg",
            asset_content="<svg><!-- other user svg --></svg>",
            title="Other User Visual",
            provenance="ai_explained",
        )
        await db_session.commit()
        asset_id = str(asset.id)

        # The signed-in test user must NOT see another user's asset.
        res = await client.get(f"/api/v1/c3/visuals/{asset_id}")
        assert res.status_code == 404

        svg = await client.get(f"/api/v1/c3/visuals/{asset_id}/svg")
        assert svg.status_code == 404

        dl = await client.get(f"/api/v1/c3/visuals/{asset_id}/download")
        assert dl.status_code == 404

        # Triggering generation for another user's presentation is also rejected.
        gen = await client.post(
            "/api/v1/c3/visuals/generate",
            json={"presentation_id": pres.public_id, "topic_id": "topic_x"},
        )
        assert gen.status_code == 404
    finally:
        app.dependency_overrides.pop(get_unit_of_work, None)


@pytest.mark.asyncio
async def test_c3_api_03_generation_trigger_dispatches(
    client: AsyncClient,
    db_session: AsyncSession,
):
    from unittest.mock import MagicMock, patch

    async def _get_uow_override():
        yield UnitOfWork(session=db_session)

    app.dependency_overrides[get_unit_of_work] = _get_uow_override
    try:
        pres = Presentation(title="C3 Trigger", owner_id=TEST_USER_ID, slide_count=1)
        db_session.add(pres)
        await db_session.flush()
        await db_session.commit()

        with patch(
            "app.workers.tasks.safe_dispatch",
            new=MagicMock(),
        ) as dispatch_mock:
            gen = await client.post(
                "/api/v1/c3/visuals/generate",
                json={"presentation_id": pres.public_id, "topic_id": "t1"},
            )
            assert gen.status_code == 202
            assert gen.json()["success"] is True
            assert dispatch_mock.called
    finally:
        app.dependency_overrides.pop(get_unit_of_work, None)


@pytest.mark.asyncio
async def test_c3_api_04_list_supports_status_and_topic_filters(
    client: AsyncClient,
    db_session: AsyncSession,
):
    async def _get_uow_override():
        yield UnitOfWork(session=db_session)

    app.dependency_overrides[get_unit_of_work] = _get_uow_override
    try:
        pres = Presentation(title="C3 Filters", owner_id=TEST_USER_ID, slide_count=1)
        db_session.add(pres)
        await db_session.flush()

        repo = TopicVisualAssetRepository(db_session)
        await repo.create(
            presentation_id=pres.id,
            user_id=TEST_USER_ID,
            topic_id="topic_a",
            topic_title="Topic A",
            visual_type="flowchart",
            status="ready",
            fingerprint="fp-a",
            asset_format="svg",
            asset_content="<svg></svg>",
            title="A",
            provenance="ai_explained",
        )
        await repo.create(
            presentation_id=pres.id,
            user_id=TEST_USER_ID,
            topic_id="topic_b",
            topic_title="Topic B",
            visual_type="concept_map",
            status="failed",
            fingerprint="fp-b",
            asset_format="svg",
            asset_content=None,
            title="B",
            provenance="ai_explained",
            error_message="render error",
        )
        await db_session.commit()

        res = await client.get(f"/api/v1/c3/visuals/presentation/{pres.public_id}?status=ready")
        assert res.status_code == 200
        assert all(a["status"] == "ready" for a in res.json()["data"])

        res2 = await client.get(
            f"/api/v1/c3/visuals/presentation/{pres.public_id}?topic_id=topic_b"
        )
        assert res2.status_code == 200
        assert [a["topic_title"] for a in res2.json()["data"]] == ["Topic B"]
    finally:
        app.dependency_overrides.pop(get_unit_of_work, None)
