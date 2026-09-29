from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database.base import SoftDeletableBaseModel
from shared.constants import PresentationStatus, PresentationVisibility

if TYPE_CHECKING:
    from app.models.content_unit import ContentUnit
    from app.models.presentation_analytics import PresentationAnalytics
    from app.models.presentation_audit_log import PresentationAuditLog
    from app.models.presentation_folder import PresentationFolder
    from app.models.presentation_tag import PresentationTag
    from app.models.presentation_version import PresentationVersion
    from app.models.topic_outline import TopicOutline

PUBLIC_ID_PREFIX = "pres_"


def generate_presentation_public_id() -> str:
    return f"{PUBLIC_ID_PREFIX}{uuid.uuid4().hex[:16]}"


class Presentation(SoftDeletableBaseModel):
    __tablename__ = "presentations"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_presentation_public_id,
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Backed by a plain String(20) column, so reads and writes are text, not
    # enum members. PresentationStatus is a str-mixin enum and every call site
    # uses `.value`, so this is annotated as str to match what the database
    # actually returns.
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=PresentationStatus.DRAFT,
        index=True,
    )
    topic: Mapped[str | None] = mapped_column(String(300), nullable=True)
    visibility: Mapped[PresentationVisibility] = mapped_column(
        String(20),
        nullable=False,
        default=PresentationVisibility.PRIVATE,
        index=True,
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        index=True,
    )
    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("presentation_folders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    slide_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    file_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    thumbnail_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    subject_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    subject_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    grade_level: Mapped[str | None] = mapped_column(String(50), nullable=True)
    extraction_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="none",
        index=True,
    )
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extraction_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    folder: Mapped[PresentationFolder | None] = relationship(
        "PresentationFolder", back_populates="presentations"
    )
    versions: Mapped[list[PresentationVersion]] = relationship(
        "PresentationVersion",
        back_populates="presentation",
        cascade="all, delete-orphan",
    )
    analytics: Mapped[PresentationAnalytics | None] = relationship(
        "PresentationAnalytics",
        back_populates="presentation",
        cascade="all, delete-orphan",
        uselist=False,
    )
    tags: Mapped[list[PresentationTag]] = relationship(
        "PresentationTag",
        back_populates="presentation",
        cascade="all, delete-orphan",
    )
    audit_logs: Mapped[list[PresentationAuditLog]] = relationship(
        "PresentationAuditLog",
        back_populates="presentation",
        cascade="all, delete-orphan",
    )
    content_units: Mapped[list[ContentUnit]] = relationship(
        "ContentUnit",
        back_populates="presentation",
        cascade="all, delete-orphan",
        order_by="ContentUnit.position",
    )
    topic_outline: Mapped[TopicOutline | None] = relationship(
        "TopicOutline",
        back_populates="presentation",
        cascade="all, delete-orphan",
        uselist=False,
    )

    __table_args__ = (
        Index("ix_presentations_owner_status", "owner_id", "status"),
        Index("ix_presentations_title", "title"),
        Index("ix_presentations_topic", "topic"),
    )
