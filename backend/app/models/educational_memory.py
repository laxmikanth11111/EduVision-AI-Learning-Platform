from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.user import User

PUBLIC_ID_PREFIX = "emem_"


def generate_educational_memory_public_id() -> str:
    return f"{PUBLIC_ID_PREFIX}{uuid.uuid4().hex[:16]}"


class EducationalMemoryRecord(Base, UUIDMixin, TimestampMixin):
    """Persisted educational memory for a user.

    Stores the full EducationalMemory schema as a JSON blob keyed by user_id.
    One row per user. The JSON structure matches the Pydantic schema:
    profile, concept_records, milestones, preferences, mastered/weak lists, etc.
    """

    __tablename__ = "educational_memories"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_educational_memory_public_id,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    memory_data: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        default=dict,
    )

    user: Mapped[User | None] = relationship(
        "User", foreign_keys=[user_id], lazy="select"
    )

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_educational_memories_user_id"),
        Index("ix_educational_memories_user", "user_id"),
    )
