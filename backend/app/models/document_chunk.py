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
from shared.constants import ChunkRetryState, ChunkSource, ChunkStatus

if TYPE_CHECKING:
    from app.models.chunk_embedding import ChunkEmbedding
    from app.models.chunk_relationship import ChunkRelationship
    from app.models.chunk_section import ChunkSection
    from app.models.content_block import ContentBlock
    from app.models.content_unit import ContentUnit
    from app.models.generated_lesson import GeneratedLesson
    from app.models.generated_lesson_version import GeneratedLessonVersion
    from app.models.presentation import Presentation

PUBLIC_ID_PREFIX = "chunk_"


def generate_chunk_public_id() -> str:
    return f"{PUBLIC_ID_PREFIX}{uuid.uuid4().hex[:16]}"


class DocumentChunk(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "document_chunks"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_chunk_public_id,
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
    lesson_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("generated_lesson_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    content_unit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_units.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    content_block_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_blocks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    section_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chunk_sections.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    parent_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_chunks.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    chunk_type: Mapped[str] = mapped_column(String(30), nullable=False, default="paragraph")
    source: Mapped[str] = mapped_column(
        String(30), nullable=False, default=ChunkSource.PRESENTATION.value
    )
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    heading_path: Mapped[dict[str, object] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    character_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_slide: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_unit_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    meta: Mapped[dict[str, object] | None] = mapped_column(
        "metadata",
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ChunkStatus.PENDING.value
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    retry_state: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ChunkRetryState.NONE.value
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    section: Mapped[ChunkSection | None] = relationship(
        "ChunkSection", foreign_keys=[section_id]
    )
    parent_chunk: Mapped[DocumentChunk | None] = relationship(
        "DocumentChunk", remote_side="DocumentChunk.id", foreign_keys=[parent_chunk_id]
    )
    child_chunks: Mapped[list[DocumentChunk]] = relationship(
        "DocumentChunk",
        back_populates="parent_chunk",
        cascade="all, delete-orphan",
        foreign_keys=[parent_chunk_id],
    )
    presentation: Mapped[Presentation | None] = relationship(
        "Presentation", foreign_keys=[presentation_id]
    )
    lesson: Mapped[GeneratedLesson | None] = relationship(
        "GeneratedLesson", foreign_keys=[lesson_id]
    )
    lesson_version: Mapped[GeneratedLessonVersion | None] = relationship(
        "GeneratedLessonVersion", foreign_keys=[lesson_version_id]
    )
    content_unit: Mapped[ContentUnit | None] = relationship(
        "ContentUnit", foreign_keys=[content_unit_id]
    )
    content_block: Mapped[ContentBlock | None] = relationship(
        "ContentBlock", foreign_keys=[content_block_id]
    )
    embeddings: Mapped[list[ChunkEmbedding]] = relationship(
        "ChunkEmbedding",
        back_populates="chunk",
        cascade="all, delete-orphan",
    )
    relationships: Mapped[list[ChunkRelationship]] = relationship(
        "ChunkRelationship",
        back_populates="source_chunk",
        cascade="all, delete-orphan",
        foreign_keys="ChunkRelationship.source_chunk_id",
    )

    @property
    def source_enum(self) -> ChunkSource:
        return ChunkSource(self.source)

    @property
    def status_enum(self) -> ChunkStatus:
        return ChunkStatus(self.status)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    __table_args__ = (
        UniqueConstraint(
            "presentation_id",
            "position",
            "version",
            name="uq_document_chunks_pres_position_version",
        ),
        Index("ix_document_chunks_source_position", "source", "position"),
        Index("ix_document_chunks_hash_version", "chunk_hash", "version"),
        Index("ix_document_chunks_pres_status", "presentation_id", "status"),
    )
