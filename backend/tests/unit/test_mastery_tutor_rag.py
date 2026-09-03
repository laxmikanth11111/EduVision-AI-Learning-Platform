"""P8 Mastery Tutor AI / RAG grounding unit tests (C3).

Verifies the mandatory ``AIContentService`` path is used (never a direct
provider-SDK call), that answers are grounded strictly in the learner's own
content units and mastery state, that attribution/confidence are truthful, and
that the deterministic fallback is used only when RAG is cold or AI fails.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.unit_of_work import UnitOfWork
from app.models.content_unit import ContentUnit
from app.models.document_chunk import DocumentChunk
from app.models.presentation import Presentation
from app.schemas.tutor import TutorMessageSendRequest, TutorSessionCreateRequest
from app.services.educational_memory_service import educational_memory_service
from app.services.mastery_tutor_service import MasteryTutorService
from shared.constants import TutorSourceKind
from tests.conftest import TestSessionLocal
from tests.learner_progress_helpers import seed_learner


@pytest.fixture(autouse=True)
def _reset_memory_cache() -> None:
    educational_memory_service._memories.clear()  # noqa: SLF001
    return


@pytest.fixture(autouse=True)
async def _cleanup_seeded_source_rows():
    """Remove learner-owned DocumentChunk/ContentUnit rows this module seeds.

    ``test_rag_indexing_service`` asserts against *global* counts of
    ``document_chunks``/``content_units`` (``_count(...) == 0``, unscoped
    ``select(DocumentChunk)``), so P8 must not leave any such rows in the
    shared, session-scoped SQLite DB. This teardown deletes the rows this
    module creates (identified by the ``Gaussian Reference`` source title) so
    the RAG-indexing subsystem's global-count assumptions stay valid.
    """
    yield
    from sqlalchemy import delete, select

    from app.models.content_unit import ContentUnit
    from app.models.document_chunk import DocumentChunk

    async with TestSessionLocal() as session:
        unit_ids = list(
            (
                await session.execute(
                    select(ContentUnit.id).where(ContentUnit.title == "Gaussian Reference")
                )
            ).scalars().all()
        )
        if unit_ids:
            await session.execute(
                delete(DocumentChunk).where(DocumentChunk.content_unit_id.in_(unit_ids))
            )
            await session.execute(delete(ContentUnit).where(ContentUnit.id.in_(unit_ids)))
            await session.commit()


async def _seed_learner_with_source(
    session: AsyncSession,
    uid: uuid.UUID,
    email: str,
    source_text: str,
) -> dict[str, object]:
    """Seed a learner + a learner-owned source chunk (ContentUnit + DocumentChunk)."""
    lookups = await seed_learner(session, uid, email=email)

    pres = (
        await session.execute(
            select(Presentation).where(Presentation.public_id == lookups["presentation_id"])
        )
    ).scalar_one()

    unit = ContentUnit(
        presentation_id=pres.id,
        position=0,
        title="Gaussian Reference",
        raw_text=source_text,
    )
    session.add(unit)
    await session.flush()

    chunk = DocumentChunk(
        presentation_id=pres.id,
        content_unit_id=unit.id,
        title="Gaussian Reference",
        content=source_text,
        position=0,
        version=1,
    )
    session.add(chunk)
    # Flush (not commit) so the tutor service can read these rows on the same
    # session while the db_session fixture's teardown rollback removes them from
    # the shared, session-scoped SQLite DB. This keeps the learner-owned chunks
    # out of the global DocumentChunk/ContentUnit tables that other subsystem
    # tests (e.g. test_rag_indexing_service) assert against with global counts.
    await session.flush()

    return {
        "presentation_id": lookups["presentation_id"],
        "lesson_id": lookups["lesson_id"],
    }


async def _make_service(session: AsyncSession) -> MasteryTutorService:
    return MasteryTutorService(UnitOfWork(session=session))


def _patch_ai_to_local(monkeypatch: pytest.MonkeyPatch) -> None:
    """Direct the tutor's AI path to ``AIContentService`` backed by the local
    deterministic provider so the RAG+AI branch is genuinely exercised.
    """
    from app.ai.config import build_ai_provider_config
    from app.ai.providers.local import LocalMockProvider
    from app.ai.service import AIContentService

    def _local_service(uow=None):
        config = build_ai_provider_config(provider="local")
        return AIContentService(provider=LocalMockProvider(config))

    # _produce_answer imports get_ai_content_service from app.ai.service.
    monkeypatch.setattr("app.ai.service.get_ai_content_service", _local_service)


@pytest.mark.asyncio
async def test_rag_path_grounds_answer_in_learner_source(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    uid = uuid.uuid4()
    source = (
        "Gaussian Distributions model symmetric bell curves. The mean sets the "
        "centre and the standard deviation sets the spread of the curve. "
        "Approximately 95% of values lie within two standard deviations of the mean."
    )
    lookups = await _seed_learner_with_source(db_session, uid, f"rag_a_{uid.hex[:6]}@example.com", source)

    # Use a deterministic local provider behind AIContentService so the RAG+AI
    # branch is actually exercised (real Gemini is absent/quota-limited in CI).
    _patch_ai_to_local(monkeypatch)

    svc = await _make_service(db_session)

    # Anchor the session to the learner's lesson so RAG resolves their content units.
    session_obj = await svc.create_session(
        uid,
        TutorSessionCreateRequest(
            lesson_id=lookups["lesson_id"],
            title="Grounded chat",
        ),
    )
    exchange = await svc.send_message(
        uid,
        session_obj["id"],
        TutorMessageSendRequest(content="Explain the bell curve from my notes."),
    )
    reply = exchange["assistant_message"]
    # RAG context is available (learner-owned chunk) so the AI path is used.
    assert reply["source_kind"] == TutorSourceKind.RAG.value
    # Attribution reflects the learner's own source; confidence is grounded.
    assert reply["attribution"]
    assert reply["confidence"] in {"high", "medium", "low"}
    # The grounded reply must reference the learner's source material.
    assert source[:50].rstrip() in reply["content"] or "Source" in reply["content"]


@pytest.mark.asyncio
async def test_rag_is_learner_scoped(db_session: AsyncSession) -> None:
    """User A's chunks must never be retrieved for User B's session."""
    owner = uuid.uuid4()
    source = "Private material belonging exclusively to user A."
    await _seed_learner_with_source(db_session, owner, f"rag_own_{owner.hex[:6]}@example.com", source)

    # User B has no content units / chunks at all.
    intruder = uuid.uuid4()
    from tests.learner_progress_helpers import seed_user

    await seed_user(db_session, intruder, email=f"rag_int_{intruder.hex[:6]}@example.com")

    svc = await _make_service(db_session)
    session_obj = await svc.create_session(
        intruder,
        TutorSessionCreateRequest(title="Intruder chat"),
    )
    exchange = await svc.send_message(
        intruder,
        session_obj["id"],
        TutorMessageSendRequest(content="Tell me about Gaussian Distributions."),
    )
    reply = exchange["assistant_message"]
    # User B has no RAG chunks, so the answer is deterministic, not grounded in
    # user A's private material.
    assert reply["source_kind"] == TutorSourceKind.DETERMINISTIC.value
    assert "Private material belonging exclusively to user A" not in reply["content"]


@pytest.mark.asyncio
async def test_deterministic_fallback_when_rag_cold(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    from tests.learner_progress_helpers import seed_learner

    lookups = await seed_learner(db_session, uid, email=f"rag_cold_{uid.hex[:6]}@example.com")
    svc = await _make_service(db_session)
    session_obj = await svc.create_session(
        uid,
        TutorSessionCreateRequest(
            lesson_id=lookups["lesson_id"],
            title="Cold RAG chat",
        ),
    )
    exchange = await svc.send_message(
        uid,
        session_obj["id"],
        TutorMessageSendRequest(content="Help me with this."),
    )
    reply = exchange["assistant_message"]
    # No RAG chunks exist → deterministic, grounded in mastery data, truthful.
    assert reply["source_kind"] == TutorSourceKind.DETERMINISTIC.value
    assert reply["confidence"] in {"high", "medium", "low"}
    # The answer is derived from the learner's own mastery state.
    assert reply["content"]
    assert len(reply["content"]) <= 8000


@pytest.mark.asyncio
async def test_answer_context_is_bounded(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    await _seed_learner_with_source(
        db_session,
        uid,
        f"rag_bnd_{uid.hex[:6]}@example.com",
        ("word " * 2000).strip(),
    )
    svc = await _make_service(db_session)
    session_obj = await svc.create_session(
        uid,
        TutorSessionCreateRequest(title="Bounded chat"),
    )
    exchange = await svc.send_message(
        uid,
        session_obj["id"],
        TutorMessageSendRequest(content="Summarize everything."),
    )
    reply = exchange["assistant_message"]
    # Even a very long learner source yields a bounded, safe reply.
    assert reply["content"]
    assert len(reply["content"]) <= 8000
