from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database.base import Base, TimestampMixin, UUIDMixin
from shared.constants import AssistantMessageRole, AssistantMessageStatus

if TYPE_CHECKING:
    from app.models.assistant_conversation import AssistantConversation

PUBLIC_ID_PREFIX = "amsg_"


def generate_message_public_id() -> str:
    return f"{PUBLIC_ID_PREFIX}{uuid.uuid4().hex[:16]}"


class AssistantMessage(Base, UUIDMixin, TimestampMixin):
    """A single user/assistant turn inside an assistant conversation.

    ``content`` is always sanitized before storage. AI responses additionally
    record the provider/model and token usage so cost and quality can be
    audited per conversation. ``client_message_id`` supports idempotent
    re-submission of the same user turn (replay protection).
    """

    __tablename__ = "assistant_messages"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_message_public_id,
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("assistant_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=AssistantMessageStatus.PENDING.value,
    )
    client_message_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    message_metadata: Mapped[dict[str, object] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )

    conversation: Mapped[AssistantConversation] = relationship(
        "AssistantConversation", foreign_keys=[conversation_id], back_populates="messages"
    )

    @property
    def role_enum(self) -> AssistantMessageRole:
        return AssistantMessageRole(self.role)

    @property
    def status_enum(self) -> AssistantMessageStatus:
        return AssistantMessageStatus(self.status)

    __table_args__ = (
        Index("ix_assistant_messages_conversation_created", "conversation_id", "created_at"),
        Index("ix_assistant_messages_user_created", "user_id", "created_at"),
        Index("ix_assistant_messages_client_id", "conversation_id", "client_message_id"),
    )
