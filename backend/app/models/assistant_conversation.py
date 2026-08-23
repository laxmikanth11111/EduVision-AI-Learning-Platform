from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.assistant_message import AssistantMessage
    from app.models.assistant_session import AssistantSession

PUBLIC_ID_PREFIX = "aconv_"


def generate_conversation_public_id() -> str:
    return f"{PUBLIC_ID_PREFIX}{uuid.uuid4().hex[:16]}"


class AssistantConversation(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    """A bounded AI assistant conversation thread (Phase 4D.6).

    Conversations are soft-deleted so history can be restored. Each
    conversation pins the lesson/slide/block anchor it was started from and
    the context version that anchored its first message. ``summary`` is
    produced asynchronously by the conversation-summary worker.
    """

    __tablename__ = "assistant_conversations"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_conversation_public_id,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("assistant_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    lesson_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("generated_lessons.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    session_public_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    lesson_public_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    slide_position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    block_position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    context_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1")
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    session: Mapped[AssistantSession | None] = relationship(
        "AssistantSession", foreign_keys=[session_id], back_populates="conversations"
    )
    messages: Mapped[list[AssistantMessage]] = relationship(
        "AssistantMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="AssistantMessage.created_at",
    )

    __table_args__ = (
        Index("ix_assistant_conversations_user_status", "user_id", "status"),
        Index("ix_assistant_conversations_user_updated", "user_id", "updated_at"),
        Index("ix_assistant_conversations_session", "session_id", "status"),
        Index("ix_assistant_conversations_lesson", "lesson_id", "status"),
    )
