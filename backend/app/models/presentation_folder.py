from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.presentation import Presentation


class PresentationFolder(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "presentation_folders"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        index=True,
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("presentation_folders.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    parent: Mapped[PresentationFolder | None] = relationship(
        "PresentationFolder",
        remote_side="PresentationFolder.id",
        back_populates="children",
    )
    children: Mapped[list[PresentationFolder]] = relationship(
        "PresentationFolder",
        back_populates="parent",
        cascade="all, delete-orphan",
    )
    presentations: Mapped[list[Presentation]] = relationship(
        "Presentation", back_populates="folder"
    )

    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "parent_id",
            "name",
            name="uq_presentation_folders_sibling",
        ),
        Index("ix_presentation_folders_owner_parent", "owner_id", "parent_id"),
    )
