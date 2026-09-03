from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database.base import Base, TimestampMixin, UUIDMixin
from shared.constants import LearningSessionStatus

if TYPE_CHECKING:
    from app.models.generated_lesson import GeneratedLesson
    from app.models.generated_lesson_version import GeneratedLessonVersion

PUBLIC_ID_PREFIX = "lsess_"

# Terminal states a session can never leave. Every other state may transition
# into one of these; the lifecycle is enforced by ``LearningSessionService``
# (atomically, via ``transition_status``) so a stale client can never corrupt
# history.
TERMINAL_STATES: frozenset[str] = frozenset(
    {
        LearningSessionStatus.COMPLETED.value,
        LearningSessionStatus.EXPIRED.value,
        LearningSessionStatus.CANCELLED.value,
    }
)


def generate_session_public_id() -> str:
    return f"{PUBLIC_ID_PREFIX}{uuid.uuid4().hex[:16]}"


class LearningSession(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "learning_sessions"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_session_public_id,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )
    lesson_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("generated_lessons.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lesson_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("generated_lesson_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=LearningSessionStatus.CREATED.value,
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    device_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    time_limit_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    paused_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_activity_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    current_slide_position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_block_position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_section: Mapped[str | None] = mapped_column(String(200), nullable=True)
    current_block_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    completion_percentage: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_time_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    resume_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    client_metadata: Mapped[dict[str, object] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )

    lesson: Mapped[GeneratedLesson | None] = relationship(
        "GeneratedLesson", foreign_keys=[lesson_id]
    )
    lesson_version: Mapped[GeneratedLessonVersion | None] = relationship(
        "GeneratedLessonVersion", foreign_keys=[lesson_version_id]
    )

    @property
    def status_enum(self) -> LearningSessionStatus:
        return LearningSessionStatus(self.status)

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATES

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_learning_sessions_user_idempotency",
        ),
        Index("ix_learning_sessions_user_status", "user_id", "status"),
        Index("ix_learning_sessions_lesson_status", "lesson_id", "status"),
        Index("ix_learning_sessions_status_updated", "status", "updated_at"),
    )
