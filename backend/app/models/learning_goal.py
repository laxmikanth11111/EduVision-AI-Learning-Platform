"""Measurable learner goal (P11).

Backs the goals capability over the ``learning_goals`` table first created by
migration ``0011_personalized_learning`` (schema-only stub; P11 adds the ORM
model without modifying the table).

Progress is always *derived* from live activity on read — the stored
``current_value`` is a denormalised snapshot updated by the goal service and
never submitted by the client. Mastery/lesson/streak state stays the single
source of truth.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.user import User

PUBLIC_ID_PREFIX = "goal_"


def generate_learning_goal_public_id() -> str:
    return f"{PUBLIC_ID_PREFIX}{uuid.uuid4().hex[:16]}"


class LearningGoal(Base, UUIDMixin, TimestampMixin):
    """A learner-owned measurable goal with derived progress."""

    __tablename__ = "learning_goals"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_learning_goal_public_id,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    path_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("learning_paths.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    goal_type: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    achieved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    progress_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )

    user: Mapped[User | None] = relationship(
        "User", foreign_keys=[user_id], lazy="select"
    )

    @property
    def is_active(self) -> bool:
        return self.status == "active"

    @property
    def progress_percent(self) -> float:
        """Progress toward the target, derived at read time (0..100)."""
        if not self.target_value or self.target_value <= 0:
            return 0.0
        return min(100.0, max(0.0, (float(self.current_value) / float(self.target_value)) * 100.0))
