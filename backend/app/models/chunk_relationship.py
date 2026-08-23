from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDMixin
from shared.constants import ChunkRelationshipType

if TYPE_CHECKING:
    from app.models.document_chunk import DocumentChunk

PUBLIC_ID_PREFIX = "rel_"


def generate_relationship_public_id() -> str:
    return f"{PUBLIC_ID_PREFIX}{uuid.uuid4().hex[:16]}"


class ChunkRelationship(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "chunk_relationships"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_relationship_public_id,
    )
    source_chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_chunks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_chunks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    relationship_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default=ChunkRelationshipType.NEXT.value
    )
    meta: Mapped[dict[str, object] | None] = mapped_column(
        "metadata",
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")

    source_chunk: Mapped[DocumentChunk] = relationship(
        "DocumentChunk",
        back_populates="relationships",
        foreign_keys=[source_chunk_id],
    )
    target_chunk: Mapped[DocumentChunk] = relationship(
        "DocumentChunk", foreign_keys=[target_chunk_id]
    )

    @property
    def relationship_type_enum(self) -> ChunkRelationshipType:
        return ChunkRelationshipType(self.relationship_type)

    __table_args__ = (
        UniqueConstraint(
            "source_chunk_id",
            "target_chunk_id",
            "relationship_type",
            name="uq_chunk_relationships_source_target_type",
        ),
        Index("ix_chunk_relationships_target_id", "target_chunk_id"),
        Index("ix_chunk_relationships_type", "relationship_type"),
    )
