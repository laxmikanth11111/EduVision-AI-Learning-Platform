from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDMixin
from shared.constants import (
    LearningMode,
    LessonDifficulty,
    LessonVersionStatus,
)

if TYPE_CHECKING:
    from app.models.generated_block import GeneratedBlock
    from app.models.generated_lesson import GeneratedLesson

PUBLIC_ID_PREFIX = "lessver_"


def generate_version_public_id() -> str:
    return f"{PUBLIC_ID_PREFIX}{uuid.uuid4().hex[:16]}"


class GeneratedLessonVersion(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "generated_lesson_versions"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_version_public_id,
    )
    lesson_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("generated_lessons.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=LessonVersionStatus.SUCCEEDED.value,
    )
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    difficulty: Mapped[str | None] = mapped_column(String(20), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(30), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payload_schema_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    generation_metadata: Mapped[dict[str, object] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    provider_retry_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_issues: Mapped[dict[str, object] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )
    quality_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    quality_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    prompt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    lesson: Mapped[GeneratedLesson] = relationship(
        "GeneratedLesson", back_populates="versions"
    )
    blocks: Mapped[list[GeneratedBlock]] = relationship(
        "GeneratedBlock",
        back_populates="lesson_version",
        cascade="all, delete-orphan",
        order_by="GeneratedBlock.position",
    )

    @property
    def status_enum(self) -> LessonVersionStatus:
        return LessonVersionStatus(self.status)

    @property
    def mode_enum(self) -> LearningMode:
        return LearningMode(self.lesson.mode)

    @property
    def difficulty_enum(self) -> LessonDifficulty | None:
        return LessonDifficulty(self.difficulty) if self.difficulty else None

    __table_args__ = (
        UniqueConstraint(
            "lesson_id",
            "version",
            name="uq_generated_lesson_versions_lesson_version",
        ),
        Index("ix_generated_lesson_versions_lesson_id_version", "lesson_id", "version"),
    )
