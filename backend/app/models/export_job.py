from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, Index, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDMixin
from shared.constants import ExportFormat, ExportJobStatus, ExportKind, ExportRetryState

if TYPE_CHECKING:
    from app.models.export_file import ExportFile

PUBLIC_ID_PREFIX = "expjob_"


def generate_export_job_public_id() -> str:
    return f"{PUBLIC_ID_PREFIX}{uuid.uuid4().hex[:16]}"


class ExportJob(Base, UUIDMixin, TimestampMixin):
    """Lifecycle tracking for an asynchronous export generation task."""

    __tablename__ = "export_jobs"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_export_job_public_id,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(
        String(30), nullable=False, default=ExportKind.NOTES.value
    )
    format: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ExportFormat.PDF.value
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ExportJobStatus.QUEUED.value
    )
    template: Mapped[str] = mapped_column(String(30), nullable=False, default="standard")
    target_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    options: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress_percentage: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    retry_state: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ExportRetryState.NONE.value
    )
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    export_files: Mapped[list[ExportFile]] = relationship(
        "ExportFile", back_populates="job", cascade="all, delete-orphan"
    )

    @property
    def status_enum(self) -> ExportJobStatus:
        return ExportJobStatus(self.status)

    @property
    def format_enum(self) -> ExportFormat:
        return ExportFormat(self.format)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    __table_args__ = (
        Index("ix_export_jobs_user_status", "user_id", "status"),
        Index("ix_export_jobs_kind_format", "kind", "format"),
    )
