from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

OutlineStatus = Literal["none", "succeeded", "failed"]


class SourceReference(BaseModel):
    """Traceable pointer to the source presentation material."""

    unit_id: str | None = None
    slide_number: int = Field(ge=1)
    preview: str | None = None


class Concept(BaseModel):
    """A granular educational concept or principle."""

    name: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=2000)
    is_source_grounded: bool = True
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    source_references: list[SourceReference] = Field(default_factory=list)


class EducationalExample(BaseModel):
    """An educational example, explicitly distinguished between source-derived and AI-inferred."""

    content: str = Field(min_length=1, max_length=1500)
    type: Literal["source_example", "ai_generated_example"] = "source_example"


class Misconception(BaseModel):
    """A student misconception and its clarifying correction."""

    statement: str = Field(min_length=1, max_length=500)
    correction: str = Field(min_length=1, max_length=1000)
    is_ai_inferred: bool = True


class Prerequisite(BaseModel):
    """A conceptual dependency relationship."""

    prerequisite_topic: str = Field(min_length=1, max_length=300)
    confidence: Literal["high", "medium", "low"] = "medium"


class Subtopic(BaseModel):
    """A logical division of an educational topic."""

    title: str = Field(min_length=1, max_length=500)
    learning_order: int = Field(default=1, ge=1)
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    source_references: list[SourceReference] = Field(default_factory=list)
    concepts: list[Concept] = Field(default_factory=list)
    learning_objectives: list[str] = Field(default_factory=list)
    examples: list[EducationalExample] = Field(default_factory=list)
    misconceptions: list[Misconception] = Field(default_factory=list)
    prerequisites: list[Prerequisite] = Field(default_factory=list)


class OutlineTopic(BaseModel):
    """A major learning topic in a structured outline.

    ``slide_ranges`` is a 1-based, inclusive pair of extracted-unit positions
    ``[start, end]`` covering the topic's slides in the source deck.
    """

    model_config = ConfigDict(extra="ignore")

    title: str = Field(min_length=1, max_length=500)
    slide_ranges: list[int] = Field(min_length=2, max_length=2)
    section: str | None = None
    source_order: int = 1
    learning_order: int = 1
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    source_references: list[SourceReference] = Field(default_factory=list)
    subtopics: list[Subtopic] = Field(default_factory=list)
    concepts: list[Concept] = Field(default_factory=list)
    learning_objectives: list[str] = Field(default_factory=list)
    examples: list[EducationalExample] = Field(default_factory=list)
    misconceptions: list[Misconception] = Field(default_factory=list)
    prerequisites: list[Prerequisite] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_ranges(self) -> OutlineTopic:
        start, end = self.slide_ranges
        if start < 1 or end < start:
            raise ValueError(
                "slide_ranges must be [start, end] with start >= 1 and end >= start"
            )
        return self


class OutlineSection(BaseModel):
    """A higher-level thematic division of the presentation."""

    title: str = Field(min_length=1, max_length=500)
    order: int = Field(default=1, ge=1)
    topic_titles: list[str] = Field(default_factory=list)
    slide_ranges: list[int] = Field(default_factory=list)


class TopicOutlinePayload(BaseModel):
    """LLM output contract for the topic outline pass."""

    title: str = Field(min_length=1, max_length=500)
    structure_version: int = 2
    sections: list[OutlineSection] = Field(default_factory=list)
    topics: list[OutlineTopic]

    @model_validator(mode="after")
    def _require_topics(self) -> TopicOutlinePayload:
        if not self.topics:
            raise ValueError("outline must contain at least one topic")
        return self


class TopicOutlineOut(BaseModel):
    presentation_id: str
    title: str | None = None
    structure_version: int = 2
    sections: list[OutlineSection] = Field(default_factory=list)
    topics: list[OutlineTopic] = Field(default_factory=list)
    status: OutlineStatus = "none"
    provider: str | None = None
    model: str | None = None
    generation_metadata: dict[str, Any] | None = None
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
            structure_version=2,
            sections=[],
            topics=[],
            status="none",
        ).model_dump(mode="json")

    raw_topics = (
        outline.topics or []
        if hasattr(outline, "topics")
        else (outline.get("topics") or [])
    )
    parsed_topics: list[OutlineTopic] = []
    sections_map: dict[str, list[str]] = {}

    for t_data in raw_topics:
        if isinstance(t_data, dict):
            t_obj = OutlineTopic.model_validate(t_data)
            parsed_topics.append(t_obj)
            sec = t_obj.section or "General"
            sections_map.setdefault(sec, []).append(t_obj.title)
        elif isinstance(t_data, OutlineTopic):
            parsed_topics.append(t_data)
            sec = t_data.section or "General"
            sections_map.setdefault(sec, []).append(t_data.title)

    sections: list[OutlineSection] = []
    for idx, (sec_title, t_titles) in enumerate(sections_map.items(), start=1):
        matching_topics = [
            t for t in parsed_topics if (t.section or "General") == sec_title
        ]
        min_slide = min([t.slide_ranges[0] for t in matching_topics]) if matching_topics else 1
        max_slide = max([t.slide_ranges[1] for t in matching_topics]) if matching_topics else 1
        sections.append(
            OutlineSection(
                title=sec_title,
                order=idx,
                topic_titles=t_titles,
                slide_ranges=[min_slide, max_slide],
            )
        )

    title_val = getattr(outline, "title", None) if hasattr(outline, "title") else outline.get("title")
    raw_status = (
        getattr(outline, "status", "none")
        if hasattr(outline, "status")
        else outline.get("status", "none")
    )
    status_val: OutlineStatus = (
        cast(OutlineStatus, raw_status)
        if raw_status in ("none", "succeeded", "failed")
        else "none"
    )
    provider_val = getattr(outline, "provider", None) if hasattr(outline, "provider") else outline.get("provider")
    model_val = getattr(outline, "model", None) if hasattr(outline, "model") else outline.get("model")
    created_val = (
        getattr(outline, "created_at", None)
        if hasattr(outline, "created_at")
        else outline.get("created_at")
    )
    updated_val = (
        getattr(outline, "updated_at", None)
        if hasattr(outline, "updated_at")
        else outline.get("updated_at")
    )

    return TopicOutlineOut(
        presentation_id=presentation_public_id,
        title=title_val,
        structure_version=2,
        sections=sections,
        topics=parsed_topics,
        status=status_val,
        provider=provider_val,
        model=model_val,
        created_at=created_val,
        updated_at=updated_val,
    ).model_dump(mode="json")
