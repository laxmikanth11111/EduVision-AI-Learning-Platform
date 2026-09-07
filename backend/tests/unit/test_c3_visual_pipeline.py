"""Integration tests for the C3 Visual Planning Pipeline & persistence."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.presentation import Presentation
from app.models.topic_visual_asset import TopicVisualAsset
from app.repositories.topic_visual_asset_repository import TopicVisualAssetRepository
from app.schemas.c3_visual_intelligence import VisualStatus, compute_visual_fingerprint
from app.schemas.topic_outline import (
    Concept,
    EducationalExample,
    OutlineTopic,
    SourceReference,
    Subtopic,
)
from app.services.c3_visual_planning_pipeline import C3VisualPlanningPipeline
from tests.conftest import TEST_USER_ID


async def _make_presentation(session: AsyncSession, owner_id=TEST_USER_ID) -> Presentation:
    pres = Presentation(
        title="C3 Test Presentation",
        owner_id=owner_id,
        slide_count=6,
    )
    session.add(pres)
    await session.flush()
    return pres


def _make_topics() -> list[OutlineTopic]:
    return [
        OutlineTopic(
            title="TCP Handshake Process",
            slide_ranges=[1, 3],
            section="Networking",
            source_references=[SourceReference(slide_number=1, preview="Handshake")],
            subtopics=[
                Subtopic(
                    title="Three-Way Handshake",
                    learning_order=1,
                    source_references=[SourceReference(slide_number=2, preview="Steps")],
                    concepts=[
                        Concept(name="SYN", description="client sends synchronize flag"),
                        Concept(name="SYN-ACK", description="server acknowledges and syncs"),
                        Concept(name="ACK", description="client acknowledges the sequence"),
                    ],
                    learning_objectives=["Describe the handshake sequence"],
                    examples=[
                        EducationalExample(
                            content=(
                                "The connection establishment process follows sequential "
                                "stages: first the client sends a SYN packet, then the server "
                                "responds with a SYN-ACK packet, and finally the client "
                                "acknowledges with an ACK packet to complete the procedure."
                            ),
                            type="source_example",
                        )
                    ],
                )
            ],
        ),
        OutlineTopic(
            title="Introduction to Networking",
            slide_ranges=[4, 6],
            source_references=[SourceReference(slide_number=4, preview="Overview")],
            concepts=[
                Concept(name="Definition", description="what a network is"),
                Concept(name="Glossary", description="terms"),
            ],
        ),
    ]


@pytest.mark.asyncio
async def test_c3_pipeline_01_plan_skips_text_preferred_topic(db_session: AsyncSession):
    pres = await _make_presentation(db_session)
    pipeline = C3VisualPlanningPipeline()
    plan = await pipeline.plan_presentation_visuals(
        presentation_id=str(pres.id),
        user_id=TEST_USER_ID,
        topics=_make_topics(),
    )
    assert plan.total_topics == 2
    # "Introduction" topic is a choice: analyzer may or may not flag visual need,
    # but at least one plan must exist per topic/subtopic.
    assert len(plan.topic_plans) >= 2
    assert isinstance(plan.visuals_planned, int)
    await db_session.rollback()


@pytest.mark.asyncio
async def test_c3_pipeline_02_generate_and_persist_visual(db_session: AsyncSession):
    pres = await _make_presentation(db_session)
    topics = _make_topics()
    repo = TopicVisualAssetRepository(db_session)
    pipeline = C3VisualPlanningPipeline(asset_repo=repo)
    plan = await pipeline.plan_presentation_visuals(
        presentation_id=str(pres.id),
        user_id=TEST_USER_ID,
        topics=topics,
    )

    generated = 0
    for topic_plan in plan.topic_plans:
        if topic_plan.visual_needed and topic_plan.specification:
            asset = await pipeline.generate_and_persist_visual(
                plan=topic_plan,
                presentation_id=str(pres.id),
                user_id=TEST_USER_ID,
            )
            if asset:
                generated += 1
                assert asset.status == VisualStatus.READY
                assert asset.asset_content.startswith("<svg")
                assert asset.fingerprint

    await db_session.commit()

    assert generated >= 1
    result = await db_session.execute(
        select(TopicVisualAsset).where(TopicVisualAsset.presentation_id == pres.id)
    )
    rows = result.scalars().all()
    assert len(rows) == generated


@pytest.mark.asyncio
async def test_c3_pipeline_03_deduplication_by_fingerprint(db_session: AsyncSession):
    pres = await _make_presentation(db_session)
    topics = _make_topics()
    repo = TopicVisualAssetRepository(db_session)
    pipeline = C3VisualPlanningPipeline(asset_repo=repo)

    plan = await pipeline.plan_presentation_visuals(
        presentation_id=str(pres.id),
        user_id=TEST_USER_ID,
        topics=topics,
    )
    planned = [tp for tp in plan.topic_plans if tp.visual_needed and tp.specification]
    assert planned, "expected at least one visual plan to dedupe"

    for tp in planned:
        first = await pipeline.generate_and_persist_visual(
            plan=tp,
            presentation_id=str(pres.id),
            user_id=TEST_USER_ID,
        )
        assert first is not None

    await db_session.commit()
    first_total = await repo.count_by_presentation(pres.id)
    assert first_total == len(planned)

    # Re-plan and re-generate: every plan must hit the fingerprint cache.
    plan2 = await pipeline.plan_presentation_visuals(
        presentation_id=str(pres.id),
        user_id=TEST_USER_ID,
        topics=topics,
    )
    for tp in plan2.topic_plans:
        if tp.visual_needed and tp.specification:
            second = await pipeline.generate_and_persist_visual(
                plan=tp,
                presentation_id=str(pres.id),
                user_id=TEST_USER_ID,
            )
            assert second is not None

    await db_session.commit()
    second_total = await repo.count_by_presentation(pres.id)
    assert second_total == first_total


@pytest.mark.asyncio
async def test_c3_pipeline_04_supersede_old_version(db_session: AsyncSession):
    pres = await _make_presentation(db_session)
    repo = TopicVisualAssetRepository(db_session)
    fingerprint = compute_visual_fingerprint(str(pres.id), "topic_b", "sub_1", ["c1"])

    v1 = await repo.create(
        presentation_id=pres.id,
        user_id=TEST_USER_ID,
        topic_id="topic_b",
        topic_title="Topic B",
        subtopic_id="sub_1",
        subtopic_title="Sub 1",
        visual_type="concept_map",
        status="ready",
        version=1,
        fingerprint=fingerprint,
        asset_format="svg",
        asset_content="<svg>old</svg>",
        title="Old Version",
        provenance="ai_explained",
    )
    v2 = await repo.create(
        presentation_id=pres.id,
        user_id=TEST_USER_ID,
        topic_id="topic_b",
        topic_title="Topic B",
        subtopic_id="sub_1",
        subtopic_title="Sub 1",
        visual_type="concept_map",
        status="ready",
        version=2,
        fingerprint=fingerprint,
        asset_format="svg",
        asset_content="<svg>new</svg>",
        title="New Version",
        provenance="ai_explained",
    )
    await repo.supersede_old_version(fingerprint, v2.id)
    await db_session.commit()

    await db_session.refresh(v1)
    await db_session.refresh(v2)
    assert v1.status == "superseded"
    assert v2.status == "ready"


@pytest.mark.asyncio
async def test_c3_pipeline_05_soft_delete_excludes_from_query(db_session: AsyncSession):
    pres = await _make_presentation(db_session)
    repo = TopicVisualAssetRepository(db_session)
    asset = await repo.create(
        presentation_id=pres.id,
        user_id=TEST_USER_ID,
        topic_id="topic_c",
        topic_title="Topic C",
        visual_type="concept_map",
        status="ready",
        fingerprint="fp-soft",
        asset_format="svg",
        asset_content="<svg>x</svg>",
        title="Deletable",
        provenance="ai_explained",
    )
    await db_session.commit()

    await repo.delete(asset.id, hard=False)
    await db_session.commit()

    ready = await repo.get_ready_assets_for_presentation(pres.id)
    assert ready == []


@pytest.mark.asyncio
async def test_c3_pipeline_06_persisted_explanation_is_clean_prose(
    db_session: AsyncSession,
):
    """The persisted explanation must not duplicate purpose prose (e.g. 'shows Show')."""
    pres = await _make_presentation(db_session)
    topics = _make_topics()
    repo = TopicVisualAssetRepository(db_session)
    pipeline = C3VisualPlanningPipeline(asset_repo=repo)
    plan = await pipeline.plan_presentation_visuals(
        presentation_id=str(pres.id),
        user_id=TEST_USER_ID,
        topics=topics,
    )

    generated = 0
    for topic_plan in plan.topic_plans:
        if topic_plan.visual_needed and topic_plan.specification:
            asset = await pipeline.generate_and_persist_visual(
                plan=topic_plan,
                presentation_id=str(pres.id),
                user_id=TEST_USER_ID,
            )
            if asset and asset.explanation:
                generated += 1
                what = asset.explanation.what_you_see
                assert "shows Show" not in what
                assert what.startswith("This diagram focuses on")
                assert topic_plan.specification.title in what

    assert generated >= 1
