from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from shared.constants import ContentBlockType, ContentUnitType, ExtractionStatus


class ContentBlockResponse(BaseModel):
    id: str
    block_type: ContentBlockType
    position: int
    content: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContentUnitResponse(BaseModel):
    id: str
    unit_type: ContentUnitType
    position: int
    title: str | None = None
    raw_text: str | None = None
    source_page: int | None = None
    blocks: list[ContentBlockResponse] = Field(default_factory=list)


class ProcessingStatusResponse(BaseModel):
    presentation_id: str
    extraction_status: ExtractionStatus
    units_count: int = 0
    extracted_at: datetime | None = None
    extraction_error: str | None = None


class ContentListResponse(BaseModel):
    presentation_id: str
    extraction_status: ExtractionStatus
    units: list[ContentUnitResponse] = Field(default_factory=list)
