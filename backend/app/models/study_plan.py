"""Dated study plan (P11).

Backs the Today/study-plan capability over the ``study_plans`` table first
created by migration ``0011_personalized_learning`` (schema-only stub; P11 adds
the ORM model without modifying the table).

A plan holds dated per-day items in the ``days`` JSONB (each day is a list of
item dicts with ``item_key``/``item_type``/``title``/``reason``/``priority``/
``deep_link``/``status`` and optional anchors). Plans are deterministic
read-compositions over live mastery/review state: completing an item routes
through the existing review/lesson flows, so the plan never drifts from the
learner's true state.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.user import User

PUBLIC_ID_PREFIX = "plan_"


def generate_study_plan_public_id() -> str:
    return f"{PUBLIC_ID_PREFIX}{uuid.uuid4().hex[:16]}"


class StudyPlan(Base, UUIDMixin, TimestampMixin):
    """A learner-owned dated plan of review/practice/lesson items."""

    __tablename__ = "study_plans"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_study_plan_public_id,
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
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    days: Mapped[dict[str, list[dict[str, Any]]] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    days_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped[User | None] = relationship(
        "User", foreign_keys=[user_id], lazy="select"
    )

    @property
    def is_active(self) -> bool:
        return self.status == "active"

    @property
    def progress_percent(self) -> float:
        if not self.total_items:
            return 0.0
        return min(100.0, max(0.0, (float(self.completed_items) / float(self.total_items)) * 100.0))
