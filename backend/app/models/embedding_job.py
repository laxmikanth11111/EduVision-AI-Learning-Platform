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
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDMixin
from shared.constants import EmbeddingJobStatus, EmbeddingJobType, EmbeddingRetryState

if TYPE_CHECKING:
    from app.models.embedding_batch import EmbeddingBatch
    from app.models.vector_index import VectorIndex

PUBLIC_ID_PREFIX = "ejob_"


def generate_job_public_id() -> str:
    return f"{PUBLIC_ID_PREFIX}{uuid.uuid4().hex[:16]}"


class EmbeddingJob(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "embedding_jobs"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_job_public_id,
    )
    index_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vector_indexes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    presentation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("presentations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    lesson_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("generated_lessons.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    job_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default=EmbeddingJobType.INDEX.value
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=EmbeddingJobStatus.QUEUED.value
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    total_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    payload: Mapped[dict[str, object] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )
    result: Mapped[dict[str, object] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    retry_state: Mapped[str] = mapped_column(
        String(20), nullable=False, default=EmbeddingRetryState.NONE.value
    )
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

    index: Mapped[VectorIndex | None] = relationship(
        "VectorIndex", foreign_keys=[index_id]
    )
    batches: Mapped[list[EmbeddingBatch]] = relationship(
        "EmbeddingBatch",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="EmbeddingBatch.sequence",
    )

    @property
    def job_type_enum(self) -> EmbeddingJobType:
        return EmbeddingJobType(self.job_type)

    @property
    def status_enum(self) -> EmbeddingJobStatus:
        return EmbeddingJobStatus(self.status)

    @property
    def retry_state_enum(self) -> EmbeddingRetryState:
        return EmbeddingRetryState(self.retry_state)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_embedding_jobs_user_idempotency",
        ),
        Index("ix_embedding_jobs_status_priority", "status", "priority"),
        Index("ix_embedding_jobs_type_status", "job_type", "status"),
        Index("ix_embedding_jobs_index_status", "index_id", "status"),
        Index("ix_embedding_jobs_status_updated", "status", "updated_at"),
    )
