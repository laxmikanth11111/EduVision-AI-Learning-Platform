"""UserFeedback model — optional learner feedback after learning."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.database.base import Base, TimestampMixin, UUIDMixin
from app.database.types import PortableJSONB

PUBLIC_ID_PREFIX = "ufbk_"


def generate_feedback_public_id() -> str:
    return f"{PUBLIC_ID_PREFIX}{uuid.uuid4().hex[:16]}"


class UserFeedback(Base, UUIDMixin, TimestampMixin):
    """Optional feedback a learner provides after a learning experience."""

    __tablename__ = "user_feedback"

    public_id: Mapped[str] = mapped_column(
        String(40), unique=True, nullable=False, index=True,
        default=generate_feedback_public_id,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    presentation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, index=True,
    )
    assessment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True,
    )

    perceived_understanding: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    usefulness: Mapped[int | None] = mapped_column(Integer, nullable=True)
    visual_usefulness: Mapped[int | None] = mapped_column(Integer, nullable=True)
    animation_usefulness: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tutor_usefulness: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recommendation_usefulness: Mapped[int | None] = mapped_column(Integer, nullable=True)
    overall_experience: Mapped[int | None] = mapped_column(Integer, nullable=True)

    qualitative_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_json: Mapped[dict[str, Any] | None] = mapped_column(PortableJSONB, nullable=True)
