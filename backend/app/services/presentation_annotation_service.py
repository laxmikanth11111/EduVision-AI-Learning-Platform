"""Per-slide annotation layer persistence (teaching continuity).

Stores/reads the overlay marks a learner or presenter draws on each slide as
normalized JSON rows keyed by ``(user_id, lesson_id, player_mode, slide_index)``.
Ownership of the *lesson* is asserted by the API layer first (via the shared
``LessonPlayerService`` helper), so cross-user reads are impossible and every
read is additionally scoped by the authenticated ``user_id``.

Data safety: items are validated and normalized to a closed set of primitives
(strokes/shapes/text with finite numbers and a strict color/hex format). The
payload is never interpreted as HTML or JS anywhere in the stack — the frontend
renders it through canvas drawing only.
"""

from __future__ import annotations

import json
import math
import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database.unit_of_work import UnitOfWork
from app.models.presentation_annotation import (
    PresentationAnnotation,
    generate_annotation_public_id,
)
from shared.constants import AnnotationLayerMode

# Hard limits keep a single layer bounded and the request size predictable.
MAX_ITEMS_PER_LAYER = 500
MAX_POINTS_PER_STROKE = 4000
MAX_TEXT_LENGTH = 2000
MAX_LAYER_BYTES = 300_000

_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
_ALLOWED_MODES = AnnotationLayerMode.as_set()


def parse_annotations(items: Any) -> list[dict[str, Any]]:
    """Validate + normalize a client annotation layer payload.

    Raises ``ValueError`` (surfaced as HTTP 422) on any structurally invalid or
    oversized item; returns a closed-shape list safe to store and draw.
    """
    if not isinstance(items, list):
        raise ValueError("annotations must be a JSON array")
    if len(items) > MAX_ITEMS_PER_LAYER:
        raise ValueError(
            f"too many annotations: {len(items)} (max {MAX_ITEMS_PER_LAYER})"
        )

    result: list[dict[str, Any]] = []
    for item in items:
        result.append(_normalize_item(item))

    size = len(json.dumps(result, separators=(",", ":")))
    if size > MAX_LAYER_BYTES:
        raise ValueError(
            f"annotation layer too large: {size} bytes (max {MAX_LAYER_BYTES})"
        )
    return result


def _normalize_item(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError("every annotation must be an object")
    item_type = item.get("type")
    if item_type == "stroke":
        tool = item.get("tool")
        if tool not in ("pen", "highlighter"):
            raise ValueError(f"invalid stroke tool: {tool!r}")
        points = item.get("points")
        if not isinstance(points, list) or not 2 <= len(points) <= MAX_POINTS_PER_STROKE:
            raise ValueError("stroke requires 2..4000 points")
        return {
            "type": "stroke",
            "tool": tool,
            "color": _color(item.get("color")),
            "size": _size(item.get("size")),
            "points": [_point(p) for p in points],
        }
    if item_type == "shape":
        kind = item.get("kind")
        if kind not in ("rect", "ellipse", "line", "arrow"):
            raise ValueError(f"invalid shape kind: {kind!r}")
        return {
            "type": "shape",
            "kind": kind,
            "color": _color(item.get("color")),
            "size": _size(item.get("size")),
            "x1": _coord(item.get("x1")),
            "y1": _coord(item.get("y1")),
            "x2": _coord(item.get("x2")),
            "y2": _coord(item.get("y2")),
        }
    if item_type == "text":
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("text annotation requires non-empty text")
        if len(text) > MAX_TEXT_LENGTH:
            raise ValueError(f"annotation text too long: {len(text)} (max {MAX_TEXT_LENGTH})")
        return {
            "type": "text",
            "x": _coord(item.get("x")),
            "y": _coord(item.get("y")),
            "text": text,
            "color": _color(item.get("color")),
            "size": _size(item.get("size")),
        }
    raise ValueError(f"unsupported annotation type: {item_type!r}")


def _color(value: Any) -> str:
    if not isinstance(value, str) or not _COLOR_RE.match(value):
        raise ValueError(f"invalid annotation color: {value!r}")
    return value


def _size(value: Any) -> float:
    number = _finite_number(value)
    if not 1.0 <= number <= 48.0:
        raise ValueError(f"annotation size out of range: {value!r}")
    return number


def _coord(value: Any) -> float:
    return _finite_number(value)


def _point(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        raise ValueError("stroke point must be an object")
    return {"x": _finite_number(value.get("x")), "y": _finite_number(value.get("y"))}


def _finite_number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"expected a finite number, got {value!r}")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"expected a finite number, got {value!r}")
    return number


class PresentationAnnotationService:
    """Persist and read per-slide annotation layers for a lesson owner."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def list_for_lesson(
        self,
        *,
        user_id: str,
        lesson_id: uuid.UUID,
    ) -> list[dict[str, Any]]:
        """Return every annotation layer for a lesson, scoped to the user."""
        stmt = (
            select(PresentationAnnotation)
            .where(
                PresentationAnnotation.user_id == uuid.UUID(str(user_id)),
                PresentationAnnotation.lesson_id == lesson_id,
            )
            .order_by(PresentationAnnotation.player_mode, PresentationAnnotation.slide_index)
        )
        rows = (await self._uow.session.execute(stmt)).scalars().all()
        return [self._serialize_layer(row) for row in rows]

    async def replace(
        self,
        *,
        user_id: str,
        lesson_id: uuid.UUID,
        player_mode: str,
        slide_index: int,
        items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Replace (or delete, when empty) one layer idempotently."""
        mode = self._validate_mode(player_mode)
        slide_index = max(0, int(slide_index))

        user_uuid = uuid.UUID(str(user_id))
        stmt = select(PresentationAnnotation).where(
            PresentationAnnotation.user_id == user_uuid,
            PresentationAnnotation.lesson_id == lesson_id,
            PresentationAnnotation.player_mode == mode,
            PresentationAnnotation.slide_index == slide_index,
        )
        row = (await self._uow.session.execute(stmt)).scalar_one_or_none()

        if not items:
            if row is not None:
                await self._uow.session.delete(row)
                await self._uow.flush()
            return {
                "public_id": (row.public_id if row else ""),
                "player_mode": mode,
                "slide_index": slide_index,
                "item_count": 0,
            }

        if row is None:
            row = PresentationAnnotation(
                public_id=generate_annotation_public_id(),
                user_id=user_uuid,
                lesson_id=lesson_id,
                player_mode=mode,
                slide_index=slide_index,
                items=items,
            )
            self._uow.session.add(row)
        else:
            row.items = items
        try:
            await self._uow.flush()
        except IntegrityError:
            # Lost a first-write race: another request created this layer between
            # our SELECT and INSERT, so our flush violated uq_lesson_annotations_layer.
            # Recover by adopting the winner's row and folding this write on top
            # instead of surfacing a 500.
            await self._uow.rollback()
            stmt = select(PresentationAnnotation).where(
                PresentationAnnotation.user_id == user_uuid,
                PresentationAnnotation.lesson_id == lesson_id,
                PresentationAnnotation.player_mode == mode,
                PresentationAnnotation.slide_index == slide_index,
            )
            winner = (await self._uow.session.execute(stmt)).scalar_one_or_none()
            if winner is None:
                raise
            winner.items = items
            await self._uow.flush()
            row = winner
        return {
            "public_id": row.public_id,
            "player_mode": mode,
            "slide_index": slide_index,
            "item_count": len(items),
        }

    @staticmethod
    def _validate_mode(value: str) -> str:
        if value not in _ALLOWED_MODES:
            raise ValueError(f"invalid annotation layer mode: {value!r}")
        return value

    @staticmethod
    def _serialize_layer(row: PresentationAnnotation) -> dict[str, Any]:
        return {
            "player_mode": row.player_mode,
            "slide_index": row.slide_index,
            "items": row.items if isinstance(row.items, list) else [],
        }
