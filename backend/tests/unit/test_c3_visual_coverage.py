"""C3.3 topic/subtopic coverage tests for the C3 visual planning pipeline.

Every topic/subtopic in a C2 outline must be considered by the planner
(a visual or an explicit need-based skip), and every visual-worthy unit
must persist an asset that maps ITS concepts individually.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.presentation import Presentation
from app.models.topic_outline import TopicOutline
from app.models.topic_visual_asset import TopicVisualAsset
from app.schemas.topic_outline import Concept, OutlineTopic, Subtopic
from app.services.c3_visual_need_analyzer import analyze_visual_need
from app.services.c3_visual_planning_pipeline import (
    MAX_VISUALS_PER_PRESENTATION,
    C3VisualPlanningPipeline,
)
from app.workers.c3_visual_tasks import _generate_visuals_async
from tests.conftest import TEST_USER_ID

PRES_TITLE = "C3 Coverage Deck"

VISUAL_CONCEPT_NAMES = ["SYN", "SYN-ACK", "ACK", "Sequence", "Window"]
TEXT_PREFERRED_CONCEPT_NAMES = ["Layers", "Encapsulation", "Framing", "MTU", "Header"]

VISUAL_EXAMPLE = {
    "content": (
        "The connection establishment procedure runs through clear stages: "
        "the client first transmits a SYN packet, then the server replies with "
        "a SYN-ACK packet, and finally the client sends an ACK to complete the "
        "whole sequential handshake process. Each step depends on the previous."
    ),
    "type": "source_example",
}


def _concept(name: str) -> Concept:
    return Concept(
        name=name,
        description=f"{name} participates in the sequential process stages of communication.",
    )


def _worthwhile_subtopic(title: str, order: int = 1) -> Subtopic:
    return Subtopic(
        title=title,
        learning_order=order,
        source_references=[{"slide_number": order, "preview": title}],
        concepts=[_concept(n) for n in VISUAL_CONCEPT_NAMES],
        examples=[dict(VISUAL_EXAMPLE)],
    )


def _text_preferred_subtopic(title: str, order: int = 1) -> Subtopic:
    return Subtopic(
        title=title,
        learning_order=order,
        source_references=[{"slide_number": order, "preview": title}],
        concepts=[_concept(n) for n in TEXT_PREFERRED_CONCEPT_NAMES],
    )


def _outline_topics() -> list[OutlineTopic]:
    return [
        OutlineTopic(
            title="TCP Handshake Process",
            slide_ranges=[1, 4],
            concepts=[_concept(n) for n in VISUAL_CONCEPT_NAMES],
            subtopics=[
                _worthwhile_subtopic("Three-Way Handshake Start"),
                _worthwhile_subtopic("Connection Close Sequence"),
            ],
        ),
        OutlineTopic(
            title="Protocol Stack Layers",
            slide_ranges=[5, 6],
            concepts=[_concept(n) for n in TEXT_PREFERRED_CONCEPT_NAMES],
            subtopics=[
                _text_preferred_subtopic("Definition of Network Layers"),
            ],
        ),
        OutlineTopic(
            title="Network Architecture",
            slide_ranges=[7, 8],
            concepts=[_concept(n) for n in VISUAL_CONCEPT_NAMES],
        ),
    ]


@pytest.mark.asyncio
async def test_c3_coverage_01_planner_visits_every_topic_and_subtopic():
    topics = _outline_topics()
    plan = await C3VisualPlanningPipeline().plan_presentation_visuals(
        presentation_id="pres-coverage-01",
        user_id=TEST_USER_ID,
        topics=topics,
    )

    assert plan.total_topics == 3
    assert plan.total_subtopics == 4
    assert len(plan.topic_plans) == 4
    assert plan.visuals_planned + plan.visuals_skipped == plan.total_subtopics

    by_topic = {p.topic_id: p for p in plan.topic_plans}
    assert "TCP Handshake Process" in by_topic
    assert "Network Architecture" in by_topic


@pytest.mark.asyncio
async def test_c3_coverage_02_every_subtopic_maps_concepts_into_asset(db_session: AsyncSession):
    pres = Presentation(title=PRES_TITLE, owner_id=TEST_USER_ID, slide_count=8)
    db_session.add(pres)
    await db_session.flush()
    db_session.add(
        TopicOutline(
            presentation_id=pres.id,
            title=PRES_TITLE,
            status="succeeded",
            topics=[t.model_dump(mode="json") for t in _outline_topics()],
        )
    )
    await db_session.commit()

    result = await _generate_visuals_async(
        presentation_id=pres.public_id,
        user_id=TEST_USER_ID,
    )
    assert result["success"] is True
    assert result["visuals_generated"] >= 2
    assert result["visuals_failed"] == 0

    rows = (
        (
            await db_session.execute(
                select(TopicVisualAsset).where(TopicVisualAsset.presentation_id == pres.id)
            )
        )
        .scalars()
        .all()
    )
    assets_by_subtopic = {a.subtopic_id: a for a in rows if a.subtopic_id}
    assert set(assets_by_subtopic) == {
        "Three-Way Handshake Start",
        "Connection Close Sequence",
    }

    handshake = assets_by_subtopic["Three-Way Handshake Start"]
    assert handshake.topic_id == "TCP Handshake Process"
    assert handshake.topic_title == "TCP Handshake Process"
    assert handshake.concept_ids == [
        f"TCP Handshake Process:{name}" for name in VISUAL_CONCEPT_NAMES
    ]
    assert handshake.status == "ready"
    assert handshake.asset_content.strip().startswith("<svg")
    assert handshake.fingerprint


@pytest.mark.asyncio
async def test_c3_coverage_03_topic_without_subtopics_gets_topic_level_visual():
    topics = _outline_topics()
    pipeline = C3VisualPlanningPipeline()
    plan = await pipeline.plan_presentation_visuals(
        presentation_id="pres-coverage-03",
        user_id=TEST_USER_ID,
        topics=topics,
    )

    topic_plan = next(p for p in plan.topic_plans if p.topic_id == "Network Architecture")
    assert topic_plan.visual_needed is True
    assert topic_plan.subtopic_id is None
    assert topic_plan.subtopic_title is None
    assert topic_plan.concept_ids == [
        f"Network Architecture:{name}" for name in VISUAL_CONCEPT_NAMES
    ]

    asset = await pipeline.generate_and_persist_visual(
        plan=topic_plan,
        presentation_id=str(uuid.uuid4()),
        user_id=TEST_USER_ID,
    )
    assert asset is not None
    assert asset.topic_id == "Network Architecture"
    assert asset.subtopic_id is None
    assert asset.asset_content.strip().startswith("<svg")


@pytest.mark.asyncio
async def test_c3_coverage_04_need_skip_produces_no_asset(db_session: AsyncSession):
    topics = _outline_topics()
    plan = await C3VisualPlanningPipeline().plan_presentation_visuals(
        presentation_id="pres-coverage-04",
        user_id=TEST_USER_ID,
        topics=topics,
    )

    skipped = [p for p in plan.topic_plans if not p.visual_needed]
    assert len(skipped) == 1
    assert skipped[0].subtopic_id == "Definition of Network Layers"
    assert skipped[0].status.value == "planned"

    pres = Presentation(title=PRES_TITLE, owner_id=TEST_USER_ID, slide_count=8)
    db_session.add(pres)
    await db_session.flush()
    db_session.add(
        TopicOutline(
            presentation_id=pres.id,
            title=PRES_TITLE,
            status="succeeded",
            topics=[t.model_dump(mode="json") for t in topics],
        )
    )
    await db_session.commit()

    result = await _generate_visuals_async(
        presentation_id=pres.public_id,
        user_id=TEST_USER_ID,
    )
    assert result["visuals_generated"] >= 2

    skipped_ids = set()
    all_rows = (
        (
            await db_session.execute(
                select(TopicVisualAsset).where(TopicVisualAsset.presentation_id == pres.id)
            )
        )
        .scalars()
        .all()
    )
    for asset in all_rows:
        assert asset.subtopic_id != "Definition of Network Layers"
    skipped_ids = {a.subtopic_id for a in all_rows}
    assert "Definition of Network Layers" not in skipped_ids


@pytest.mark.asyncio
async def test_c3_coverage_05_worst_case_subtopic_units_stay_bounded():
    topics = [
        OutlineTopic(
            title=f"Topic {i:02d}",
            slide_ranges=[i + 1, i + 1],
            subtopics=[_worthwhile_subtopic(f"Subtopic {i:02d}")],
        )
        for i in range(MAX_VISUALS_PER_PRESENTATION + 10)
    ]
    plan = await C3VisualPlanningPipeline().plan_presentation_visuals(
        presentation_id="pres-coverage-05",
        user_id=TEST_USER_ID,
        topics=topics,
    )
    assert plan.visuals_planned == MAX_VISUALS_PER_PRESENTATION
    assert plan.total_subtopics == MAX_VISUALS_PER_PRESENTATION + 10
    assert plan.visuals_skipped == 0


@pytest.mark.asyncio
async def test_c3_coverage_06_topic_level_units_stay_bounded_too():
    topics = [
        OutlineTopic(
            title=f"Topic {i:02d}",
            slide_ranges=[i + 1, i + 1],
            concepts=[_concept(n) for n in VISUAL_CONCEPT_NAMES],
        )
        for i in range(MAX_VISUALS_PER_PRESENTATION + 10)
    ]
    plan = await C3VisualPlanningPipeline().plan_presentation_visuals(
        presentation_id="pres-coverage-06",
        user_id=TEST_USER_ID,
        topics=topics,
    )
    assert plan.visuals_planned == MAX_VISUALS_PER_PRESENTATION
    assert plan.total_subtopics == MAX_VISUALS_PER_PRESENTATION + 10
    assert len(plan.topic_plans) == MAX_VISUALS_PER_PRESENTATION


@pytest.mark.asyncio
async def test_c3_coverage_07_need_analysis_explains_coverage_decisions():
    for topic in _outline_topics():
        for subtopic in topic.subtopics:
            decision = analyze_visual_need(
                topic_title=topic.title,
                topic_content=f"{subtopic.title} "
                + " ".join(c.description for c in subtopic.concepts),
                subtopic_title=subtopic.title,
                subtopic_content=f"{subtopic.title} "
                + " ".join(c.description for c in subtopic.concepts),
                concepts=[
                    {"name": c.name, "description": c.description} for c in subtopic.concepts
                ],
            )
            if "Definition" in subtopic.title:
                assert decision.visual_needed is False
                assert "text-preferred" in decision.skip_reason
            else:
                assert decision.visual_needed is True
                assert decision.reason
