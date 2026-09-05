"""QuizAttempt model — maps to the `quiz_attempts` table (migration 0005)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.database.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    pass

PUBLIC_ID_PREFIX = "qatt_"


def generate_attempt_public_id() -> str:
    return f"{PUBLIC_ID_PREFIX}{uuid.uuid4().hex[:16]}"


class QuizAttempt(Base, UUIDMixin, TimestampMixin):
    """A single user attempt on a quiz."""

    __tablename__ = "quiz_attempts"

    public_id: Mapped[str] = mapped_column(
        String(40), unique=True, nullable=False, index=True,
        default=generate_attempt_public_id,
    )
    quiz_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("quizzes.id", ondelete="CASCADE"),
        nullable=False,
    )
    quiz_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("quiz_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="in_progress")
    score: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    max_score: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False, default=0)
    percent_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    time_spent_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_practice: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    adaptive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_quiz_attempts_quiz_user", "quiz_id", "user_id"),
        Index("ix_quiz_attempts_status", "status"),
    )
