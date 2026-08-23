from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database.base import Base, TimestampMixin, UUIDMixin
from shared.constants import EmbeddingStatisticsPeriod

if TYPE_CHECKING:
    from app.models.vector_index import VectorIndex

PUBLIC_ID_PREFIX = "estat_"


def generate_statistics_public_id() -> str:
    return f"{PUBLIC_ID_PREFIX}{uuid.uuid4().hex[:16]}"


class EmbeddingStatistics(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "embedding_statistics"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_statistics_public_id,
    )
    index_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("vector_indexes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    period: Mapped[str] = mapped_column(
        String(20), nullable=False, default=EmbeddingStatisticsPeriod.TOTAL.value
    )
    stats_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    total_chunks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    embedded_chunks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pending_chunks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_chunks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stale_chunks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    orphan_embeddings: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_embeddings: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens_embedded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_dimension: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    avg_tokens_per_chunk: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    avg_embedding_latency_ms: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0
    )
    total_embeddings_generated: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    total_embedding_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ready")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    index: Mapped[VectorIndex | None] = relationship(
        "VectorIndex", foreign_keys=[index_id]
    )

    @property
    def period_enum(self) -> EmbeddingStatisticsPeriod:
        return EmbeddingStatisticsPeriod(self.period)

    @property
    def is_deleted(self) -> bool:
        return False

    __table_args__ = (
        UniqueConstraint(
            "index_id",
            "period",
            "stats_date",
            name="uq_embedding_statistics_index_period_date",
        ),
        Index("ix_embedding_statistics_period_date", "period", "stats_date"),
        Index("ix_embedding_statistics_index_period", "index_id", "period"),
    )
