"""UserAnswer model — maps to the `user_answers` table (migration 0005, renamed 0022)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.database.base import Base, TimestampMixin, UUIDMixin
from app.database.types import PortableJSONB

if TYPE_CHECKING:
    pass


PUBLIC_ID_PREFIX = "ua_"


def generate_user_answer_public_id() -> str:
    return f"{PUBLIC_ID_PREFIX}{uuid.uuid4().hex[:16]}"


class UserAnswer(Base, UUIDMixin, TimestampMixin):
    """Records the actual answer submitted by a user for a single question."""

    __tablename__ = "user_answers"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_user_answer_public_id,
    )
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
        index=True,
    )
    answer_type: Mapped[str] = mapped_column(String(30), nullable=False)
    option_ids: Mapped[list[str] | None] = mapped_column(PortableJSONB, nullable=True)
    text_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    matching_pairs: Mapped[list[dict[str, str]] | None] = mapped_column(
        PortableJSONB, nullable=True
    )
    order_values: Mapped[list[str] | None] = mapped_column(PortableJSONB, nullable=True)
    is_auto_graded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    grading_status: Mapped[str] = mapped_column(String(20), nullable=False, default="auto")
