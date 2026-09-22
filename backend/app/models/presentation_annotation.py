"""Per-slide annotation layers bound to a lesson (teaching continuity).

Teacher/learner annotations (strokes, shapes, text) are stored as per-layer
JSON rows instead of reusing the legacy ``bookmarks``/``student_notes`` tables
(migration 0009), which store the opposite direction of data (learner notes
towards a lesson, not overlay marks ON a slide) and do not model a slide
layer. A layer is identified uniquely by
``(user_id, lesson_id, player_mode, slide_index)`` — one row per slide per
view — so the player can restore every view's marks independently.

No HTML/JS is ever rendered from ``items`` server-side; the frontend draws the
payload on a canvas and text is entered/rendered through a textarea + canvas
``fillText`` (no innerHTML injection).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.generated_lesson import GeneratedLesson

PUBLIC_ID_PREFIX = "pann_"


def generate_annotation_public_id() -> str:
    return f"{PUBLIC_ID_PREFIX}{uuid.uuid4().hex[:16]}"


class PresentationAnnotation(Base, UUIDMixin, TimestampMixin):
    """A single annotation layer (all marks on one slide in one view)."""

    __tablename__ = "lesson_annotations"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_annotation_public_id,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )
    lesson_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("generated_lessons.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    player_mode: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        index=True,
    )
    slide_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    items: Mapped[list[dict[str, object]]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        default=list,
        server_default="[]",
    )

    lesson: Mapped[GeneratedLesson | None] = relationship(
        "GeneratedLesson", foreign_keys=[lesson_id]
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "lesson_id",
            "player_mode",
            "slide_index",
            name="uq_lesson_annotations_layer",
        ),
        CheckConstraint(
            "player_mode IN ('source', 'learning', 'visual', 'animation')",
            name="ck_lesson_annotations_player_mode",
        ),
        CheckConstraint(
            "slide_index >= 0",
            name="ck_lesson_annotations_slide_index",
        ),
        Index("ix_lesson_annotations_layer_scan", "user_id", "lesson_id", "player_mode"),
        Index("ix_lesson_annotations_lesson_mode", "lesson_id", "player_mode"),
    )
