"""QuestionExplanation model — maps to the `question_explanations` table (migration 0005)."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.database.base import Base, TimestampMixin, UUIDMixin


class QuestionExplanation(Base, UUIDMixin, TimestampMixin):
    """Explanation text for a question, shown after submission."""

    __tablename__ = "question_explanations"

    question_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    display_timing: Mapped[str] = mapped_column(String(20), nullable=False, default="after_submit")
