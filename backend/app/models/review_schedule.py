"""Spaced-repetition review schedule (P10).

Backs the deterministic review/scheduler that turns mastery + time into an
actionable, per-learner review queue. The table ``review_schedules`` was first
created by migration ``0011_personalized_learning`` (schema-only stub with no
ORM model); P10 adds the ORM model plus the ``concept_id`` and
``last_reviewed_at`` columns via the additive migration
``0031_review_schedule_concept``.

Learnability/ownership rules:
  - Every row is learner-owned (``user_id``, FK CASCADE).
  - ``concept_id`` is the concept being reviewed (nullable to preserve
    pre-P10 rows; new rows always set it).
  - ``lesson_id`` optionally scopes the review to a lesson (nullable).
  - ``topic`` stores the human-readable concept name for legacy compatibility.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.concept import Concept
    from app.models.generated_lesson import GeneratedLesson
    from app.models.user import User

PUBLIC_ID_PREFIX = "rev_"


def generate_review_schedule_public_id() -> str:
    return f"{PUBLIC_ID_PREFIX}{uuid.uuid4().hex[:16]}"


class ReviewSchedule(Base, UUIDMixin, TimestampMixin):
    """A concept scheduled for spaced review for a learner."""

    __tablename__ = "review_schedules"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_review_schedule_public_id,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lesson_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("generated_lessons.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    concept_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("concepts.id", ondelete="SET NULL"),
        nullable=True,
    )
    topic: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="scheduled")
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False)
    interval_days: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    mastery_at_schedule: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    review_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )

    user: Mapped[User | None] = relationship(
        "User", foreign_keys=[user_id], lazy="select"
    )
    lesson: Mapped[GeneratedLesson | None] = relationship(
        "GeneratedLesson", foreign_keys=[lesson_id], lazy="select"
    )
    concept: Mapped[Concept | None] = relationship(
        "Concept", foreign_keys=[concept_id], lazy="select"
    )

    __table_args__ = (
        Index("ix_review_schedules_user_due", "user_id", "due_at"),
        Index("ix_review_schedules_concept_id", "concept_id"),
    )
