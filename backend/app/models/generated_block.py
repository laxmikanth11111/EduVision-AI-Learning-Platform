from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDMixin
from shared.constants import GeneratedBlockType

if TYPE_CHECKING:
    from app.models.generated_lesson_version import GeneratedLessonVersion

PUBLIC_ID_PREFIX = "gblk_"


def generate_generated_block_public_id() -> str:
    return f"{PUBLIC_ID_PREFIX}{uuid.uuid4().hex[:16]}"


class GeneratedBlock(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "generated_blocks"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_generated_block_public_id,
    )
    lesson_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("generated_lesson_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    block_type: Mapped[str] = mapped_column(String(30), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    heading: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[dict[str, object] | None] = mapped_column(
        "metadata",
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )

    lesson_version: Mapped[GeneratedLessonVersion] = relationship(
        "GeneratedLessonVersion", back_populates="blocks"
    )

    @property
    def block_type_enum(self) -> GeneratedBlockType:
        return GeneratedBlockType(self.block_type)

    __table_args__ = (
        UniqueConstraint(
            "lesson_version_id",
            "position",
            name="uq_generated_blocks_version_position",
        ),
        Index("ix_generated_blocks_version_position", "lesson_version_id", "position"),
    )
