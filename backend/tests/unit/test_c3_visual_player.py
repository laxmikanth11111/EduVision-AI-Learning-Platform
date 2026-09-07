"""C3.9 player linking — ready C3 visual assets are surfaced inside the player.

The lesson player state links each topic to the ready C3 visuals generated for
that topic (matched by topic title), so the front-end can render the visual
inline (``svg_content``) or lazily via the SVG endpoint.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.unit_of_work import UnitOfWork, get_unit_of_work
from app.main import app
from app.models.generated_block import GeneratedBlock
from app.models.generated_lesson import GeneratedLesson
from app.models.generated_lesson_version import GeneratedLessonVersion
from app.models.presentation import Presentation
from app.models.topic_outline import TopicOutline
from app.models.topic_visual_asset import TopicVisualAsset
from app.repositories.topic_visual_asset_repository import TopicVisualAssetRepository
from app.schemas.topic_outline import Concept, OutlineTopic, Subtopic
from app.services.c3_visual_planning_pipeline import C3VisualPlanningPipeline
from app.services.lesson_player_service import LessonPlayerService
from tests.conftest import TEST_USER_ID

OUTLINE_TOPICS = [
    {
        "title": "Three-Way Handshake",
        "slide_ranges": [1, 2],
        "subtopics": [
            {
                "title": "Connection Establishment",
                "learning_order": 1,
                "concepts": [
                    {"name": "SYN", "description": "synchronize flag"},
                    {"name": "SYN-ACK", "description": "ack + sync"},
                    {"name": "ACK", "description": "acknowledge"},
                    {"name": "Sequence", "description": "packet ordering"},
                    {"name": "Window", "description": "flow control"},
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

PLAYER_TOPIC = "Three-Way Handshake"
TEXT_ONLY_TOPIC = "Introduction"


async def _seed_lesson_and_visuals(db_session: AsyncSession) -> GeneratedLesson:
    pres = Presentation(title="C3 Player Deck", owner_id=TEST_USER_ID, slide_count=3)
    db_session.add(pres)
    await db_session.flush()

    outline = TopicOutline(
        presentation_id=pres.id,
        title="C3 Player Deck",
        status="succeeded",
        topics=OUTLINE_TOPICS,
    )
    db_session.add(outline)

    lesson = GeneratedLesson(
        presentation_id=pres.id,
        user_id=None,
        mode="slide",
        status="ready",
        title="C3 Player Lesson",
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
        title="C3 Player Lesson",
        summary="summary",
        language="en",
    )
    db_session.add(version)
    await db_session.flush()

    blocks = [
        GeneratedBlock(
            lesson_version_id=version.id,
            block_type="heading",
            position=0,
            heading=PLAYER_TOPIC,
            content="Body 0",
        ),
        GeneratedBlock(
            lesson_version_id=version.id,
            block_type="heading",
            position=1,
            heading=TEXT_ONLY_TOPIC,
            content="Body 1",
        ),
    ]
    for block in blocks:
        db_session.add(block)
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
    repo = TopicVisualAssetRepository(db_session)
    pipeline = C3VisualPlanningPipeline(asset_repo=repo)
    plan = await pipeline.plan_presentation_visuals(
        presentation_id=str(pres.id),
        user_id=TEST_USER_ID,
        topics=topics,
    )
    for topic_plan in plan.topic_plans:
        if topic_plan.visual_needed and topic_plan.specification:
            await pipeline.generate_and_persist_visual(
                plan=topic_plan,
                presentation_id=str(pres.id),
                user_id=TEST_USER_ID,
            )
    await db_session.commit()
    return lesson


def _player(db_session: AsyncSession) -> LessonPlayerService:
    return LessonPlayerService(UnitOfWork(session=db_session))


@pytest.mark.asyncio
async def test_c3_player_01_state_links_ready_visuals_to_topic(
    db_session: AsyncSession,
):
    lesson = await _seed_lesson_and_visuals(db_session)

    state = await _player(db_session).get_state(lesson.public_id, owner_id=str(TEST_USER_ID))

    topic = next(t for t in state["topics"] if t["title"] == PLAYER_TOPIC)
    assert topic["visuals"], "expected a linked visual on the matching topic"

    visual = topic["visuals"][0]
    assert visual["visual_id"]
    assert visual["visual_type"] == "flowchart" or visual["visual_type"]
    assert visual["asset_format"] == "svg"
    assert visual["svg_content"].startswith("<svg")
    assert visual["topic_title"] == PLAYER_TOPIC
    assert visual["concepts"]
    assert visual["concept_ids"]
    assert any(c == "SYN" for c in visual["concepts"])
    assert "purpose" in visual
    assert "learning_objective" in visual

    text_only = next(t for t in state["topics"] if t["title"] == TEXT_ONLY_TOPIC)
    assert text_only["visuals"] == []


@pytest.mark.asyncio
async def test_c3_player_02_start_also_surfaces_visuals(db_session: AsyncSession):
    lesson = await _seed_lesson_and_visuals(db_session)

    state = await _player(db_session).start(lesson.public_id, owner_id=str(TEST_USER_ID))

    topic = next(t for t in state["topics"] if t["title"] == PLAYER_TOPIC)
    assert topic["visuals"]
    assert topic["visuals"][0]["svg_content"].startswith("<svg")


@pytest.mark.asyncio
async def test_c3_player_03_visual_is_embeddable_via_svg_endpoint(
    client: AsyncClient,
    db_session: AsyncSession,
):
    async def _get_uow_override():
        yield UnitOfWork(session=db_session)

    app.dependency_overrides[get_unit_of_work] = _get_uow_override
    try:
        lesson = await _seed_lesson_and_visuals(db_session)

        res = await client.get(f"/api/v1/lessons/{lesson.public_id}/player")
        assert res.status_code == 200
        topics = res.json()["data"]["topics"]
        topic = next(t for t in topics if t["title"] == PLAYER_TOPIC)
        visual = topic["visuals"][0]
        assert visual["visual_id"]

        asset_row = (
            await db_session.execute(
                select(TopicVisualAsset).where(TopicVisualAsset.id == _to_uuid(visual["visual_id"]))
            )
        ).scalar_one()
        assert asset_row.public_id == visual["public_id"]

        svg = await client.get(f"/api/v1/c3/visuals/{visual['visual_id']}/svg")
        assert svg.status_code == 200
        assert svg.text.startswith("<svg")
        assert svg.headers["content-type"].startswith("image/svg+xml")
    finally:
        app.dependency_overrides.pop(get_unit_of_work, None)


def _to_uuid(value: str):
    import uuid

    return uuid.UUID(value)
