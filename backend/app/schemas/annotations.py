"""Annotation-layer request/response schemas (teaching continuity).

A "layer" is every mark on one slide in one view: ``(player_mode, slide_index)``.
Items are validated/normalized server-side (see
``PresentationAnnotationService.parse_annotations``) so the stored payload is a
closed set of primitive shapes — never HTML/JS.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AnnotationLayerResponse(BaseModel):
    player_mode: str
    slide_index: int
    items: list[dict[str, Any]] = Field(default_factory=list)


class AnnotationListResponse(BaseModel):
    layers: list[AnnotationLayerResponse] = Field(default_factory=list)


class AnnotationSaveResponse(BaseModel):
    player_mode: str
    slide_index: int
    item_count: int = 0
