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
from shared.constants import (
    ChunkingStrategy,
    EmbeddingRetryState,
    VectorIndexStatus,
    VectorIndexType,
)

if TYPE_CHECKING:
    from app.models.embedding_metadata import EmbeddingMetadata
    from app.models.embedding_statistics import EmbeddingStatistics
    from app.models.vector_index_version import VectorIndexVersion

PUBLIC_ID_PREFIX = "vindex_"


def generate_index_public_id() -> str:
    return f"{PUBLIC_ID_PREFIX}{uuid.uuid4().hex[:16]}"


class VectorIndex(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "vector_indexes"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_index_public_id,
    )
    presentation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("presentations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    lesson_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("generated_lessons.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    index_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default=VectorIndexType.PRESENTATION.value
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=VectorIndexStatus.BUILDING.value
    )
    strategy: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ChunkingStrategy.HEADING.value
    )
    chunk_size: Mapped[int] = mapped_column(Integer, nullable=False, default=1500)
    chunk_overlap: Mapped[int] = mapped_column(Integer, nullable=False, default=150)
    max_chunk_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    provider: Mapped[str | None] = mapped_column(String(30), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    dimension: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    embedding_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    latest_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    config: Mapped[dict[str, object] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_state: Mapped[str] = mapped_column(
        String(20), nullable=False, default=EmbeddingRetryState.NONE.value
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    versions: Mapped[list[VectorIndexVersion]] = relationship(
        "VectorIndexVersion",
        back_populates="index",
        cascade="all, delete-orphan",
        order_by="VectorIndexVersion.version",
    )
    metadata_rows: Mapped[list[EmbeddingMetadata]] = relationship(
        "EmbeddingMetadata", back_populates="index"
    )
    statistics: Mapped[list[EmbeddingStatistics]] = relationship(
        "EmbeddingStatistics", back_populates="index"
    )

    @property
    def index_type_enum(self) -> VectorIndexType:
        return VectorIndexType(self.index_type)

    @property
    def status_enum(self) -> VectorIndexStatus:
        return VectorIndexStatus(self.status)

    @property
    def strategy_enum(self) -> ChunkingStrategy:
        return ChunkingStrategy(self.strategy)

    @property
    def retry_state_enum(self) -> EmbeddingRetryState:
        return EmbeddingRetryState(self.retry_state)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    __table_args__ = (
        UniqueConstraint(
            "presentation_id",
            "index_type",
            name="uq_vector_indexes_presentation_index_type",
        ),
        Index("ix_vector_indexes_status_updated", "status", "updated_at"),
        Index("ix_vector_indexes_presentation_status", "presentation_id", "status"),
        Index("ix_vector_indexes_type_status", "index_type", "status"),
    )
