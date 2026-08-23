from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from shared.constants import PresentationStatus


class VersionResponse(BaseModel):
    id: str
    presentation_id: uuid.UUID
    version: str
    version_number: int
    title: str
    slide_count: int = 0
    diff_summary: str | None = None
    status: PresentationStatus
    created_by: uuid.UUID | None = None
    created_at: datetime
