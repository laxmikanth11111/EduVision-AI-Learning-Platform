from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDMixin
from shared.constants import ContentBlockType

if TYPE_CHECKING:
    from app.models.content_unit import ContentUnit

PUBLIC_ID_PREFIX = "block_"


def generate_content_block_public_id() -> str:
    return f"{PUBLIC_ID_PREFIX}{uuid.uuid4().hex[:16]}"


class ContentBlock(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "content_blocks"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_content_block_public_id,
    )
    content_unit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_units.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    block_type: Mapped[ContentBlockType] = mapped_column(
        String(30),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[dict[str, object] | None] = mapped_column(
        "metadata",
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )

    content_unit: Mapped[ContentUnit] = relationship("ContentUnit", back_populates="blocks")

    __table_args__ = (
        UniqueConstraint(
            "content_unit_id",
            "position",
            name="uq_content_blocks_unit_position",
        ),
        Index("ix_content_blocks_unit_position", "content_unit_id", "position"),
    )
