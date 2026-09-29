"""Question and QuestionOption models — maps to `questions` and `question_options` tables."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database.base import Base, TimestampMixin, UUIDMixin
from app.database.types import PortableJSONB

if TYPE_CHECKING:
    pass


class Question(Base, UUIDMixin, TimestampMixin):
    """A single question inside a quiz version."""

    __tablename__ = "questions"

    public_id: Mapped[str] = mapped_column(
        String(40), unique=True, nullable=False, index=True,
        default=lambda: f"q_{uuid.uuid4().hex[:16]}",
    )
    quiz_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("quiz_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    question_type: Mapped[str] = mapped_column(String(30), nullable=False, default="multiple_choice")
    stem: Mapped[str] = mapped_column(Text, nullable=False)
    bloom_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    difficulty: Mapped[str | None] = mapped_column(String(20), nullable=True)
    points: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    scenario_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    concept_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("concepts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    meta: Mapped[dict[str, Any] | None] = mapped_column(PortableJSONB, nullable=True)

    options: Mapped[list[QuestionOption]] = relationship(
        "QuestionOption",
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="QuestionOption.position",
    )

    __table_args__ = (
        Index("uq_questions_version_position", "quiz_version_id", "position", unique=True),
    )


class QuestionOption(Base, TimestampMixin):
    """A single answer option for a question."""

    __tablename__ = "question_options"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    public_id: Mapped[str] = mapped_column(
        String(40), unique=True, nullable=False, index=True,
        default=lambda: f"opt_{uuid.uuid4().hex[:16]}",
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    meta: Mapped[dict[str, Any] | None] = mapped_column(PortableJSONB, nullable=True)

    question: Mapped[Question] = relationship("Question", foreign_keys=[question_id], back_populates="options")
