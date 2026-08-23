from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class AnalyticsResponse(BaseModel):
    presentation_id: uuid.UUID
    view_count: int = 0
    unique_viewers: int = 0
    quiz_attempts: int = 0
    publish_count: int = 0
    learning_sessions: int = 0
    total_opens: int = 0
    avg_quiz_score: float | None = None
    completion_rate: float | None = None
    last_viewed_at: datetime | None = None
