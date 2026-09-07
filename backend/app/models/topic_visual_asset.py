"""SQLAlchemy 2.0 Models for Checkpoint C3 — Topic-Level Visual Assets.

Extends the Phase 4I visual_knowledge_graph models with topic/subtopic-driven
visual assets that carry specifications, explanations, provenance, and lifecycle state.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import JSON, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.database.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin


def generate_visual_asset_public_id() -> str:
    return f"c3v_{uuid.uuid4().hex[:16]}"


class TopicVisualAsset(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    """A generated visual asset associated with a topic/subtopic."""

    __tablename__ = "topic_visual_assets"

    public_id: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
        default=generate_visual_asset_public_id,
    )
    presentation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("presentations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )
    topic_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    topic_title: Mapped[str] = mapped_column(String(500), nullable=False)
    subtopic_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    subtopic_title: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Visual specification and lifecycle
    visual_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="planned", index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Generated asset
    asset_format: Mapped[str] = mapped_column(String(16), nullable=False, default="svg")
    asset_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    asset_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    asset_content: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Educational content
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False, default="")
    learning_objective: Mapped[str] = mapped_column(Text, nullable=False, default="")
    provenance: Mapped[str] = mapped_column(String(32), nullable=False, default="ai_explained")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.8)

    # Structured JSON fields
    specification: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        default=dict,
    )
    explanation: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        default=dict,
    )
    source_references: Mapped[list[Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        default=list,
    )
    concept_ids: Mapped[list[Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        default=list,
    )
    generation_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        default=dict,
    )

    # Error handling
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("ix_topic_visual_assets_pres_topic", "presentation_id", "topic_id"),
        Index("ix_topic_visual_assets_pres_subtopic", "presentation_id", "subtopic_id"),
        Index("ix_topic_visual_assets_status_version", "status", "version"),
    )
