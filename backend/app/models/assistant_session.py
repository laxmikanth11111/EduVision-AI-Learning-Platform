from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database.base import Base, TimestampMixin, UUIDMixin
from shared.constants import AssistantSessionStatus

if TYPE_CHECKING:
    from app.models.assistant_conversation import AssistantConversation
    from app.models.generated_lesson import GeneratedLesson

PUBLIC_ID_PREFIX = "asess_"


def generate_assistant_session_public_id() -> str:
    return f"{PUBLIC_ID_PREFIX}{uuid.uuid4().hex[:16]}"


class AssistantSession(Base, UUIDMixin, TimestampMixin):
    """A context-scoped AI assistant workspace for a learner (Phase 4D.6).

    Holds the learner's current lesson/slide/block anchor so new conversations
    can be seeded with the right context. One learner may hold multiple active
    sessions (one per lesson). Conversations are soft-deletable children.
    """

    __tablename__ = "assistant_sessions"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_assistant_session_public_id,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )
    lesson_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("generated_lessons.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    session_public_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False, default="AI Assistant")
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=AssistantSessionStatus.ACTIVE.value,
    )
    slide_position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    block_position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    context_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1")
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    conversations: Mapped[list[AssistantConversation]] = relationship(
        "AssistantConversation",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="AssistantConversation.created_at",
    )
    lesson: Mapped[GeneratedLesson | None] = relationship(
        "GeneratedLesson", foreign_keys=[lesson_id]
    )

    @property
    def status_enum(self) -> AssistantSessionStatus:
        return AssistantSessionStatus(self.status)

    __table_args__ = (
        Index("ix_assistant_sessions_user_status", "user_id", "status"),
        Index("ix_assistant_sessions_user_updated", "user_id", "updated_at"),
        Index("ix_assistant_sessions_lesson", "lesson_id", "status"),
    )
