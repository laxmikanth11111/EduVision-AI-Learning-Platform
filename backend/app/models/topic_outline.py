from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.presentation import Presentation

PUBLIC_ID_PREFIX = "outline_"


def generate_topic_outline_public_id() -> str:
    return f"{PUBLIC_ID_PREFIX}{uuid.uuid4().hex[:16]}"


class TopicOutline(Base, UUIDMixin, TimestampMixin):
    """Structured topic outline produced by an LLM pass over extracted content.

    One outline per presentation (unique ``presentation_id``). The ``topics``
    JSONB column stores the outline contract consumed both by the topics page
    and by lesson generation::

        [{"title": str, "slide_ranges": [start, end]}]

    ``slide_ranges`` are 1-based, inclusive unit positions into the
    presentation's extracted ``ContentUnit`` rows.
    """

    __tablename__ = "topic_outlines"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_topic_outline_public_id,
    )
    presentation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("presentations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    topics: Mapped[list[dict[str, object]] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
        default=list,
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="succeeded"
    )
    provider: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(Text, nullable=True)

    presentation: Mapped[Presentation] = relationship(
        "Presentation", back_populates="topic_outline"
    )
