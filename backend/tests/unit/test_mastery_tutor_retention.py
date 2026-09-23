"""P9 Mastery Tutor retention enforcement tests (F3).

The ``TUTOR_SESSION_IDLE_DAYS`` / ``TUTOR_CONVERSATION_CLEANUP_DAYS`` settings
previously existed but were never enforced, so ``tutor_sessions`` and
``tutor_messages`` could grow without bound. These tests prove the bounded,
on-read cleanup in ``MasteryTutorService.enforce_retention``:

* idle ``active`` sessions older than ``TUTOR_SESSION_IDLE_DAYS`` are archived,
* conversations older than ``TUTOR_CONVERSATION_CLEANUP_DAYS`` are soft-deleted
  and their message rows hard-deleted (the storage-growth bound),
* fresh records are left completely untouched.

Everything is driven by a deterministic ``now`` argument and direct ORM seeding
with back-dated ``updated_at`` values; no real AI is called.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.unit_of_work import UnitOfWork
from app.models.tutor_conversation import TutorConversation
from app.models.tutor_message import TutorMessage
from app.models.tutor_session import TutorSession
from app.services.educational_memory_service import educational_memory_service
from app.services.mastery_tutor_service import MasteryTutorService
from shared.constants import TutorConversationStatus, TutorSessionStatus
from tests.learner_progress_helpers import seed_user


@pytest.fixture(autouse=True)
def _reset_memory_cache() -> None:
    educational_memory_service._memories.clear()  # noqa: SLF001


@pytest.fixture(autouse=True)
async def _cleanup_seeded_rows():
    """Remove this module's seeded tutor rows after each test.

    ``db_session`` is backed by a session-scoped SQLite engine and the shared
    DB is reused across tests, so rows this module creates (identified by a
    recognizable title) must be removed to avoid leaking into the global tutor
    tables that other subsystems assert against and to keep
    ``enforce_retention`` (now learner-scoped) deterministic.
    """
    yield
    from sqlalchemy import delete, select

    from app.models.tutor_conversation import TutorConversation
    from app.models.tutor_message import TutorMessage
    from app.models.tutor_session import TutorSession
    from tests.conftest import TestSessionLocal

    async with TestSessionLocal() as session:
        conversation_ids = list(
            (
                await session.execute(
                    select(TutorConversation.id).where(
                        TutorConversation.title == "Retention conversation"
                    )
                )
            ).scalars().all()
        )
        if conversation_ids:
            await session.execute(
                delete(TutorMessage).where(
                    TutorMessage.conversation_id.in_(conversation_ids)
                )
            )
            await session.execute(delete(TutorConversation).where(TutorConversation.id.in_(conversation_ids)))
        await session.execute(
            delete(TutorSession).where(TutorSession.title == "Retention test session")
        )
        await session.commit()


def _make_service(db_session: AsyncSession) -> MasteryTutorService:
    return MasteryTutorService(UnitOfWork(session=db_session))


async def _seed_user_with_session(
    db_session: AsyncSession,
    *,
    user_id: uuid.UUID,
    until: datetime,
) -> TutorSession:
    await seed_user(db_session, user_id, email=f"ret-{user_id.hex[:6]}@example.com")
    session = TutorSession(
        user_id=user_id,
        title="Retention test session",
        status=TutorSessionStatus.ACTIVE.value,
    )
    db_session.add(session)
    await db_session.flush()
    session.updated_at = until
    session.created_at = until
    await db_session.flush()
    return session


async def _seed_conversation_with_messages(
    db_session: AsyncSession,
    *,
    user_id: uuid.UUID,
    session: TutorSession,
    until: datetime,
) -> TutorConversation:
    conversation = TutorConversation(
        user_id=user_id,
        session_id=session.id,
        session_public_id=session.public_id,
        title="Retention conversation",
        status=TutorConversationStatus.ACTIVE.value,
    )
    db_session.add(conversation)
    await db_session.flush()
    msg = TutorMessage(
        conversation_id=conversation.id,
        user_id=user_id,
        role="user",
        content="old message bound for cleanup",
        status="completed",
    )
    db_session.add(msg)
    await db_session.flush()
    conversation.updated_at = until
    conversation.created_at = until
    msg.created_at = until
    msg.updated_at = until
    await db_session.flush()
    return conversation


async def _message_count(db_session: AsyncSession, conversation_id: uuid.UUID) -> int:
    result = await db_session.execute(
        select(func.count()).select_from(TutorMessage).where(
            TutorMessage.conversation_id == conversation_id
        )
    )
    return int(result.scalar_one() or 0)


@pytest.mark.asyncio
async def test_enforce_retention_archives_idle_sessions(
    db_session: AsyncSession,
) -> None:
    uid = uuid.uuid4()
    now = datetime(2026, 9, 4, tzinfo=UTC)
    idle_past = now - timedelta(days=40)  # > TUTOR_SESSION_IDLE_DAYS (30)
    await _seed_user_with_session(db_session, user_id=uid, until=idle_past)

    fresh = await _seed_user_with_session(db_session, user_id=uuid.uuid4(), until=now)

    archived, removed = await _make_service(db_session).enforce_retention(user_id=uid, now=now)

    assert archived == 1
    assert removed == 0
    # Idle session archived; fresh session still active.
    result = await db_session.execute(
        select(TutorSession.status).where(TutorSession.id == fresh.id)
    )
    assert result.scalar_one() == TutorSessionStatus.ACTIVE.value


@pytest.mark.asyncio
async def test_enforce_retention_removes_expired_conversation_messages(
    db_session: AsyncSession,
) -> None:
    uid = uuid.uuid4()
    now = datetime(2026, 9, 4, tzinfo=UTC)
    cleanup_past = now - timedelta(days=100)  # > TUTOR_CONVERSATION_CLEANUP_DAYS (90)
    session = await _seed_user_with_session(db_session, user_id=uid, until=cleanup_past)
    conversation = await _seed_conversation_with_messages(
        db_session, user_id=uid, session=session, until=cleanup_past
    )

    archived, removed = await _make_service(db_session).enforce_retention(user_id=uid, now=now)

    # The 100-day-old session is idle too, so it is correctly archived AND its
    # expired conversation is removed with its messages.
    assert archived == 1
    assert removed == 1
    # Conversation is soft-deleted and its message rows are gone (storage bound).
    result = await db_session.execute(
        select(TutorConversation).where(TutorConversation.id == conversation.id)
    )
    conv_row = result.scalar_one()
    assert conv_row.deleted_at is not None
    assert await _message_count(db_session, conversation.id) == 0


@pytest.mark.asyncio
async def test_enforce_retention_leaves_fresh_data_intact(
    db_session: AsyncSession,
) -> None:
    uid = uuid.uuid4()
    now = datetime(2026, 9, 4, tzinfo=UTC)
    session = await _seed_user_with_session(db_session, user_id=uid, until=now)
    conversation = await _seed_conversation_with_messages(
        db_session, user_id=uid, session=session, until=now
    )

    archived, removed = await _make_service(db_session).enforce_retention(user_id=uid, now=now)

    assert archived == 0
    assert removed == 0
    result = await db_session.execute(
        select(TutorSession.status).where(TutorSession.id == session.id)
    )
    assert result.scalar_one() == TutorSessionStatus.ACTIVE.value
    conv_result = await db_session.execute(
        select(TutorConversation).where(TutorConversation.id == conversation.id)
    )
    assert conv_result.scalar_one().deleted_at is None
    assert await _message_count(db_session, conversation.id) == 1
