"""QuestionAttempt model — maps to the `question_attempts` table (migration 0005)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.database.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    pass


class QuestionAttempt(Base, UUIDMixin, TimestampMixin):
    """Tracks the outcome of a single question within an attempt."""

    __tablename__ = "question_attempts"

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("quiz_attempts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="unanswered")
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    points_earned: Mapped[float] = mapped_column(nullable=False, default=0)
    points_possible: Mapped[float] = mapped_column(nullable=False, default=1)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
