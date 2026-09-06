from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings


class VideoProjectCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str = Field(
        min_length=1,
        max_length=settings.VIDEO_RENDER_MAX_TOPIC_CHARS,
        description="Topic to visualise as a learning video.",
    )
    description: str | None = Field(default=None, max_length=2000)
    target_audience: str = Field(default="general_learner", max_length=80)
    difficulty_level: str = Field(default="Intermediate", max_length=40)
    components: list[dict[str, Any]] = Field(
        default_factory=list,
        max_length=settings.VIDEO_RENDER_MAX_COMPONENTS,
    )


class VideoProjectRenderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    force: bool = Field(default=False, description="Restart rendering of a ready/failed project.")


class VideoProjectSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    public_id: str
    video_id: str
    topic: str
    status: str
    progress_percentage: float
    playable_url: str | None = None
    error: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
