"""API schemas for learner notes (Phase 4D.1/4D.2)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NoteCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_type: str = Field(min_length=1, max_length=20)
    target_position: int | None = Field(default=None, ge=0, le=100000)
    target_ref: str | None = Field(default=None, max_length=200)
    content: str = Field(min_length=1, max_length=20000)
    is_pinned: bool = False
    session_id: str | None = Field(default=None, max_length=40)


class NoteUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_type: str | None = Field(default=None, min_length=1, max_length=20)
    target_position: int | None = Field(default=None, ge=0, le=100000)
    target_ref: str | None = Field(default=None, max_length=200)
    content: str | None = Field(default=None, min_length=1, max_length=20000)
    is_pinned: bool | None = None


class NoteResponse(BaseModel):
    id: str
    lesson_id: str | None = None
    target_type: str
    target_position: int | None = None
    target_ref: str | None = None
    content: str
    is_pinned: bool = False
    version: int = 1
    is_sanitized: bool = False
    edited_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


StudentNoteCreateRequest = NoteCreateRequest  # backward compat alias
StudentNoteUpdateRequest = NoteUpdateRequest  # backward compat alias
StudentNoteResponse = NoteResponse  # backward compat alias
