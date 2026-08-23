from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.vector_index import VectorIndex

PUBLIC_ID_PREFIX = "vidx_"


def generate_index_version_public_id() -> str:
    return f"{PUBLIC_ID_PREFIX}{uuid.uuid4().hex[:16]}"


class VectorIndexVersion(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "vector_index_versions"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_index_version_public_id,
    )
    index_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vector_indexes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ready")
    source_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    embedding_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    config: Mapped[dict[str, object] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )
    changelog: Mapped[dict[str, object] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )
    meta: Mapped[dict[str, object] | None] = mapped_column(
        "metadata",
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    index: Mapped[VectorIndex] = relationship(
        "VectorIndex", back_populates="versions"
    )

    @property
    def is_deleted(self) -> bool:
        return False

    __table_args__ = (
        UniqueConstraint(
            "index_id",
            "version",
            name="uq_vector_index_versions_index_version",
        ),
        Index("ix_vector_index_versions_index_version", "index_id", "version"),
        Index("ix_vector_index_versions_status", "status"),
    )
