from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid

from app.database.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin
from shared.constants import TutorConfidenceLevel, TutorMessageStatus, TutorSourceKind

if TYPE_CHECKING:
    from app.models.tutor_conversation import TutorConversation

PUBLIC_ID_PREFIX = "tum_"


def generate_tutor_message_public_id() -> str:
    return f"{PUBLIC_ID_PREFIX}{uuid.uuid4().hex[:16]}"


class TutorMessage(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    """A single sanitized user/assistant turn in a tutor conversation.

    Maps the existing ``tutor_messages`` table (migration 0013). In addition to
    the auditable model/provider/token/latency/retrieval metadata, P8 adds three
    columns that make every answer truthful: ``source_kind`` (``rag`` vs
    ``deterministic``), ``attribution`` (the learner-owned source material name)
    and ``confidence`` (``high``/``medium``/``low``). ``content`` is always
    sanitized before storage.
    """

    __tablename__ = "tutor_messages"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_tutor_message_public_id,
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tutor_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=TutorMessageStatus.PENDING.value,
    )
    client_message_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retrieval_metadata: Mapped[dict[str, object] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    answer_metadata: Mapped[dict[str, object] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    source_kind: Mapped[str | None] = mapped_column(String(30), nullable=True)
    attribution: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(20), nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    retry_state: Mapped[str] = mapped_column(String(20), nullable=False, default="none")
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    conversation: Mapped[TutorConversation] = relationship(
        "TutorConversation", foreign_keys=[conversation_id], back_populates="messages"
    )

    @property
    def status_enum(self) -> TutorMessageStatus:
        return TutorMessageStatus(self.status)

    @property
    def confidence_enum(self) -> TutorConfidenceLevel | None:
        return TutorConfidenceLevel(self.confidence) if self.confidence else None

    @property
    def source_kind_enum(self) -> TutorSourceKind | None:
        return TutorSourceKind(self.source_kind) if self.source_kind else None

    __table_args__ = (
        Index("ix_tutor_messages_conversation_created", "conversation_id", "created_at"),
        Index("ix_tutor_messages_user_created", "user_id", "created_at"),
        Index("ix_tutor_messages_client_id", "conversation_id", "client_message_id"),
    )
