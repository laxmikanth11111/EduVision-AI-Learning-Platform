"""ScoreSummary model — maps to the `score_summaries` table (migration 0005)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.database.base import Base, TimestampMixin, UUIDMixin
from app.database.types import PortableJSONB

PUBLIC_ID_PREFIX = "ss_"


def generate_score_summary_public_id() -> str:
    return f"{PUBLIC_ID_PREFIX}{uuid.uuid4().hex[:16]}"


class ScoreSummary(Base, UUIDMixin, TimestampMixin):
    """Aggregate score breakdown for a completed quiz attempt."""

    __tablename__ = "score_summaries"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_score_summary_public_id,
    )
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
    breakdown: Mapped[dict[str, Any] | None] = mapped_column(PortableJSONB, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    graded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    scoring_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
