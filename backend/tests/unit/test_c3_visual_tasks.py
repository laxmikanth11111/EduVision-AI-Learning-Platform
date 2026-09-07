"""Tests for the C3 async visual generation task core (`_generate_visuals_async`)."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.presentation import Presentation
from app.models.topic_outline import TopicOutline
from app.models.topic_visual_asset import TopicVisualAsset
from app.workers.c3_visual_tasks import _generate_visuals_async
from tests.conftest import TEST_USER_ID

VALID_TOPICS = [
    {
        "title": "TCP Handshake Process",
        "slide_ranges": [1, 3],
        "section": "Networking",
        "source_references": [{"slide_number": 1, "preview": "Handshake"}],
        "subtopics": [
            {
                "title": "Three-Way Handshake",
                "learning_order": 1,
                "source_references": [{"slide_number": 2, "preview": "Exchange"}],
                "concepts": [
                    {"name": "SYN", "description": "client sends synchronize flag"},
                    {"name": "SYN-ACK", "description": "server accepts and syncs"},
                    {"name": "ACK", "description": "client confirms the sequence"},
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
    }
]


@pytest.mark.asyncio
async def test_c3_task_01_generates_visuals_from_outline(db_session: AsyncSession):
    pres = Presentation(title="C3 Task Deck", owner_id=TEST_USER_ID, slide_count=3)
    db_session.add(pres)
    await db_session.flush()
    outline = TopicOutline(
        presentation_id=pres.id,
        title="C3 Task Deck",
        status="succeeded",
        topics=VALID_TOPICS,
    )
    db_session.add(outline)
    await db_session.commit()

    result = await _generate_visuals_async(
        presentation_id=pres.public_id,
        user_id=TEST_USER_ID,
    )

    assert result["success"] is True
    assert result["visuals_generated"] >= 1
    assert result["visuals_failed"] == 0


@pytest.mark.asyncio
async def test_c3_task_02_missing_outline_returns_error(db_session: AsyncSession):
    pres = Presentation(title="C3 No Outline", owner_id=TEST_USER_ID, slide_count=1)
    db_session.add(pres)
    await db_session.commit()

    result = await _generate_visuals_async(
        presentation_id=pres.public_id,
        user_id=TEST_USER_ID,
    )
    assert result["success"] is False


@pytest.mark.asyncio
async def test_c3_task_03_cross_user_is_rejected(db_session: AsyncSession):
    other = "00000000-0000-0000-0000-000000000099"
    import uuid as _uuid

    pres = Presentation(title="C3 Other Owner", owner_id=_uuid.UUID(other), slide_count=1)
    db_session.add(pres)
    await db_session.commit()

    result = await _generate_visuals_async(
        presentation_id=pres.public_id,
        user_id=TEST_USER_ID,
    )
    assert result["success"] is False
    assert result.get("error") == "Not owner"


@pytest.mark.asyncio
async def test_c3_task_04_rerun_is_idempotent(db_session: AsyncSession):
    pres = Presentation(title="C3 Idempotent", owner_id=TEST_USER_ID, slide_count=3)
    db_session.add(pres)
    await db_session.flush()
    db_session.add(
        TopicOutline(
            presentation_id=pres.id,
            title="C3 Idempotent",
            status="succeeded",
            topics=VALID_TOPICS,
        )
    )
    await db_session.commit()

    r1 = await _generate_visuals_async(presentation_id=pres.public_id, user_id=TEST_USER_ID)
    assert r1["visuals_generated"] == 1

    r2 = await _generate_visuals_async(presentation_id=pres.public_id, user_id=TEST_USER_ID)
    assert r2["visuals_generated"] == 1

    from sqlalchemy import func, select

    total = (
        await db_session.execute(
            select(func.count())
            .select_from(TopicVisualAsset)
            .where(TopicVisualAsset.presentation_id == pres.id)
        )
    ).scalar()
    assert total == 1
