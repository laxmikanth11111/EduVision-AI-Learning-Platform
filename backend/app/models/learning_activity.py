from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDMixin
from shared.constants import LearningActivityType

if TYPE_CHECKING:
    from app.models.generated_lesson import GeneratedLesson
    from app.models.generated_lesson_version import GeneratedLessonVersion

PUBLIC_ID_PREFIX = "lact_"


def generate_activity_public_id() -> str:
    return f"{PUBLIC_ID_PREFIX}{uuid.uuid4().hex[:16]}"


class LearningActivity(Base, UUIDMixin, TimestampMixin):
    """An interactive learning activity embedded in a lesson (Phase 4D.4).

    The row is content, not learner state: it binds an activity to a lesson
    (and optionally the lesson version it was authored against) at a block/slide
    position. ``config`` holds everything the attempt evaluator needs
    (options, accepted answers, matching pairs, ordering, rubric), while
    ``topics``/``concepts``/``learning_objectives`` feed the adaptive engine.
    """

    __tablename__ = "learning_activities"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_activity_public_id,
    )
    lesson_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("generated_lessons.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lesson_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("generated_lesson_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    block_position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    slide_position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    section: Mapped[str | None] = mapped_column(String(200), nullable=True)
    activity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    config: Mapped[dict[str, object] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False, default="beginner")
    bloom_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    topics: Mapped[list[str] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )
    concepts: Mapped[list[str] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )
    learning_objectives: Mapped[list[str] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )
    estimated_duration_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=120
    )
    scoring_model: Mapped[str] = mapped_column(String(30), nullable=False, default="exact")
    is_optional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    requires_explanation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    lesson: Mapped[GeneratedLesson | None] = relationship(
        "GeneratedLesson", foreign_keys=[lesson_id]
    )
    lesson_version: Mapped[GeneratedLessonVersion | None] = relationship(
        "GeneratedLessonVersion", foreign_keys=[lesson_version_id]
    )
    @property
    def activity_type_enum(self) -> LearningActivityType:
        return LearningActivityType(self.activity_type)

    __table_args__ = (
        Index("ix_learning_activities_lesson_type", "lesson_id", "activity_type"),
        Index("ix_learning_activities_version_position", "lesson_version_id", "block_position"),
    )
