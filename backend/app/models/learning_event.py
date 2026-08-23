"""LearningEvent model — append-only event stream for learning activity tracking."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.database.base import Base, TimestampMixin, UUIDMixin

PUBLIC_ID_PREFIX = "levt_"


def generate_event_public_id() -> str:
    return f"{PUBLIC_ID_PREFIX}{uuid.uuid4().hex[:16]}"


class LearningEvent(Base, UUIDMixin, TimestampMixin):
    """Append-only record of a meaningful learning activity."""

    __tablename__ = "learning_events"

    public_id: Mapped[str] = mapped_column(
        String(40), unique=True, nullable=False, index=True,
        default=generate_event_public_id,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True,
    )
    resource_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    concept_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    presentation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True,
    )
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index("ix_learning_events_user_type", "user_id", "event_type"),
        Index("ix_learning_events_user_occurred", "user_id", "occurred_at"),
        Index("ix_learning_events_presentation", "presentation_id"),
    )
