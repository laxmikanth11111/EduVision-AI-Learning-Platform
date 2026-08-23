from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.unit_of_work import UnitOfWork
from app.models.content_unit import ContentUnit
from app.models.presentation import Presentation
from app.services.export_service import ExportService
from shared.constants import PresentationStatus, PresentationVisibility

pytestmark = pytest.mark.asyncio


async def test_full_export_workflow_integration(db_session: AsyncSession) -> None:
    # Create Presentation and Content Units
    pres = Presentation(
        id=uuid.uuid4(),
        public_id=f"pres_{uuid.uuid4().hex[:16]}",
        owner_id=None,
        title="Comprehensive Quantum Computing",
        description="Introduction to qubits and entanglement.",
        status=PresentationStatus.PUBLISHED.value,
        visibility=PresentationVisibility.PUBLIC.value,
    )
    unit1 = ContentUnit(
        id=uuid.uuid4(),
        presentation_id=pres.id,
        position=1,
        title="Qubits",
        raw_text="A qubit is the basic unit of quantum information.",
    )
    db_session.add(pres)
    db_session.add(unit1)
    await db_session.commit()

    # 1. Create Export Job via Service
    uow = UnitOfWork(session=db_session)
    service = ExportService(uow=uow)

    dummy_user_id = uuid.uuid4()

    job = await service.create_export_job(
        user_id=dummy_user_id,
        kind="notes",
        format="pdf",
        target_id=pres.public_id,
        include_modes=["theory"],
        options=None,
    )
    assert job.status == "queued"

    # Process export generation
    await service.process_export_job(job.public_id)

    # Verify status completed
    status_data = await service.get_export_job_status(user_id=dummy_user_id, public_id=job.public_id)
    assert status_data["status"] == "completed"
    assert status_data["progressPercentage"] == 100
    assert status_data["downloadUrl"] is not None
