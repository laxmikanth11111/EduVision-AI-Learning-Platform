"""Quiz model — maps to the `quizzes` table (migration 0005)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.quiz_version import QuizVersion

PUBLIC_ID_PREFIX = "quiz_"


def generate_quiz_public_id() -> str:
    return f"{PUBLIC_ID_PREFIX}{uuid.uuid4().hex[:16]}"


class Quiz(Base, UUIDMixin, TimestampMixin):
    """A quiz attached to a presentation."""

    __tablename__ = "quizzes"

    public_id: Mapped[str] = mapped_column(
        String(40), unique=True, nullable=False, index=True,
        default=generate_quiz_public_id,
    )
    presentation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("presentations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    lesson_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("generated_lessons.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    lesson_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("generated_lesson_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="practice")
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    difficulty: Mapped[str | None] = mapped_column(String(20), nullable=True)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    passing_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    time_limit_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shuffle_questions: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    shuffle_options: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    show_feedback_after: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    max_attempts_per_user: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    latest_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    published_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    question_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    retry_state: Mapped[str] = mapped_column(String(20), nullable=False, default="idle")
    assessment_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="normal",
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    versions: Mapped[list[QuizVersion]] = relationship(
        "QuizVersion",
        back_populates="quiz",
        cascade="all, delete-orphan",
        order_by="QuizVersion.version.desc()",
    )

    __table_args__ = (
        Index("ix_quizzes_presentation_status", "presentation_id", "status"),
    )
