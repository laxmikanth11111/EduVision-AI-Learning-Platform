"""ScoreSummary model — maps to the `score_summaries` table (migration 0005)."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.database.base import Base, TimestampMixin, UUIDMixin
from app.database.types import PortableJSONB


class ScoreSummary(Base, UUIDMixin, TimestampMixin):
    """Aggregate score breakdown for a completed quiz attempt."""

    __tablename__ = "score_summaries"

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("quiz_attempts.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    total_points: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False, default=0)
    earned_points: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False, default=0)
    percent: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    incorrect_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    partially_correct_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unanswered_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    breakdown: Mapped[dict | None] = mapped_column(PortableJSONB, nullable=True)
