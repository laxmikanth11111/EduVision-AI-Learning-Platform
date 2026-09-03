from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin
from shared.constants import TutorConversationStatus

if TYPE_CHECKING:
    from app.models.generated_lesson import GeneratedLesson
    from app.models.tutor_message import TutorMessage
    from app.models.tutor_session import TutorSession

PUBLIC_ID_PREFIX = "tuc_"


def generate_tutor_conversation_public_id() -> str:
    return f"{PUBLIC_ID_PREFIX}{uuid.uuid4().hex[:16]}"


class TutorConversation(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    """A continuous tutor conversation within a tutor session (Phase 4E.4, P8).

    Maps the existing ``tutor_conversations`` table (migration 0013). Holds the
    rolling summary and aggregate counters. Messages are hard-cascade children
    (per schema ``ondelete=CASCADE``). Conversations are soft-deleted so history
    can be restored.
    """

    __tablename__ = "tutor_conversations"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_tutor_conversation_public_id,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tutor_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    session_public_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    lesson_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("generated_lessons.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    lesson_public_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=TutorConversationStatus.ACTIVE.value,
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    context_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1")
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    retry_state: Mapped[str] = mapped_column(String(20), nullable=False, default="none")
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    session: Mapped[TutorSession | None] = relationship(
        "TutorSession", foreign_keys=[session_id], back_populates="conversations"
    )
    lesson: Mapped[GeneratedLesson | None] = relationship(
        "GeneratedLesson", foreign_keys=[lesson_id]
    )
    messages: Mapped[list[TutorMessage]] = relationship(
        "TutorMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="TutorMessage.created_at",
    )

    @property
    def status_enum(self) -> TutorConversationStatus:
        return TutorConversationStatus(self.status)

    __table_args__ = (
        Index("ix_tutor_conversations_user_status", "user_id", "status"),
        Index("ix_tutor_conversations_user_updated", "user_id", "updated_at"),
        Index("ix_tutor_conversations_session_status", "session_id", "status"),
        Index("ix_tutor_conversations_lesson", "lesson_id", "status"),
    )
