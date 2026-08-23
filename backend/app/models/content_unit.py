from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDMixin
from shared.constants import ContentUnitType

if TYPE_CHECKING:
    from app.models.content_block import ContentBlock
    from app.models.presentation import Presentation

PUBLIC_ID_PREFIX = "unit_"


def generate_content_unit_public_id() -> str:
    return f"{PUBLIC_ID_PREFIX}{uuid.uuid4().hex[:16]}"


class ContentUnit(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "content_units"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_content_unit_public_id,
    )
    presentation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("presentations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    unit_type: Mapped[ContentUnitType] = mapped_column(
        String(20),
        nullable=False,
        default=ContentUnitType.DOCUMENT,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    meta: Mapped[dict[str, object] | None] = mapped_column(
        "metadata",
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )

    presentation: Mapped[Presentation] = relationship(
        "Presentation", back_populates="content_units"
    )
    blocks: Mapped[list[ContentBlock]] = relationship(
        "ContentBlock",
        back_populates="content_unit",
        cascade="all, delete-orphan",
        order_by="ContentBlock.position",
    )

    __table_args__ = (
        UniqueConstraint(
            "presentation_id",
            "position",
            name="uq_content_units_pres_position",
        ),
        Index("ix_content_units_pres_position", "presentation_id", "position"),
    )
