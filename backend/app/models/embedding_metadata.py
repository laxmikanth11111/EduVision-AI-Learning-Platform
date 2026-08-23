from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.vector_index import VectorIndex

PUBLIC_ID_PREFIX = "embmd_"


def generate_metadata_public_id() -> str:
    return f"{PUBLIC_ID_PREFIX}{uuid.uuid4().hex[:16]}"


class EmbeddingMetadata(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "embedding_metadata"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_metadata_public_id,
    )
    index_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vector_indexes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    dimension: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    max_tokens_per_input: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    supported_languages: Mapped[dict[str, object] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )
    config_snapshot: Mapped[dict[str, object] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )
    fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    meta: Mapped[dict[str, object] | None] = mapped_column(
        "metadata",
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )

    index: Mapped[VectorIndex | None] = relationship(
        "VectorIndex", foreign_keys=[index_id]
    )

    __table_args__ = (
        UniqueConstraint(
            "provider",
            "model",
            name="uq_embedding_metadata_provider_model",
        ),
        Index("ix_embedding_metadata_provider_model", "provider", "model"),
        Index("ix_embedding_metadata_status", "status"),
    )
