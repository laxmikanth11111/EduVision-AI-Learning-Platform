"""Simplified player schemas — topic navigation only.

No quiz sessions, no bookmarks, no notes, no progress tracking.
Just lesson metadata, version info, topic list, and a lightweight
session pointer (which topic index we're on).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PlayerLessonResponse(BaseModel):
    id: str
    presentation_id: str | None = None
    mode: str
    status: str
    title: str | None = None
    language: str | None = None
    difficulty: str | None = None
    latest_version: int = 0


class PlayerVersionResponse(BaseModel):
    id: str
    lesson_id: str
    version: int
    status: str
    title: str | None = None
    summary: str | None = None
    language: str | None = None
    difficulty: str | None = None
    model: str | None = None
    completed_at: datetime | None = None


class PlayerTopicResponse(BaseModel):
    index: int
    title: str
    description: str = ""
    block_id: str | None = None
    section: str | None = None
    outline_title: str | None = None
    subtopics: list[dict[str, Any]] = Field(default_factory=list)
    concepts: list[dict[str, Any]] = Field(default_factory=list)
    learning_objectives: list[str] = Field(default_factory=list)
    source_references: list[dict[str, Any]] = Field(default_factory=list)
    visuals: list[dict[str, Any]] = Field(default_factory=list)


class PlayerSessionResponse(BaseModel):
    session_id: str
    lesson_id: str
    topic_index: int = 0
    slide_index: int = 0
    total_topics: int = 0
    status: str = "active"
    completion_percentage: float = 0.0


class PlayerPresentationResponse(BaseModel):
    id: str
    title: str | None = None
    file_name: str | None = None
    source_type: str | None = None
    slide_count: int = 0


class PlayerStateResponse(BaseModel):
    lesson: PlayerLessonResponse
    version: PlayerVersionResponse | None = None
    topics: list[PlayerTopicResponse] = Field(default_factory=list)
    source_units: list[dict[str, Any]] = Field(default_factory=list)
    presentation: PlayerPresentationResponse | None = None
    learning_structure: dict[str, Any] | None = None
    session: PlayerSessionResponse | None = None


class StartPlayerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str | None = Field(default=None, max_length=128)
    client_metadata: dict[str, Any] | None = None


class SetPositionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, max_length=40)
    slide_index: int = Field(ge=0, le=100000)
