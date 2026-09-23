"""B6 — Export-worker ownership-hardening tests.

These are *worker ownership-hardening* tests, NOT exploit reproductions. The
export job creation route already enforces presentation ownership
(``POST /api/v1/exports`` → ``PresentationService.assert_ownership``) and every
reachable execution path into the worker uses a server-generated job
``public_id`` from that guarded route. This suite instead verifies the worker's
own content-construction boundary: even if a job row were ever to reference a
presentation that is not owned by ``job.user_id``, the worker must not export
that victim presentation's content and must behave identically to the
missing-presentation case (no existence/ownership oracle).

Discrimination: ``ExportService._build_export_content`` currently resolves the
target presentation by ``public_id``/numeric id with no owner predicate, so a
cross-user job would include the victim's content. The owner predicate added for
B6 makes foreign targets resolve to the same generic fallback as missing ones.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.unit_of_work import UnitOfWork
from app.models.content_unit import ContentUnit
from app.models.presentation import Presentation
from app.schemas.export import ExportOptions
from app.services.export_service import ExportService
from shared.constants import (
    ExportFormat,
    ExportJobStatus,
    ExportKind,
    PresentationStatus,
    PresentationVisibility,
)

pytestmark = pytest.mark.asyncio

_USER_A_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_USER_B_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

_VICTIM_TITLE = "Victim Quantum Deck"
_VICTIM_CONTENT = "QUBIT_SECRET_CONTENT_MARKER"


async def _seed_owned_presentation(
    session: AsyncSession, owner_id: uuid.UUID
) -> Presentation:
    """Insert a presentation owned by *owner_id* with one distinctive unit."""
    pres = Presentation(
        id=uuid.uuid4(),
        public_id=f"pres_{uuid.uuid4().hex[:16]}",
        owner_id=owner_id,
        title=_VICTIM_TITLE,
        description="Victim content for ownership-boundary tests.",
        topic="Quantum Computing",
        status=PresentationStatus.PUBLISHED.value,
        visibility=PresentationVisibility.PRIVATE.value,
    )
    session.add(pres)
    await session.flush()
    session.add(
        ContentUnit(
            id=uuid.uuid4(),
            presentation_id=pres.id,
            position=1,
            title="Qubits",
            raw_text=_VICTIM_CONTENT,
        )
    )
    await session.commit()
    return pres


async def _create_job(
    service: ExportService,
    user_id: uuid.UUID,
    target_id: str,
    kind: str = ExportKind.NOTES.value,
    fmt: str = ExportFormat.PDF.value,
):
    # Use a unique format variant per call so the active-job dedupe never
    # returns a previously-created job for a different scenario.
    return await service.create_export_job(
        user_id=user_id,
        kind=kind,
        format=fmt,
        target_id=target_id,
        include_modes=["theory"],
        options=ExportOptions(),
    )


def _content_has_victim_data(content) -> bool:
    """True if the built export content carries the victim's markers."""
    if content.title == _VICTIM_TITLE or _VICTIM_CONTENT in (content.title or ""):
        return True
    for section in content.sections or []:
        if _VICTIM_TITLE in str(section.get("title", "")):
            return True
        if _VICTIM_CONTENT in str(section.get("content", "")):
            return True
    return False


async def test_owner_export_builds_content(db_session: AsyncSession) -> None:
    """Owner job + owner presentation → real (non-generic) content is built."""
    pres = await _seed_owned_presentation(db_session, _USER_A_ID)
    service = ExportService(UnitOfWork(session=db_session))
    job = await _create_job(service, _USER_A_ID, pres.public_id)

    content = await service._build_export_content(job)
    assert _content_has_victim_data(content) is True
    assert content.title == _VICTIM_TITLE


async def test_cross_user_job_presentation_mismatch_exported_no_victim_content(
    db_session: AsyncSession,
) -> None:
    """job.user_id=B + presentation.owner_id=A → victim content is NOT built.

    This constructs the mismatched job directly because no reachable route can
    produce it today; it proves the worker boundary would not leak even if such
    a job row existed.
    """
    pres = await _seed_owned_presentation(db_session, _USER_A_ID)
    service = ExportService(UnitOfWork(session=db_session))
    job = await _create_job(service, _USER_B_ID, pres.public_id)

    content = await service._build_export_content(job)
    assert _content_has_victim_data(content) is False


async def test_cross_user_mismatch_matches_missing_presentation_semantics(
    db_session: AsyncSession,
) -> None:
    """A foreign target resolves exactly like a missing one (no oracle)."""
    pres = await _seed_owned_presentation(db_session, _USER_A_ID)
    service = ExportService(UnitOfWork(session=db_session))

    foreign_job = await _create_job(service, _USER_B_ID, pres.public_id, fmt="docx")
    missing_job = await _create_job(
        service, _USER_B_ID, "pres_does_not_exist_123456", fmt="markdown"
    )

    foreign_content = await service._build_export_content(foreign_job)
    missing_content = await service._build_export_content(missing_job)

    assert _content_has_victim_data(foreign_content) is False
    assert _content_has_victim_data(missing_content) is False
    assert foreign_content.title == missing_content.title


async def test_missing_presentation_uses_generic_fallback(db_session: AsyncSession) -> None:
    """Missing presentation keeps the existing generic-fallback semantics."""
    service = ExportService(UnitOfWork(session=db_session))
    job = await _create_job(
        service, _USER_A_ID, "pres_does_not_exist_123456", fmt="pptx"
    )

    content = await service._build_export_content(job)
    assert _content_has_victim_data(content) is False
    assert str(job.kind).capitalize() in content.title or "EduVision" in content.title


async def test_legitimate_worker_processing_completes(db_session: AsyncSession) -> None:
    """A-owned job + A-owned presentation → full worker processing completes."""
    pres = await _seed_owned_presentation(db_session, _USER_A_ID)
    service = ExportService(UnitOfWork(session=db_session))
    job = await _create_job(service, _USER_A_ID, pres.public_id, fmt="html")

    await service.process_export_job(job.public_id)

    status = await service.get_export_job_status(
        user_id=_USER_A_ID, public_id=job.public_id
    )
    assert status["status"] == ExportJobStatus.COMPLETED.value
    assert status["downloadUrl"] is not None
    assert status["progressPercentage"] == 100


async def test_retry_replay_keeps_ownership_boundary(db_session: AsyncSession) -> None:
    """A replayed/reprocessed job still never exports victim content."""
    pres = await _seed_owned_presentation(db_session, _USER_A_ID)
    service = ExportService(UnitOfWork(session=db_session))

    job = await _create_job(service, _USER_B_ID, pres.public_id, fmt="csv")
    first = await service._build_export_content(job)

    second = await service._build_export_content(job)
    assert _content_has_victim_data(first) is False
    assert _content_has_victim_data(second) is False
    assert first.title == second.title

    # A replay through the processing path must not change the outcome either.
    await service.process_export_job(job.public_id)
    status = await service.get_export_job_status(
        user_id=_USER_B_ID, public_id=job.public_id
    )
    assert status["status"] == ExportJobStatus.COMPLETED.value
    assert status["errorMessage"] is None
