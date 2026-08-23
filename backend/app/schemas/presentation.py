from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from shared.constants import PresentationStatus, PresentationVisibility


class PresentationCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(None, max_length=5000)
    topic: str | None = Field(None, max_length=300)
    visibility: PresentationVisibility = PresentationVisibility.PRIVATE
    file_key: str | None = Field(None, max_length=500)
    file_name: str | None = Field(None, max_length=500)
    folder_id: uuid.UUID | None = None
    subject_id: str | None = Field(None, max_length=100)
    grade_level: str | None = Field(None, max_length=50)
    tags: list[str] = Field(default_factory=list, max_length=50)


class PresentationManualRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    topics: list[str] = Field(min_length=1, max_length=50)
    description: str | None = Field(None, max_length=5000)
    visibility: PresentationVisibility = PresentationVisibility.PRIVATE
    folder_id: uuid.UUID | None = None
    subject_id: str | None = Field(None, max_length=100)
    grade_level: str | None = Field(None, max_length=50)
    tags: list[str] = Field(default_factory=list, max_length=50)


class PresentationUpdateRequest(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=300)
    description: str | None = Field(None, max_length=5000)
    topic: str | None = Field(None, max_length=300)
    visibility: PresentationVisibility | None = None
    subject_id: str | None = Field(None, max_length=100)
    grade_level: str | None = Field(None, max_length=50)
    folder_id: uuid.UUID | None = None
    tags: list[str] | None = None
    expected_updated_at: datetime | None = None


class PresentationStatusUpdateRequest(BaseModel):
    status: PresentationStatus


class PresentationResponse(BaseModel):
    id: str
    title: str
    description: str | None = None
    status: PresentationStatus
    topic: str | None = None
    visibility: PresentationVisibility = PresentationVisibility.PRIVATE
    slide_count: int = 0
    owner_id: str
    folder_id: uuid.UUID | None = None
    subject_id: str | None = None
    subject_confidence: float | None = None
    grade_level: str | None = None
    file_key: str | None = None
    file_name: str | None = None
    file_size: int = 0
    mime_type: str | None = None
    thumbnail_key: str | None = None
    source_status: str | None = None
    extraction_status: str | None = None
    tags: list[str] = Field(default_factory=list)
    published_at: datetime | None = None
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class PresentationSummary(BaseModel):
    id: str
    title: str
    status: PresentationStatus
    topic: str | None = None
    slide_count: int = 0
    subject_id: str | None = None
    subject_confidence: float | None = None
    grade_level: str | None = None
    file_size: int = 0
    thumbnail_key: str | None = None
    extraction_status: str | None = "none"
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None = None


class PublishPresentationResponse(BaseModel):
    presentation_id: str
    status: PresentationStatus
    published_version: str
    published_at: datetime
    snapshot_id: str


class UnpublishPresentationResponse(BaseModel):
    presentation_id: str
    status: PresentationStatus
    unpublished_at: datetime


class AutosaveRequest(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=300)
    description: str | None = Field(None, max_length=5000)
    topic: str | None = Field(None, max_length=300)
    tags: list[str] | None = None
    expected_updated_at: datetime | None = None


class AutosaveResponse(BaseModel):
    presentation_id: str
    saved_at: datetime
    draft_saved: bool


class VersionSaveRequest(BaseModel):
    diff_summary: str | None = Field(None, max_length=2000)


class VersionComparisonResponse(BaseModel):
    presentation_id: str
    from_version: dict[str, Any]
    to_version: dict[str, Any]
    differences: dict[str, Any]


class ThumbnailResponse(BaseModel):
    presentation_id: str
    thumbnail_key: str | None = None


class ThumbnailRegenerateResponse(BaseModel):
    presentation_id: str
    task_scheduled: bool


class ViewRecordedResponse(BaseModel):
    presentation_id: str
    view_count: int
    last_viewed_at: datetime


class LearningSessionResponse(BaseModel):
    presentation_id: str
    session_started_at: datetime
    learning_sessions: int
