from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.assistant_conversation import AssistantConversation
    from app.models.generated_lesson import GeneratedLesson

PUBLIC_ID_PREFIX = "actx_"


def generate_context_snapshot_public_id() -> str:
    return f"{PUBLIC_ID_PREFIX}{uuid.uuid4().hex[:16]}"


class AssistantContextSnapshot(Base, UUIDMixin, TimestampMixin):
    """A frozen copy of the context a conversation turn was answered from.

    Prompt construction only ever reads the ``context`` JSON blob, so
    conversations remain reproducible even when the live lesson, progress or
    mastery data changes afterwards. ``prompt_hash`` records the exact prompt
    revision used for auditability.
    """

    __tablename__ = "assistant_context_snapshots"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_context_snapshot_public_id,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("assistant_conversations.id", ondelete="SET NULL"),
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
    session_public_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    slide_position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    block_position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    context_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1")
    prompt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    context: Mapped[dict[str, object]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=False
    )

    conversation: Mapped[AssistantConversation | None] = relationship(
        "AssistantConversation", foreign_keys=[conversation_id]
    )
    lesson: Mapped[GeneratedLesson | None] = relationship(
        "GeneratedLesson", foreign_keys=[lesson_id]
    )

    __table_args__ = (
        Index("ix_assistant_context_snapshots_user_created", "user_id", "created_at"),
        Index("ix_assistant_context_snapshots_conversation", "conversation_id", "created_at"),
        Index("ix_assistant_context_snapshots_lesson", "lesson_id", "created_at"),
    )
