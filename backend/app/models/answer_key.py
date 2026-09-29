"""AnswerKey model — maps to the `answer_keys` table (migration 0005)."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.database.base import Base, TimestampMixin, UUIDMixin
from app.database.types import PortableJSONB


class AnswerKey(Base, UUIDMixin, TimestampMixin):
    """Type-specific answer key per question."""

    __tablename__ = "answer_keys"

    question_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    answer_type: Mapped[str] = mapped_column(String(30), nullable=False)
    correct_option_ids: Mapped[list[str] | None] = mapped_column(
        PortableJSONB, nullable=True
    )
    correct_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    acceptable_answers: Mapped[list[str] | None] = mapped_column(
        PortableJSONB, nullable=True
    )
    matching_pairs: Mapped[list[dict[str, str]] | None] = mapped_column(
        PortableJSONB, nullable=True
    )
    correct_order: Mapped[list[str] | None] = mapped_column(PortableJSONB, nullable=True)
    scoring_rule: Mapped[str | None] = mapped_column(String(20), nullable=True)
    points_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
    case_sensitive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
