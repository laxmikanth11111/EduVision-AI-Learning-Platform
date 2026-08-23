from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database.base import Base, TimestampMixin, UUIDMixin
from shared.constants import PresentationStatus

if TYPE_CHECKING:
    from app.models.presentation import Presentation

PUBLIC_ID_PREFIX = "ver_"


def generate_version_public_id() -> str:
    return f"{PUBLIC_ID_PREFIX}{uuid.uuid4().hex[:16]}"


class PresentationVersion(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "presentation_versions"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_version_public_id,
    )
    presentation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("presentations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    slide_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    diff_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[PresentationStatus] = mapped_column(
        String(20),
        nullable=False,
        default=PresentationStatus.DRAFT,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        index=True,
    )

    presentation: Mapped[Presentation] = relationship("Presentation", back_populates="versions")

    __table_args__ = (
        UniqueConstraint(
            "presentation_id",
            "version_number",
            name="uq_presentation_versions_pres_version",
        ),
        Index("ix_presentation_versions_created", "created_at"),
    )
