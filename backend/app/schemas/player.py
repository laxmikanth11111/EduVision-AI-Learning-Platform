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


class PlayerSessionResponse(BaseModel):
    session_id: str
    lesson_id: str
    topic_index: int = 0
    total_topics: int = 0
    status: str = "active"


class PlayerStateResponse(BaseModel):
    lesson: PlayerLessonResponse
    version: PlayerVersionResponse | None = None
    topics: list[PlayerTopicResponse] = Field(default_factory=list)
    session: PlayerSessionResponse | None = None


class StartPlayerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str | None = Field(default=None, max_length=128)
    client_metadata: dict[str, Any] | None = None
