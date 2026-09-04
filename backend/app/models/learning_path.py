"""Personalised learning path (P11).

Backs the deterministic learning-path capability over the ``learning_paths``
table first created by migration ``0011_personalized_learning`` (schema-only
stub with no ORM model; P11 adds the model without modifying the table).

The path is a versioned, learner-owned ordered sequence of lessons
(``sequence`` JSONB of lesson public ids) with a ``current_position`` and
``progress_percent``. Mastery/review state remains the single source of
truth — the path is a deterministic read-composition over it, never a second
scheduler.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.user import User

PUBLIC_ID_PREFIX = "path_"


def generate_learning_path_public_id() -> str:
    return f"{PUBLIC_ID_PREFIX}{uuid.uuid4().hex[:16]}"


class LearningPath(Base, UUIDMixin, TimestampMixin):
    """A learner-owned, ordered, versioned sequence of lessons."""

    __tablename__ = "learning_paths"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_learning_path_public_id,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    sequence: Mapped[list[Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    config: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    current_position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_percent: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    context_version: Mapped[str] = mapped_column(
        String(32), nullable=False, default="1"
    )

    user: Mapped[User | None] = relationship(
        "User", foreign_keys=[user_id], lazy="select"
    )

    @property
    def lesson_count(self) -> int:
        return len(self.sequence or [])

    @property
    def is_active(self) -> bool:
        return self.status == "active"
