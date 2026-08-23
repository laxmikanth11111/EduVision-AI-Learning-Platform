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

if TYPE_CHECKING:
    from app.models.document_chunk import DocumentChunk
    from app.models.generated_lesson import GeneratedLesson
    from app.models.presentation import Presentation

PUBLIC_ID_PREFIX = "sec_"


def generate_section_public_id() -> str:
    return f"{PUBLIC_ID_PREFIX}{uuid.uuid4().hex[:16]}"


class ChunkSection(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "chunk_sections"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_section_public_id,
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
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chunk_sections.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    section_type: Mapped[str] = mapped_column(String(30), nullable=False, default="heading")
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    heading_path: Mapped[dict[str, object] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_slide: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_unit_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    meta: Mapped[dict[str, object] | None] = mapped_column(
        "metadata",
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    parent: Mapped[ChunkSection | None] = relationship(
        "ChunkSection", remote_side="ChunkSection.id", foreign_keys=[parent_id]
    )
    children: Mapped[list[ChunkSection]] = relationship(
        "ChunkSection",
        back_populates="parent",
        cascade="all, delete-orphan",
        foreign_keys=[parent_id],
    )
    presentation: Mapped[Presentation | None] = relationship(
        "Presentation", foreign_keys=[presentation_id]
    )
    lesson: Mapped[GeneratedLesson | None] = relationship(
        "GeneratedLesson", foreign_keys=[lesson_id]
    )
    chunks: Mapped[list[DocumentChunk]] = relationship(
        "DocumentChunk",
        back_populates="section",
        foreign_keys="DocumentChunk.section_id",
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    __table_args__ = (
        UniqueConstraint(
            "presentation_id",
            "position",
            "level",
            name="uq_chunk_sections_pres_pos_level",
        ),
        Index("ix_chunk_sections_pres_level", "presentation_id", "level"),
    )
