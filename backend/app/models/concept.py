from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.presentation import Presentation

PUBLIC_ID_PREFIX = "concept_"


def generate_concept_public_id() -> str:
    return f"{PUBLIC_ID_PREFIX}{uuid.uuid4().hex[:16]}"


class Concept(Base, UUIDMixin, TimestampMixin):
    """A discrete, named learning concept.

    Concepts are the atomic units of knowledge that quizzes measure,
    mastery tracks, and the AI tutor references.  A concept belongs
    to a topic and optionally to a presentation (source material).
    """

    __tablename__ = "concepts"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_concept_public_id,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    topic: Mapped[str | None] = mapped_column(String(200), nullable=True)
    presentation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("presentations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    lesson_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("generated_lessons.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    difficulty_level: Mapped[str] = mapped_column(String(20), nullable=False, default="intermediate")
    prerequisites: Mapped[list[str] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    source_references: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")

    presentation: Mapped[Presentation | None] = relationship(
        "Presentation", foreign_keys=[presentation_id], lazy="select"
    )

    __table_args__ = (
        UniqueConstraint("presentation_id", "name", name="uq_concepts_presentation_name"),
        Index("ix_concepts_topic", "topic"),
    )
