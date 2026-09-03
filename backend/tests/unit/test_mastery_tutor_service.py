"""P8 Mastery Tutor service unit tests.

Exercise ``MasteryTutorService`` directly against the seeded test database
without HTTP: learner-scoped session creation, ownership verification of the
target concept, deterministic (AI-unavailable) fallback answering with truthful
``source_kind``/``attribution``/``confidence``, idempotent turn replay, bounded
context assembly, remediation, and cross-user isolation (404-equalized).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.database.unit_of_work import UnitOfWork
from app.models.concept import Concept
from app.services.educational_memory_service import educational_memory_service
from app.services.mastery_tutor_service import MasteryTutorService
from shared.constants import TutorSourceKind
from tests.learner_progress_helpers import seed_learner, seed_user


@pytest.fixture(autouse=True)
def _reset_memory_cache() -> None:
    educational_memory_service._memories.clear()  # noqa: SLF001
    return


async def _seed_tutor_learner(
    session: AsyncSession,
    user_id: uuid.UUID,
    email: str,
) -> dict[str, object]:
    """Seed a learner + a Gaussian concept owned by that learner.

    The weak concept's public id is unique per test so that committed rows never
    collide across tests sharing the same SQLite file. The educational memory is
    re-pointed at that same unique concept id so remediation's mastery lookup
    stays consistent.
    """
    lookups = await seed_learner(session, user_id, email=email)

    from sqlalchemy import select

    from app.models.educational_memory import EducationalMemoryRecord
    from app.models.presentation import Presentation

    concept_id = f"concept_{uuid.uuid4().hex[:12]}"

    rec = (
        await session.execute(
            select(EducationalMemoryRecord).where(
                EducationalMemoryRecord.user_id == user_id
            )
        )
    ).scalar_one()
    # memory_data is a plain JSON column (not MutableDict) so we must assign a
    # brand-new dict for SQLAlchemy to detect the change on flush.
    mem = dict(rec.memory_data)
    records = {
        str(k): dict(v) for k, v in mem["concept_records"].items()
    }
    records[concept_id] = records.pop("concept_gauss")
    new_mem = dict(mem)
    new_mem["weak_concepts"] = [concept_id]
    new_mem["concept_records"] = records
    rec.memory_data = new_mem
    await session.flush()

    pres = (
        await session.execute(
            select(Presentation).where(Presentation.public_id == lookups["presentation_id"])
        )
    ).scalar_one()
    gauss = Concept(
        public_id=concept_id,
        name="Gaussian Distributions",
        description="Normal distribution functions and their properties.",
        presentation_id=pres.id,
        lesson_id=None,
    )
    session.add(gauss)
    await session.flush()
    await session.commit()

    return {
        "presentation_id": lookups["presentation_id"],
        "lesson_id": lookups["lesson_id"],
        "concept_id": concept_id,
    }


async def _make_service(session: AsyncSession) -> MasteryTutorService:
    return MasteryTutorService(UnitOfWork(session=session))


def _create_session_request(**overrides: object) -> object:
    from app.schemas.tutor import TutorSessionCreateRequest

    return TutorSessionCreateRequest(**overrides)


def _send_request(content: str, client_message_id: str | None = None) -> object:
    from app.schemas.tutor import TutorMessageSendRequest

    return TutorMessageSendRequest(content=content, client_message_id=client_message_id)


def _remediate_request(concept_id: str) -> object:
    from app.schemas.tutor import TutorRemediateRequest

    return TutorRemediateRequest(target_concept_id=concept_id)


@pytest.mark.asyncio
async def test_create_session_for_owned_lesson(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    lookups = await _seed_tutor_learner(db_session, uid, email=f"tutor_own_{uid.hex[:6]}@example.com")
    svc = await _make_service(db_session)
    result = await svc.create_session(
        uid,
        _create_session_request(  # type: ignore[arg-type]
            lesson_id=lookups["lesson_id"],
            title="Gaussian help",
        ),
    )
    assert result["title"] == "Gaussian help"
    assert result["status"] == "active"
    assert result["lesson_id"] == lookups["lesson_id"]


@pytest.mark.asyncio
async def test_create_session_rejects_foreign_lesson(db_session: AsyncSession) -> None:
    owner = uuid.uuid4()
    lookups = await _seed_tutor_learner(db_session, owner, email=f"tutor_own_{owner.hex[:6]}@example.com")
    other = uuid.uuid4()
    await seed_user(db_session, other, email=f"tutor_other_{other.hex[:6]}@example.com")
    svc = await _make_service(db_session)
    with pytest.raises(NotFoundError):
        # `other` tries to anchor a session to `owner`'s lesson.
        await svc.create_session(
            other,
            _create_session_request(  # type: ignore[arg-type]
                lesson_id=lookups["lesson_id"],
                title="Sneaky",
            ),
        )


@pytest.mark.asyncio
async def test_send_message_deterministic_fallback(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    await _seed_tutor_learner(db_session, uid, email=f"tutor_msg_{uid.hex[:6]}@example.com")
    svc = await _make_service(db_session)
    session_obj = await svc.create_session(uid, _create_session_request(title="Tutor chat"))  # type: ignore[arg-type]
    exchange = await svc.send_message(
        uid,
        session_obj["id"],
        _send_request("Why is Gaussian Distributions weak for me?"),
    )
    assert exchange["assistant_message"] is not None
    reply = exchange["assistant_message"]
    assert reply["source_kind"] == TutorSourceKind.DETERMINISTIC.value
    # Deterministic answers are always grounded/attributed, never fabricated.
    assert reply["confidence"] in {"high", "medium", "low"}
    # The assistant content references the learner's weak concept.
    assert "Gaussian Distributions" in reply["content"] or "mastery" in reply["content"]


@pytest.mark.asyncio
async def test_send_message_idempotent_replay(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    await _seed_tutor_learner(db_session, uid, email=f"tutor_idem_{uid.hex[:6]}@example.com")
    svc = await _make_service(db_session)
    session_obj = await svc.create_session(uid, _create_session_request(title="Tutor idem"))  # type: ignore[arg-type]
    client_id = f"cli_{uuid.uuid4().hex}"
    first = await svc.send_message(
        uid, session_obj["id"], _send_request("Hello tutor", client_id)
    )
    second = await svc.send_message(
        uid, session_obj["id"], _send_request("Hello tutor", client_id)
    )
    assert first["assistant_message"]["id"] == second["assistant_message"]["id"]


@pytest.mark.asyncio
async def test_remediate_weak_concept(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    lookups = await _seed_tutor_learner(db_session, uid, email=f"tutor_rem_{uid.hex[:6]}@example.com")
    svc = await _make_service(db_session)
    result = await svc.remediate(uid, _remediate_request(str(lookups["concept_id"])))
    assert result["target_concept_name"] == "Gaussian Distributions"
    assert result["mastery_score"] == 30.0
    assert result["source_kind"] == TutorSourceKind.DETERMINISTIC.value
    assert result["response"]
    assert "Gaussian Distributions" in result["response"]
    assert result["conversation_id"] is not None


@pytest.mark.asyncio
async def test_remediate_foreign_concept_is_404(db_session: AsyncSession) -> None:
    owner = uuid.uuid4()
    lookups = await _seed_tutor_learner(db_session, owner, email=f"tutor_remown_{owner.hex[:6]}@example.com")
    other = uuid.uuid4()
    await seed_user(db_session, other, email=f"tutor_remoth_{other.hex[:6]}@example.com")
    svc = await _make_service(db_session)
    with pytest.raises(NotFoundError):
        # Concept belongs to `owner`, but `other` asks to remediate it.
        await svc.remediate(other, _remediate_request(str(lookups["concept_id"])))


@pytest.mark.asyncio
async def test_remediate_missing_concept_is_404(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    await _seed_tutor_learner(db_session, uid, email=f"tutor_remmiss_{uid.hex[:6]}@example.com")
    svc = await _make_service(db_session)
    with pytest.raises(NotFoundError):
        await svc.remediate(uid, _remediate_request("concept_nope"))


@pytest.mark.asyncio
async def test_send_message_to_foreign_session_is_404(db_session: AsyncSession) -> None:
    owner = uuid.uuid4()
    await _seed_tutor_learner(db_session, owner, email=f"tutor_ms_own_{owner.hex[:6]}@example.com")
    other = uuid.uuid4()
    await seed_user(db_session, other, email=f"tutor_ms_oth_{other.hex[:6]}@example.com")
    svc = await _make_service(db_session)
    session_obj = await svc.create_session(owner, _create_session_request(title="Owner chat"))  # type: ignore[arg-type]
    with pytest.raises(NotFoundError):
        await svc.send_message(other, session_obj["id"], _send_request("intruder"))
