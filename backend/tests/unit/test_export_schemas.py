from __future__ import annotations

from datetime import UTC, datetime, timezone

from app.schemas.export import (
    ExportCreateRequest,
    ExportJobData,
    ExportOptions,
    ExportStatusData,
)


def test_export_options_schema() -> None:
    options = ExportOptions(includeAnswerKey=True, pageSize="a4")
    assert options.include_answer_key is True
    assert options.page_size == "a4"
    assert options.include_diagrams is True


def test_export_create_request_schema() -> None:
    req = ExportCreateRequest(
        format="pdf",
        kind="notes",
        includeModes=["theory", "quiz"],
        options=ExportOptions(includeAnswerKey=False),
    )
    assert req.format == "pdf"
    assert req.kind == "notes"
    assert "quiz" in req.include_modes


def test_export_job_data_schema() -> None:
    now = datetime.now(UTC)
    data = ExportJobData(
        exportId="expjob_123",
        status="queued",
        queuedAt=now,
        kind="notes",
        format="pdf",
    )
    assert data.export_id == "expjob_123"
    assert data.progress_percentage == 0


def test_export_status_data_schema() -> None:
    data = ExportStatusData(
        exportId="expjob_123",
        status="completed",
        downloadUrl="https://example.com/download.pdf",
        format="pdf",
        progressPercentage=100,
    )
    assert data.download_url == "https://example.com/download.pdf"
    assert data.progress_percentage == 100
