from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDMixin
from shared.constants import EmbeddingBatchStatus

if TYPE_CHECKING:
    from app.models.embedding_job import EmbeddingJob

PUBLIC_ID_PREFIX = "ebat_"


def generate_batch_public_id() -> str:
    return f"{PUBLIC_ID_PREFIX}{uuid.uuid4().hex[:16]}"


class EmbeddingBatch(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "embedding_batches"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_batch_public_id,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("embedding_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=EmbeddingBatchStatus.QUEUED.value
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    request_ids: Mapped[dict[str, object] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )
    result: Mapped[dict[str, object] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    job: Mapped[EmbeddingJob] = relationship("EmbeddingJob", back_populates="batches")

    @property
    def status_enum(self) -> EmbeddingBatchStatus:
        return EmbeddingBatchStatus(self.status)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    __table_args__ = (
        UniqueConstraint(
            "job_id",
            "sequence",
            name="uq_embedding_batches_job_sequence",
        ),
        Index("ix_embedding_batches_job_status", "job_id", "status"),
        Index("ix_embedding_batches_status_updated", "status", "updated_at"),
    )
