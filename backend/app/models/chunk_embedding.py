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
from shared.constants import EmbeddingVersionStatus

if TYPE_CHECKING:
    from app.models.document_chunk import DocumentChunk

PUBLIC_ID_PREFIX = "emb_"


def generate_embedding_public_id() -> str:
    return f"{PUBLIC_ID_PREFIX}{uuid.uuid4().hex[:16]}"


class ChunkEmbedding(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "chunk_embeddings"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_embedding_public_id,
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_chunks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    dimension: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    vector: Mapped[list[float] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    embedding_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=EmbeddingVersionStatus.ACTIVE.value
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    meta: Mapped[dict[str, object] | None] = mapped_column(
        "metadata",
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    chunk: Mapped[DocumentChunk] = relationship(
        "DocumentChunk", back_populates="embeddings"
    )

    @property
    def status_enum(self) -> EmbeddingVersionStatus:
        return EmbeddingVersionStatus(self.status)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    __table_args__ = (
        UniqueConstraint(
            "chunk_id",
            "provider",
            "model",
            "version",
            name="uq_chunk_embeddings_chunk_provider_model_version",
        ),
        Index("ix_chunk_embeddings_provider_model", "provider", "model"),
        Index("ix_chunk_embeddings_status_version", "status", "version"),
        Index("ix_chunk_embeddings_chunk_status", "chunk_id", "status"),
    )
