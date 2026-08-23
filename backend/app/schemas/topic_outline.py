from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

OutlineStatus = Literal["none", "succeeded", "failed"]


class OutlineTopic(BaseModel):
    """A single topic in a structured outline.

    ``slide_ranges`` is a 1-based, inclusive pair of extracted-unit positions
    ``[start, end]`` covering the topic's slides in the source deck.
    """

    title: str = Field(min_length=1, max_length=500)
    slide_ranges: list[int] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def _validate_ranges(self) -> OutlineTopic:
        start, end = self.slide_ranges
        if start < 1 or end < start:
            raise ValueError(
                "slide_ranges must be [start, end] with start >= 1 and end >= start"
            )
        return self


class TopicOutlinePayload(BaseModel):
    """LLM output contract for the topic outline pass."""

    title: str = Field(min_length=1, max_length=500)
    topics: list[OutlineTopic]

    @model_validator(mode="after")
    def _require_topics(self) -> TopicOutlinePayload:
        if not self.topics:
            raise ValueError("outline must contain at least one topic")
        return self


class TopicOutlineOut(BaseModel):
    presentation_id: str
    title: str | None = None
    topics: list[OutlineTopic] = Field(default_factory=list)
    status: OutlineStatus = "none"
    provider: str | None = None
    model: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


def build_outline_response(
    *,
    presentation_public_id: str,
    outline: Any | None,
) -> dict[str, Any]:
    if outline is None:
        return TopicOutlineOut(
            presentation_id=presentation_public_id,
            title=None,
            topics=[],
            status="none",
        ).model_dump(mode="json")
    return TopicOutlineOut(
        presentation_id=presentation_public_id,
        title=outline.title,
        topics=[OutlineTopic(**topic) for topic in (outline.topics or [])],
        status=outline.status,
        provider=outline.provider,
        model=outline.model,
        created_at=outline.created_at,
        updated_at=outline.updated_at,
    ).model_dump(mode="json")
