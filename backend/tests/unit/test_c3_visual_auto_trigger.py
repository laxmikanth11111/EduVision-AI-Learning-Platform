"""Tests for the C3 auto-trigger wiring (C3.4).

Verifies that ``PresentationService._trigger_c3_visual_generation`` dispatches
the C3 generation task only after a succeeded C2 outline exists, and skips
cleanly when the outline is missing or the presentation has no owner.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.presentation import Presentation
from app.models.topic_outline import TopicOutline
from app.services.presentation_service import PresentationService
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
            }
        ],
    }
]


@pytest.mark.asyncio
async def test_c3_auto_trigger_04_dispatches_after_succeeded_outline(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    """After C2 outline succeeds, the auto-trigger dispatches the C3 task."""
    pres = Presentation(title="C3 Auto Trigger", owner_id=TEST_USER_ID, slide_count=3)
    db_session.add(pres)
    await db_session.flush()
    db_session.add(
        TopicOutline(
            presentation_id=pres.id,
            title="C3 Auto Trigger",
            status="succeeded",
            topics=VALID_TOPICS,
        )
    )
    await db_session.commit()

    dispatched: list[tuple[object, str, str]] = []
    from app.workers import tasks as worker_tasks

    def _capture(task: object, *args: object, **kwargs: object) -> None:
        dispatched.append((task, str(args[0]), kwargs.get("force_regenerate", "")))

    monkeypatch.setattr(worker_tasks, "safe_dispatch", _capture)

    from app.database.unit_of_work import UnitOfWork

    await PresentationService(UnitOfWork(session=db_session))._trigger_c3_visual_generation(
        pres.public_id
    )

    assert len(dispatched) == 1
    task, public_id, _force = dispatched[0]
    assert public_id == pres.public_id
    from app.workers.c3_visual_tasks import c3_generate_visuals_task

    assert task is c3_generate_visuals_task


@pytest.mark.asyncio
async def test_c3_auto_trigger_05_skips_when_no_outline(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    """Without a succeeded C2 outline, the trigger must not dispatch (no-op)."""
    pres = Presentation(title="C3 No Outline Trigger", owner_id=TEST_USER_ID, slide_count=1)
    db_session.add(pres)
    await db_session.commit()

    dispatched: list[tuple[object, ...]] = []
    from app.workers import tasks as worker_tasks

    monkeypatch.setattr(worker_tasks, "safe_dispatch", lambda *a, **k: dispatched.append(a))

    from app.database.unit_of_work import UnitOfWork

    await PresentationService(UnitOfWork(session=db_session))._trigger_c3_visual_generation(
        pres.public_id
    )

    assert dispatched == []


@pytest.mark.asyncio
async def test_c3_auto_trigger_06_skips_when_owner_missing(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    """Presentations without an owner never dispatch C3 generation."""
    pres = Presentation(title="C3 No Owner", owner_id=None, slide_count=1)
    db_session.add(pres)
    await db_session.commit()

    dispatched: list[tuple[object, ...]] = []
    from app.workers import tasks as worker_tasks

    monkeypatch.setattr(worker_tasks, "safe_dispatch", lambda *a, **k: dispatched.append(a))

    from app.database.unit_of_work import UnitOfWork

    await PresentationService(UnitOfWork(session=db_session))._trigger_c3_visual_generation(
        pres.public_id
    )

    assert dispatched == []
