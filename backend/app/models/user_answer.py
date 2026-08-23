"""UserAnswer model — maps to the `user_answers` table (migration 0005, renamed 0022)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.database.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    pass


class UserAnswer(Base, UUIDMixin, TimestampMixin):
    """Records the actual answer submitted by a user for a single question."""

    __tablename__ = "user_answers"

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("quiz_attempts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_attempt_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("question_attempts.id", ondelete="CASCADE"),
        nullable=False,
    )
    answer_type: Mapped[str] = mapped_column(String(30), nullable=False)
    option_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    text_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    matching_pairs: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    order_values: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    is_auto_graded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    grading_status: Mapped[str] = mapped_column(String(20), nullable=False, default="auto")
