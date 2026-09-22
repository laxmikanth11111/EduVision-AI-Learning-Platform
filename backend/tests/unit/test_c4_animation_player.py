"""C4.10 player linking — ready C4 animations are surfaced inside the player.

The lesson player state links each topic to the ready C4 animations generated
for that topic (matched by topic title), so the front-end can render the
self-contained animation package in the Animation Mode tab.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.unit_of_work import UnitOfWork
from app.models.generated_block import GeneratedBlock
from app.models.generated_lesson import GeneratedLesson
from app.models.generated_lesson_version import GeneratedLessonVersion
from app.models.presentation import Presentation
from app.models.topic_outline import TopicOutline
from app.repositories.topic_animation_asset_repository import (
    TopicAnimationAssetRepository,
)
from app.repositories.topic_visual_asset_repository import TopicVisualAssetRepository
from app.schemas.topic_outline import (
    Concept,
    EducationalExample,
    OutlineTopic,
    Subtopic,
)
from app.services.c3_visual_planning_pipeline import C3VisualPlanningPipeline
from app.services.c4_animation_planning_pipeline import C4AnimationPlanningPipeline
from app.services.lesson_player_service import LessonPlayerService
from tests.conftest import TEST_USER_ID

OUTLINE_TOPICS = [
    {
        "title": "TCP Handshake Process",
        "slide_ranges": [1, 2],
        "subtopics": [
            {
                "title": "Three-Way Handshake",
                "learning_order": 1,
                "concepts": [
                    {"name": "SYN", "description": "synchronize flag"},
                    {"name": "SYN-ACK", "description": "ack + sync"},
                    {"name": "ACK", "description": "acknowledge"},
                ],
                "examples": [
                    {
                        "content": (
                            "The connection establishment process proceeds through "
                            "sequential stages: the client first transmits a SYN packet, "
                            "then the server replies with a SYN-ACK packet, and finally "
                            "the client sends an ACK to complete the whole procedure."
                        ),
                        "type": "source_example",
                    }
                ],
            }
        ],
    },
    {
        "title": "Introduction",
        "slide_ranges": [3, 3],
        "concepts": [{"name": "Definition", "description": "what it is"}],
    },
]

ANIM_TOPIC = "TCP Handshake Process"
TEXT_ONLY_TOPIC = "Introduction"


async def _seed_lesson_and_animations(db_session: AsyncSession) -> GeneratedLesson:
    pres = Presentation(title="C4 Player Deck", owner_id=TEST_USER_ID, slide_count=3)
    db_session.add(pres)
    await db_session.flush()

    db_session.add(
        TopicOutline(
            presentation_id=pres.id,
            title="C4 Player Deck",
            status="succeeded",
            topics=OUTLINE_TOPICS,
        )
    )

    lesson = GeneratedLesson(
        presentation_id=pres.id,
        user_id=None,
        mode="slide",
        status="ready",
        title="C4 Player Lesson",
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
        title="C4 Player Lesson",
        summary="summary",
        language="en",
    )
    db_session.add(version)
    await db_session.flush()

    db_session.add(
        GeneratedBlock(
            lesson_version_id=version.id,
            block_type="heading",
            position=0,
            heading=ANIM_TOPIC,
            content="Body 0",
        )
    )
    db_session.add(
        GeneratedBlock(
            lesson_version_id=version.id,
            block_type="heading",
            position=1,
            heading=TEXT_ONLY_TOPIC,
            content="Body 1",
        )
    )
    await db_session.flush()

    topics = [
        OutlineTopic(
            title=od["title"],
            slide_ranges=od["slide_ranges"],
            subtopics=[
                Subtopic(
                    title=s["title"],
                    concepts=[
                        Concept(name=c["name"], description=c["description"]) for c in s["concepts"]
                    ],
                    examples=[
                        EducationalExample(content=e["content"], type=e["type"])
                        for e in s.get("examples", [])
                    ],
                )
                for s in od.get("subtopics", [])
            ],
            concepts=[
                Concept(name=c["name"], description=c["description"])
                for c in od.get("concepts", [])
            ],
        )
        for od in OUTLINE_TOPICS
    ]

    c3_repo = TopicVisualAssetRepository(db_session)
    c3 = C3VisualPlanningPipeline(asset_repo=c3_repo)
    c3_plan = await c3.plan_presentation_visuals(
        presentation_id=str(pres.id),
        user_id=TEST_USER_ID,
        topics=topics,
    )
    for tp in c3_plan.topic_plans:
        if tp.visual_needed and tp.specification:
            await c3.generate_and_persist_visual(
                plan=tp,
                presentation_id=str(pres.id),
                user_id=TEST_USER_ID,
            )

    anim_repo = TopicAnimationAssetRepository(db_session)
    c4 = C4AnimationPlanningPipeline(asset_repo=anim_repo, c3_repo=c3_repo)
    c4_plan = await c4.plan_presentation_animations(
        presentation_id=str(pres.id),
        user_id=TEST_USER_ID,
        topics=topics,
    )
    for tp in c4_plan.topic_plans:
        if tp.animation_needed and tp.specification:
            await c4.generate_and_persist_animation(
                plan=tp,
                presentation_id=str(pres.id),
                user_id=TEST_USER_ID,
            )
    await db_session.commit()
    return lesson


def _player(db_session: AsyncSession) -> LessonPlayerService:
    return LessonPlayerService(UnitOfWork(session=db_session))


@pytest.mark.asyncio
async def test_c4_player_01_state_links_ready_animations_to_topic(
    db_session: AsyncSession,
):
    lesson = await _seed_lesson_and_animations(db_session)

    state = await _player(db_session).get_state(lesson.public_id, owner_id=str(TEST_USER_ID))

    topic = next(t for t in state["topics"] if t["title"] == ANIM_TOPIC)
    assert topic["animations"], "expected a linked animation on the matching topic"

    anim = topic["animations"][0]
    assert anim["animation_id"]
    assert anim["animation_type"]
    assert anim["asset_format"] == "html"
    assert anim["package_content"].startswith("<!DOCTYPE html>")
    assert anim["specification"]
    assert anim["topic_title"] == ANIM_TOPIC
    assert anim["concepts"]
    assert anim["concept_ids"]
    assert "pedagogical_rationale" in anim

    text_only = next(t for t in state["topics"] if t["title"] == TEXT_ONLY_TOPIC)
    assert text_only["animations"] == []


@pytest.mark.asyncio
async def test_c4_player_02_start_also_surfaces_animations(db_session: AsyncSession):
    lesson = await _seed_lesson_and_animations(db_session)

    state = await _player(db_session).start(lesson.public_id, owner_id=str(TEST_USER_ID))

    topic = next(t for t in state["topics"] if t["title"] == ANIM_TOPIC)
    assert topic["animations"]
    assert topic["animations"][0]["package_content"].startswith("<!DOCTYPE html>")


@pytest.mark.asyncio
async def test_c4_player_03_animation_embeddable_via_html_endpoint(
    db_session: AsyncSession,
):
    lesson = await _seed_lesson_and_animations(db_session)

    from sqlalchemy import select

    from app.models.topic_animation_asset import TopicAnimationAsset

    state = await _player(db_session).get_state(lesson.public_id, owner_id=str(TEST_USER_ID))
    topic = next(t for t in state["topics"] if t["title"] == ANIM_TOPIC)
    anim = topic["animations"][0]

    row = (
        await db_session.execute(
            select(TopicAnimationAsset).where(TopicAnimationAsset.id == uuid.UUID(anim["asset_id"]))
        )
    ).scalar_one()
    assert row.public_id == anim["public_id"]
    assert row.package_content.startswith("<!DOCTYPE html>")
