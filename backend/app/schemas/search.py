from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from shared.constants import PresentationStatus


class SearchResult(BaseModel):
    presentation_id: str
    title: str
    relevance: float = Field(ge=0.0, le=1.0)
    match_context: str | None = None
    match_field: str | None = None
    slide_index: int | None = None
    status: PresentationStatus
    updated_at: datetime
