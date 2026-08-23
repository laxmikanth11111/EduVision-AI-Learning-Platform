from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDMixin
from shared.constants import ExportRetryState

if TYPE_CHECKING:
    from app.models.export_job import ExportJob

PUBLIC_ID_PREFIX = "expfile_"


def generate_export_file_public_id() -> str:
    return f"{PUBLIC_ID_PREFIX}{uuid.uuid4().hex[:16]}"


class ExportFile(Base, UUIDMixin, TimestampMixin):
    """Artifact payload metadata for a generated export output file."""

    __tablename__ = "export_files"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_export_file_public_id,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("export_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    download_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    meta: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    retry_state: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ExportRetryState.NONE.value
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    job: Mapped[ExportJob] = relationship("ExportJob", back_populates="export_files")

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    __table_args__ = (
        Index("ix_export_files_job_user", "job_id", "user_id"),
        Index("ix_export_files_expires", "expires_at"),
    )
