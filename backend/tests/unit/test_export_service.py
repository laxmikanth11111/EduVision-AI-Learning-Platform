from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.export import ExportOptions
from app.services.export_service import ExportService
from shared.constants import ExportFormat, ExportJobStatus, ExportKind

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_uow() -> MagicMock:
    uow = MagicMock()
    session = AsyncMock()
    uow.session = session
    uow.flush = AsyncMock()

    async def mock_enter(*args: Any, **kwargs: Any) -> MagicMock:
        return uow

    async def mock_exit(*args: Any) -> None:
        pass

    uow.__aenter__ = mock_enter
    uow.__aexit__ = mock_exit
    return uow


@pytest.fixture
def mock_storage() -> MagicMock:
    storage = MagicMock()
    storage.upload_fileobj = AsyncMock(return_value="exports/file.pdf")
    storage.generate_presigned_url = AsyncMock(return_value="https://example.com/download.pdf")
    return storage


async def test_create_export_job(mock_uow: MagicMock) -> None:
    user_id = uuid.uuid4()

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    mock_uow.session.execute = AsyncMock(return_value=mock_res)

    service = ExportService(uow=mock_uow)
    job = await service.create_export_job(
        user_id=user_id,
        kind=ExportKind.NOTES.value,
        format=ExportFormat.PDF.value,
        target_id="pres_123",
        include_modes=["theory", "quiz"],
        options=ExportOptions(),
    )

    assert job.user_id == user_id
    assert job.kind == ExportKind.NOTES.value
    assert job.format == ExportFormat.PDF.value
    assert job.status == ExportJobStatus.QUEUED.value


async def test_get_export_job_status(mock_uow: MagicMock, mock_storage: MagicMock) -> None:
    user_id = uuid.uuid4()
    job = MagicMock()
    job.id = uuid.uuid4()
    job.public_id = "expjob_123"
    job.status = ExportJobStatus.COMPLETED.value
    job.format = "pdf"
    job.progress_percentage = 100
    job.expires_at = None
    job.error_message = None

    exp_file = MagicMock()
    exp_file.file_path = "exports/notes.pdf"
    exp_file.file_size_bytes = 1024
    exp_file.expires_at = None

    job_res = MagicMock()
    job_res.scalar_one_or_none.return_value = job

    file_res = MagicMock()
    file_res.scalars.return_value.all.return_value = [exp_file]

    mock_uow.session.execute = AsyncMock(side_effect=[job_res, file_res])

    service = ExportService(uow=mock_uow, storage_backend=mock_storage)
    status_data = await service.get_export_job_status(user_id=user_id, public_id="expjob_123")

    assert status_data["exportId"] == "expjob_123"
    assert status_data["status"] == ExportJobStatus.COMPLETED.value
    assert status_data["downloadUrl"] == "https://example.com/download.pdf"
    assert status_data["fileSize"] == 1024
