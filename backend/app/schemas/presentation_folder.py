from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class FolderCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    parent_id: uuid.UUID | None = None


class FolderUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    parent_id: uuid.UUID | None = None


class FolderResponse(BaseModel):
    id: uuid.UUID
    name: str
    owner_id: uuid.UUID
    parent_id: uuid.UUID | None = None
    presentation_count: int = 0
    created_at: datetime
    updated_at: datetime


class BreadcrumbResponse(BaseModel):
    id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None = None
