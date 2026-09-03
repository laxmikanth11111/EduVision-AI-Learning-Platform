from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin
from shared.constants import TutorSessionStatus

if TYPE_CHECKING:
    from app.models.generated_lesson import GeneratedLesson
    from app.models.presentation import Presentation
    from app.models.tutor_conversation import TutorConversation

PUBLIC_ID_PREFIX = "tus_"


def generate_tutor_session_public_id() -> str:
    return f"{PUBLIC_ID_PREFIX}{uuid.uuid4().hex[:16]}"


class TutorSession(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    """A mastery-aware AI tutor workspace (Phase 4E.4, P8).

    Maps the existing ``tutor_sessions`` table (migration 0013). A session
    anchors tutoring to a presentation/lesson (and, in P8, a weak target
    concept). Conversations are soft-deletable children; aggregate token and
    message counters are maintained on the row for cheap listing.
    """

    __tablename__ = "tutor_sessions"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_tutor_session_public_id,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    presentation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("presentations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    lesson_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("generated_lessons.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    lesson_public_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    target_concept_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False, default="AI Tutor")
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=TutorSessionStatus.ACTIVE.value,
    )
    mode: Mapped[str] = mapped_column(String(30), nullable=False, default="interactive")
    difficulty: Mapped[str | None] = mapped_column(String(20), nullable=True)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    context_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1")
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    retry_state: Mapped[str] = mapped_column(String(20), nullable=False, default="none")
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    presentations: Mapped[Presentation | None] = relationship(
        "Presentation", foreign_keys=[presentation_id]
    )
    lesson: Mapped[GeneratedLesson | None] = relationship(
        "GeneratedLesson", foreign_keys=[lesson_id]
    )
    conversations: Mapped[list[TutorConversation]] = relationship(
        "TutorConversation",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="TutorConversation.created_at",
    )

    @property
    def status_enum(self) -> TutorSessionStatus:
        return TutorSessionStatus(self.status)

    __table_args__ = (
        Index("ix_tutor_sessions_user_status", "user_id", "status"),
        Index("ix_tutor_sessions_user_updated", "user_id", "updated_at"),
        Index("ix_tutor_sessions_lesson", "lesson_id", "status"),
    )
