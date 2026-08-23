"""API schemas for learner bookmarks (Phase 4D.1/4D.2)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BookmarkCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_type: str = Field(min_length=1, max_length=20)
    target_position: int | None = Field(default=None, ge=0, le=100000)
    target_ref: str | None = Field(default=None, max_length=200)
    title: str | None = Field(default=None, max_length=500)
    label: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=2000)
    is_pinned: bool = False
    session_id: str | None = Field(default=None, max_length=40)


class BookmarkUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_type: str | None = Field(default=None, min_length=1, max_length=20)
    target_position: int | None = Field(default=None, ge=0, le=100000)
    target_ref: str | None = Field(default=None, max_length=200)
    title: str | None = Field(default=None, max_length=500)
    label: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=2000)
    is_pinned: bool | None = None


class BookmarkResponse(BaseModel):
    id: str
    lesson_id: str | None = None
    target_type: str
    target_position: int | None = None
    target_ref: str | None = None
    title: str | None = None
    label: str | None = None
    notes: str | None = None
    is_pinned: bool = False
    created_at: datetime
    updated_at: datetime
