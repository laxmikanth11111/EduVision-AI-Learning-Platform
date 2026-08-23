from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database.base import Base, TimestampMixin, UUIDMixin
from shared.constants import (
    LearningMode,
    LessonDifficulty,
    LessonRetryState,
    LessonStatus,
)

if TYPE_CHECKING:
    from app.models.generated_lesson_version import GeneratedLessonVersion
    from app.models.presentation import Presentation

PUBLIC_ID_PREFIX = "lesson_"


def generate_lesson_public_id() -> str:
    return f"{PUBLIC_ID_PREFIX}{uuid.uuid4().hex[:16]}"


class GeneratedLesson(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "generated_lessons"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_lesson_public_id,
    )
    presentation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("presentations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        index=True,
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=LessonStatus.QUEUED.value)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    difficulty: Mapped[str | None] = mapped_column(String(20), nullable=True)
    model_override: Mapped[str | None] = mapped_column(String(100), nullable=True)
    latest_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    retry_state: Mapped[str] = mapped_column(
        String(20), nullable=False, default=LessonRetryState.NONE.value
    )

    versions: Mapped[list[GeneratedLessonVersion]] = relationship(
        "GeneratedLessonVersion",
        back_populates="lesson",
        cascade="all, delete-orphan",
        order_by="GeneratedLessonVersion.version",
    )
    presentation: Mapped[Presentation] = relationship(
        "Presentation", foreign_keys=[presentation_id]
    )

    @property
    def mode_enum(self) -> LearningMode:
        return LearningMode(self.mode)

    @property
    def status_enum(self) -> LessonStatus:
        return LessonStatus(self.status)

    @property
    def difficulty_enum(self) -> LessonDifficulty | None:
        return LessonDifficulty(self.difficulty) if self.difficulty else None

    @property
    def retry_state_enum(self) -> LessonRetryState:
        return LessonRetryState(self.retry_state)

    def schedule_retry(self, next_retry_at: datetime, max_attempts: int) -> None:
        self.attempt_count += 1
        self.max_attempts = max_attempts
        self.next_retry_at = next_retry_at
        self.retry_state = LessonRetryState.SCHEDULED.value

    def mark_failed_permanent(self) -> None:
        self.retry_state = LessonRetryState.EXHAUSTED.value
        self.next_retry_at = None

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_generated_lessons_user_idempotency",
        ),
        Index("ix_generated_lessons_mode", "mode"),
        Index("ix_generated_lessons_status", "status"),
    )
