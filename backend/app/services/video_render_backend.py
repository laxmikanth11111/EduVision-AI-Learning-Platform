"""Render backend seam for the async video runtime (P16).

The service layer renders through this seam so tests and E2E checks run with a
deterministic ``VideoRenderBackend`` (``VIDEO_RENDER_BACKEND=mock``) that needs no
OpenCV/FFmpeg, while production uses the existing binary renderer unchanged.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.video_engine import VideoProject
from app.services.video_renderer_service import UPLOADS_VIDEO_DIR, video_renderer_service

logger = get_logger(__name__)

ProgressCallback = Callable[[float], None]


@dataclass(frozen=True)
class RenderResult:
    playable_url: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.playable_url is not None and self.error is None


class VideoRenderBackend(Protocol):
    def render(
        self,
        project: VideoProject | None,
        progress: ProgressCallback,
    ) -> RenderResult:
        """Render ``project`` to a playable mp4 synchronously.

        ``progress`` must be invoked with floats in ``[0, 1]``; the final
        invocation is ``1.0`` exactly when rendering succeeds.
        """
        ...


class RealFfmpegRenderBackend:
    """Wraps the existing PIL/OpenCV/FFmpeg renderer unchanged."""

    def render(
        self,
        project: VideoProject | None,
        progress: ProgressCallback,
    ) -> RenderResult:
        if project is None:
            return RenderResult(error="Video project blueprint is missing (cannot re-render)")
        try:
            playable_url = video_renderer_service.render_video_mp4(
                project,
                progress_callback=progress,
            )
        except Exception as exc:
            logger.exception("video_render_failed", video_id=project.video_id)
            return RenderResult(error=f"{type(exc).__name__}: {exc}")
        return RenderResult(playable_url=playable_url)


class MockRenderBackend:
    """Deterministic offline backend for tests so no OpenCV/FFmpeg is needed."""

    def render(
        self,
        project: VideoProject | None,
        progress: ProgressCallback,
    ) -> RenderResult:
        if project is None:
            return RenderResult(error="Video project blueprint is missing (cannot re-render)")
        os.makedirs(UPLOADS_VIDEO_DIR, exist_ok=True)
        output_path = os.path.join(UPLOADS_VIDEO_DIR, f"{project.video_id}.mp4")
        payload = (
            "EDUVISION-MOCK-RENDER\n"
            f"video_id={project.video_id}\n"
            f"topic={project.topic}\n"
        ).encode()
        with open(output_path, "wb") as handle:
            handle.write(payload)

        milestones = max(2, settings.VIDEO_RENDER_PROGRESS_MILESTONES)
        for step in range(1, milestones + 1):
            progress(step / milestones)
        progress(1.0)
        return RenderResult(playable_url=f"/uploads/videos/{project.video_id}.mp4")


def get_video_render_backend() -> VideoRenderBackend:
    name = settings.VIDEO_RENDER_BACKEND.strip().lower()
    if name == "mock":
        return MockRenderBackend()
    return RealFfmpegRenderBackend()
