from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.presentation import Presentation


class PresentationTag(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "presentation_tags"

    presentation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("presentations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)

    presentation: Mapped[Presentation] = relationship("Presentation", back_populates="tags")

    __table_args__ = (
        UniqueConstraint(
            "presentation_id",
            "name",
            name="uq_presentation_tags_pres_name",
        ),
        Index("ix_presentation_tags_name", "name"),
    )
