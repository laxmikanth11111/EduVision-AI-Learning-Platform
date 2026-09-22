"""Integration tests for the C4 Animation API — ownership, lifecycle, and player delivery."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.unit_of_work import UnitOfWork, get_unit_of_work
from app.main import app
from app.models.presentation import Presentation
from app.repositories.topic_animation_asset_repository import (
    TopicAnimationAssetRepository,
)
from app.schemas.c3_visual_intelligence import C3VisualType
from app.schemas.topic_outline import (
    Concept,
    EducationalExample,
    OutlineTopic,
    SourceReference,
    Subtopic,
)
from tests.conftest import TEST_USER_ID

OTHER_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000099")


def _make_topics() -> list[OutlineTopic]:
    return [
        OutlineTopic(
            title="Network Classification",
            slide_ranges=[1, 2],
            source_references=[SourceReference(slide_number=1, preview="Classification")],
            learning_objectives=["Classify networks by scale and role"],
            subtopics=[
                Subtopic(
                    title="Network Scale Types",
                    learning_order=1,
                    source_references=[SourceReference(slide_number=2, preview="Scale types")],
                    concepts=[
                        Concept(name="PAN", description="personal area"),
                        Concept(name="LAN", description="local area"),
                        Concept(name="WAN", description="wide area"),
                    ],
                    examples=[
                        EducationalExample(
                            content=(
                                "Computer networks are organized hierarchically by scope. "
                                "The smallest is a PAN, next comes a LAN connecting devices "
                                "in one building, and the broadest is a WAN spanning "
                                "geographic regions between distant sites."
                            ),
                            type="source_example",
                        )
                    ],
                )
            ],
        )
    ]


async def _seed_animation(
    db_session: AsyncSession,
    pres: Presentation,
) -> str:
    from app.schemas.c3_visual_intelligence import VisualEdge, VisualNode
    from app.schemas.c4_animation_intelligence import (
        AnimationInteraction,
        AnimationScene,
        AnimationSpecification,
        AnimationStep,
        AnimationStepKind,
        C4AnimationType,
    )

    repo = TopicAnimationAssetRepository(db_session)
    topic = _make_topics()[0]
    subtopic = topic.subtopics[0]

    nodes = [
        VisualNode(id="n1", label="PAN"),
        VisualNode(id="n2", label="LAN"),
        VisualNode(id="n3", label="WAN"),
    ]
    edges = [
        VisualEdge(id="e1", source_id="n1", target_id="n2"),
        VisualEdge(id="e2", source_id="n2", target_id="n3"),
    ]
    scenes = [
        AnimationScene(
            scene_index=1,
            title="Classify by scale",
            steps=[
                AnimationStep(
                    step_index=1,
                    kind=AnimationStepKind.REVEAL,
                    node_ids=["n1"],
                    caption="Smallest scope",
                ),
                AnimationStep(
                    step_index=2, kind=AnimationStepKind.REVEAL, node_ids=["n2"], caption="Local"
                ),
                AnimationStep(
                    step_index=3, kind=AnimationStepKind.REVEAL, node_ids=["n3"], caption="Broadest"
                ),
                AnimationStep(
                    step_index=4,
                    kind=AnimationStepKind.HIGHLIGHT,
                    node_ids=["n2"],
                    caption="LAN focus",
                ),
            ],
        )
    ]
    interactions = [
        AnimationInteraction(
            interaction_index=1,
            kind="self_check",
            anchor_step_index=2,
            prompt="Which scope is local?",
            answer="LAN",
            guide_hint="Think building",
        )
    ]
    spec = AnimationSpecification(
        animation_type=C4AnimationType.PROCESS_SEQUENCE,
        title=f"Learn: {topic.title}",
        purpose="Classify networks",
        learning_objective="Classify networks by scale",
        base_visual_type=C3VisualType.HIERARCHY,
        source_visual_id="c3a_test",
        nodes=nodes,
        edges=edges,
        scenes=scenes,
        interactions=interactions,
        pedagogical_rationale="Ordering cannot be shown statically",
        concept_ids=[f"{topic.title}:{c.name}" for c in subtopic.concepts],
        source_references=[
            {"slide_number": r.slide_number, "preview": r.preview}
            for r in subtopic.source_references
        ],
    )
    asset = await repo.create(
        presentation_id=pres.id,
        user_id=TEST_USER_ID,
        topic_id=topic.title,
        topic_title=topic.title,
        subtopic_id=subtopic.title,
        subtopic_title=subtopic.title,
        animation_type=spec.animation_type.value,
        status="ready",
        version=1,
        fingerprint=f"fp-{uuid.uuid4()}",
        asset_format="html",
        package_content=(
            '<html><body><svg id="c4-svg"></svg>'
            '<div id="c4-hud"></div><script>const payload='
            f'{{"animationType":"{spec.animation_type.value}"'
            ',"scenes":[],"starts":[]};</script></body></html>'
        ),
        title=spec.title,
        purpose=spec.purpose,
        learning_objective=spec.learning_objective,
        provenance="ai_explained",
        confidence=0.95,
        specification=spec.model_dump(mode="json"),
        explanation={"what_you_see": "hi", "why_it_matters": "ok"},
        source_references=[
            {"slide_number": r.slide_number, "preview": r.preview}
            for r in subtopic.source_references
        ],
        concept_ids=[f"{topic.title}:{c.name}" for c in subtopic.concepts],
    )
    await db_session.commit()
    return str(asset.id)


@pytest.mark.asyncio
async def test_c4_api_01_asset_flow(client: AsyncClient, db_session: AsyncSession):
    async def _get_uow_override():
        yield UnitOfWork(session=db_session)

    app.dependency_overrides[get_unit_of_work] = _get_uow_override
    try:
        pres = Presentation(title="C4 API Test", owner_id=TEST_USER_ID, slide_count=2)
        db_session.add(pres)
        await db_session.flush()
        asset_id = await _seed_animation(db_session, pres)

        # List all
        res = await client.get(f"/api/v1/c4/animations/presentation/{pres.public_id}")
        assert res.status_code == 200
        assert res.json()["data"]
        assert res.json()["pagination"]["total"] == 1

        # By topic
        by_topic = await client.get(
            f"/api/v1/c4/animations/presentation/{pres.public_id}/topic/Network Classification"
        )
        assert by_topic.status_code == 200
        assert by_topic.json()["data"]

        # Ready (player consumption)
        ready = await client.get(f"/api/v1/c4/animations/presentation/{pres.public_id}/ready")
        assert ready.status_code == 200
        payload = ready.json()["data"][0]
        assert payload["asset_id"]
        assert payload["animation_type"]
        assert payload["topic_title"]
        assert payload["specification"]
        assert payload["package_content"].startswith("<html")
        assert payload["concepts"]
        assert all(
            any(cid.endswith(f":{c}") for cid in payload["concept_ids"])
            for c in payload["concepts"]
        )

        # Single get
        one = await client.get(f"/api/v1/c4/animations/{asset_id}")
        assert one.status_code == 200
        assert one.json()["data"]["title"]

        # HTML inline
        html = await client.get(f"/api/v1/c4/animations/{asset_id}/html")
        assert html.status_code == 200
        assert html.text.startswith("<html")
        assert html.headers["content-type"].startswith("text/html")

        # Soft delete
        deleted = await client.delete(f"/api/v1/c4/animations/{asset_id}")
        assert deleted.status_code == 204
        await db_session.commit()

        after = await client.get(f"/api/v1/c4/animations/{asset_id}")
        assert after.status_code == 404
    finally:
        app.dependency_overrides.pop(get_unit_of_work, None)


@pytest.mark.asyncio
async def test_c4_api_02_cross_user_ownership_denied(
    client: AsyncClient,
    db_session: AsyncSession,
):
    async def _get_uow_override():
        yield UnitOfWork(session=db_session)

    app.dependency_overrides[get_unit_of_work] = _get_uow_override
    try:
        pres = Presentation(title="C4 Other User", owner_id=OTHER_USER_ID, slide_count=2)
        db_session.add(pres)
        await db_session.flush()
        await db_session.commit()

        repo = TopicAnimationAssetRepository(db_session)
        asset = await repo.create(
            presentation_id=pres.id,
            user_id=OTHER_USER_ID,
            topic_id="topic_x",
            topic_title="Topic X",
            animation_type="process_sequence",
            status="ready",
            version=1,
            fingerprint="fp-x",
            asset_format="html",
            package_content="<html></html>",
            title="Other User Animation",
            provenance="ai_explained",
        )
        await db_session.commit()
        asset_id = str(asset.id)

        res = await client.get(f"/api/v1/c4/animations/{asset_id}")
        assert res.status_code == 404

        html = await client.get(f"/api/v1/c4/animations/{asset_id}/html")
        assert html.status_code == 404

        gen = await client.post(
            "/api/v1/c4/animations/generate",
            json={"presentation_id": pres.public_id, "topic_id": "t"},
        )
        assert gen.status_code == 404
    finally:
        app.dependency_overrides.pop(get_unit_of_work, None)


@pytest.mark.asyncio
async def test_c4_api_05_download_export_attachment(
    client: AsyncClient,
    db_session: AsyncSession,
):
    async def _get_uow_override():
        yield UnitOfWork(session=db_session)

    app.dependency_overrides[get_unit_of_work] = _get_uow_override
    try:
        pres = Presentation(title="C4 Download", owner_id=TEST_USER_ID, slide_count=2)
        db_session.add(pres)
        await db_session.flush()
        asset_id = await _seed_animation(db_session, pres)

        res = await client.get(f"/api/v1/c4/animations/{asset_id}/download")
        assert res.status_code == 200
        assert res.text.startswith("<html")
        assert res.headers["content-type"].startswith("text/html")
        assert res.headers["content-disposition"].startswith("attachment")
        assert 'filename="Learn_Network_Classification.html"' in res.headers[
            "content-disposition"
        ]
        assert res.headers["x-content-type-options"] == "nosniff"
        assert res.headers["cache-control"] == "private, no-store"
    finally:
        app.dependency_overrides.pop(get_unit_of_work, None)


@pytest.mark.asyncio
async def test_c4_api_06_download_requires_ready_and_ownership(
    client: AsyncClient,
    db_session: AsyncSession,
):
    async def _get_uow_override():
        yield UnitOfWork(session=db_session)

    app.dependency_overrides[get_unit_of_work] = _get_uow_override
    try:
        owner_pres = Presentation(title="C4 Owner", owner_id=TEST_USER_ID, slide_count=1)
        other_pres = Presentation(title="C4 Foreign", owner_id=OTHER_USER_ID, slide_count=1)
        db_session.add_all([owner_pres, other_pres])
        await db_session.flush()

        repo = TopicAnimationAssetRepository(db_session)
        failed = await repo.create(
            presentation_id=owner_pres.id,
            user_id=TEST_USER_ID,
            topic_id="topic_x",
            topic_title="Topic X",
            animation_type="process_sequence",
            status="failed",
            version=1,
            fingerprint="fp-failed",
            asset_format="html",
            package_content=None,
            title="Broken Asset",
            provenance="ai_explained",
            error_message="render error",
        )
        foreign = await repo.create(
            presentation_id=other_pres.id,
            user_id=OTHER_USER_ID,
            topic_id="topic_y",
            topic_title="Topic Y",
            animation_type="process_sequence",
            status="ready",
            version=1,
            fingerprint="fp-foreign",
            asset_format="html",
            package_content="<html></html>",
            title="Foreign Asset",
            provenance="ai_explained",
        )
        await db_session.commit()

        not_ready = await client.get(f"/api/v1/c4/animations/{failed.id}/download")
        assert not_ready.status_code == 404

        foreign_dl = await client.get(f"/api/v1/c4/animations/{foreign.id}/download")
        assert foreign_dl.status_code == 404
        assert foreign_dl.json()["error"]
    finally:
        app.dependency_overrides.pop(get_unit_of_work, None)


@pytest.mark.asyncio
async def test_c4_api_03_generation_trigger_dispatches(
    client: AsyncClient,
    db_session: AsyncSession,
):
    from unittest.mock import MagicMock, patch

    async def _get_uow_override():
        yield UnitOfWork(session=db_session)

    app.dependency_overrides[get_unit_of_work] = _get_uow_override
    try:
        pres = Presentation(title="C4 Trigger", owner_id=TEST_USER_ID, slide_count=1)
        db_session.add(pres)
        await db_session.flush()
        await db_session.commit()

        with patch("app.workers.c4_animation_tasks.c4_generate_animations_task") as task_mock:
            dispatch_patch = patch("app.workers.tasks.safe_dispatch", new=MagicMock())
            with dispatch_patch as dispatch_mock:
                gen = await client.post(
                    "/api/v1/c4/animations/generate",
                    json={"presentation_id": pres.public_id, "topic_id": "t1"},
                )
                assert gen.status_code == 202
                assert gen.json()["success"] is True
                assert dispatch_mock.called
                assert task_mock.accessed  # pragma: no cover - ensures import resolves
    finally:
        app.dependency_overrides.pop(get_unit_of_work, None)


@pytest.mark.asyncio
async def test_c4_api_04_list_supports_status_and_topic_filters(
    client: AsyncClient,
    db_session: AsyncSession,
):
    async def _get_uow_override():
        yield UnitOfWork(session=db_session)

    app.dependency_overrides[get_unit_of_work] = _get_uow_override
    try:
        pres = Presentation(title="C4 Filters", owner_id=TEST_USER_ID, slide_count=1)
        db_session.add(pres)
        await db_session.flush()

        repo = TopicAnimationAssetRepository(db_session)
        await repo.create(
            presentation_id=pres.id,
            user_id=TEST_USER_ID,
            topic_id="topic_a",
            topic_title="Topic A",
            animation_type="process_sequence",
            status="ready",
            version=1,
            fingerprint="fp-a",
            asset_format="html",
            package_content="<html></html>",
            title="A",
            provenance="ai_explained",
        )
        await repo.create(
            presentation_id=pres.id,
            user_id=TEST_USER_ID,
            topic_id="topic_b",
            topic_title="Topic B",
            animation_type="network_flow",
            status="failed",
            version=1,
            fingerprint="fp-b",
            asset_format="html",
            package_content=None,
            title="B",
            provenance="ai_explained",
            error_message="render error",
        )
        await db_session.commit()

        res = await client.get(f"/api/v1/c4/animations/presentation/{pres.public_id}?status=ready")
        assert res.status_code == 200
        assert all(a["status"] == "ready" for a in res.json()["data"])

        res2 = await client.get(
            f"/api/v1/c4/animations/presentation/{pres.public_id}?topic_id=topic_b"
        )
        assert res2.status_code == 200
        assert [a["topic_title"] for a in res2.json()["data"]] == ["Topic B"]
    finally:
        app.dependency_overrides.pop(get_unit_of_work, None)
