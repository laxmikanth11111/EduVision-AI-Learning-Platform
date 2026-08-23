from __future__ import annotations

import uuid

from app.models.export_file import ExportFile, generate_export_file_public_id
from app.models.export_job import ExportJob, generate_export_job_public_id
from app.models.export_template import ExportTemplate, generate_export_template_public_id
from shared.constants import ExportFormat, ExportJobStatus, ExportKind


def test_export_job_defaults() -> None:
    job = ExportJob(
        public_id=generate_export_job_public_id(),
        user_id=uuid.uuid4(),
        kind=ExportKind.NOTES.value,
        format=ExportFormat.PDF.value,
        status=ExportJobStatus.QUEUED.value,
    )
    assert job.public_id.startswith("expjob_")
    assert job.kind == ExportKind.NOTES.value
    assert job.format == ExportFormat.PDF.value
    assert job.status == ExportJobStatus.QUEUED.value
    assert job.status_enum == ExportJobStatus.QUEUED
    assert job.format_enum == ExportFormat.PDF
    assert not job.is_deleted


def test_export_file_defaults() -> None:
    job_id = uuid.uuid4()
    user_id = uuid.uuid4()
    exp_file = ExportFile(
        public_id=generate_export_file_public_id(),
        job_id=job_id,
        user_id=user_id,
        filename="notes.pdf",
        file_path="exports/notes.pdf",
        mime_type="application/pdf",
        download_count=0,
    )
    assert exp_file.public_id.startswith("expfile_")
    assert exp_file.download_count == 0
    assert not exp_file.is_deleted


def test_export_template_defaults() -> None:
    template = ExportTemplate(
        public_id=generate_export_template_public_id(),
        name="Standard",
        template_key="std_test",
        kind=ExportKind.NOTES.value,
        format=ExportFormat.PDF.value,
        is_active=True,
        is_default=False,
    )
    assert template.public_id.startswith("exptpl_")
    assert template.is_active is True
    assert template.is_default is False
    assert not template.is_deleted
