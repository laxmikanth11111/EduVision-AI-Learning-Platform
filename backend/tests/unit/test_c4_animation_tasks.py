"""Tests for the C4 async animation generation task core (`_generate_animations_async`)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.presentation import Presentation
from app.models.topic_animation_asset import TopicAnimationAsset
from app.models.topic_outline import TopicOutline
from app.repositories.topic_visual_asset_repository import TopicVisualAssetRepository
from app.schemas.topic_outline import (
    Concept,
    EducationalExample,
    OutlineTopic,
    SourceReference,
    Subtopic,
)
from app.services.c3_visual_planning_pipeline import C3VisualPlanningPipeline
from app.workers.c4_animation_tasks import _generate_animations_async
from tests.conftest import TEST_USER_ID


def _make_topics() -> list[OutlineTopic]:
    return [
        OutlineTopic(
            title="TCP Handshake Process",
            slide_ranges=[1, 3],
            source_references=[SourceReference(slide_number=1, preview="Handshake")],
            learning_objectives=["Explain the TCP three-way handshake sequence"],
            subtopics=[
                Subtopic(
                    title="Three-Way Handshake",
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
                                "The connection establishment process proceeds through "
                                "sequential stages: the client first transmits a SYN packet, "
                                "then the server replies with a SYN-ACK packet, and finally "
                                "the client sends an ACK to complete the whole procedure."
                            ),
                            type="source_example",
                        )
                    ],
                )
            ],
        )
    ]


async def _seed_c3_foundation(db_session: AsyncSession, pres: Presentation) -> None:
    """Create a ready C3 visual asset so the C4 worker has a foundation to animate."""
    repo = TopicVisualAssetRepository(db_session)
    pipeline = C3VisualPlanningPipeline(asset_repo=repo)
    plan = await pipeline.plan_presentation_visuals(
        presentation_id=str(pres.id),
        user_id=TEST_USER_ID,
        topics=_make_topics(),
    )
    for tp in plan.topic_plans:
        if tp.visual_needed and tp.specification:
            await pipeline.generate_and_persist_visual(
                plan=tp,
                presentation_id=str(pres.id),
                user_id=TEST_USER_ID,
            )
            break
    await db_session.commit()


@pytest.mark.asyncio
async def test_c4_task_01_generates_animations_from_c3_foundation(
    db_session: AsyncSession,
):
    pres = Presentation(title="C4 Task Deck", owner_id=TEST_USER_ID, slide_count=3)
    db_session.add(pres)
    await db_session.flush()
    db_session.add(
        TopicOutline(
            presentation_id=pres.id,
            title="C4 Task Deck",
            status="succeeded",
            topics=[t.model_dump(mode="json") for t in _make_topics()],
        )
    )
    await db_session.commit()

    await _seed_c3_foundation(db_session, pres)

    result = await _generate_animations_async(
        presentation_id=pres.public_id,
        user_id=TEST_USER_ID,
    )

    assert result["success"] is True
    assert result["animations_planned"] >= 1
    assert result["animations_failed"] == 0

    from sqlalchemy import func, select

    total = (
        await db_session.execute(
            select(func.count())
            .select_from(TopicAnimationAsset)
            .where(TopicAnimationAsset.presentation_id == pres.id)
        )
    ).scalar()
    assert total >= 1


@pytest.mark.asyncio
async def test_c4_task_02_missing_outline_returns_error(db_session: AsyncSession):
    pres = Presentation(title="C4 No Outline", owner_id=TEST_USER_ID, slide_count=1)
    db_session.add(pres)
    await db_session.commit()

    result = await _generate_animations_async(
        presentation_id=pres.public_id,
        user_id=TEST_USER_ID,
    )
    assert result["success"] is False


@pytest.mark.asyncio
async def test_c4_task_03_cross_user_is_rejected(db_session: AsyncSession):
    other = uuid.UUID("00000000-0000-0000-0000-000000000099")
    pres = Presentation(title="C4 Other Owner", owner_id=other, slide_count=1)
    db_session.add(pres)
    await db_session.commit()

    result = await _generate_animations_async(
        presentation_id=pres.public_id,
        user_id=TEST_USER_ID,
    )
    assert result["success"] is False
    assert result.get("error") == "Not owner"


@pytest.mark.asyncio
async def test_c4_task_04_no_c3_foundation_skips_cleanly(db_session: AsyncSession):
    pres = Presentation(title="C4 No C3", owner_id=TEST_USER_ID, slide_count=3)
    db_session.add(pres)
    await db_session.flush()
    db_session.add(
        TopicOutline(
            presentation_id=pres.id,
            title="C4 No C3",
            status="succeeded",
            topics=[t.model_dump(mode="json") for t in _make_topics()],
        )
    )
    await db_session.commit()

    result = await _generate_animations_async(
        presentation_id=pres.public_id,
        user_id=TEST_USER_ID,
    )
    assert result["success"] is True
    assert result["animations_generated"] == 0
