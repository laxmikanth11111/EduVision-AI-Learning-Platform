"""Annotation layer validation + persistence (teaching continuity)."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.database.unit_of_work import UnitOfWork
from app.models.generated_lesson import GeneratedLesson
from app.models.presentation import Presentation
from app.models.presentation_annotation import (
    PresentationAnnotation,
    generate_annotation_public_id,
)
from app.models.user import User
from app.services.presentation_annotation_service import (
    MAX_ITEMS_PER_LAYER,
    MAX_LAYER_BYTES,
    MAX_POINTS_PER_STROKE,
    MAX_TEXT_LENGTH,
    PresentationAnnotationService,
    parse_annotations,
)

_STROKE = {
    "type": "stroke",
    "tool": "pen",
    "color": "#F2A623",
    "size": 4,
    "points": [{"x": 1.0, "y": 2.0}, {"x": 3.0, "y": 4.0}],
}
_SHAPE = {
    "type": "shape",
    "kind": "rect",
    "color": "#1D9E75",
    "size": 2,
    "x1": 0.0,
    "y1": 0.0,
    "x2": 10.0,
    "y2": 10.0,
}
_TEXT = {
    "type": "text",
    "x": 5.0,
    "y": 6.0,
    "text": "label",
    "color": "#ffffff",
    "size": 12,
}


class TestParseAnnotations:
    def test_accepts_and_normalizes_closed_shapes(self) -> None:
        assert parse_annotations([_STROKE, _SHAPE, _TEXT]) == [_STROKE, _SHAPE, _TEXT]

    def test_rejects_non_list_payload(self) -> None:
        with pytest.raises(ValueError, match="must be a JSON array"):
            parse_annotations({"type": "stroke"})

    def test_rejects_empty_stroke(self) -> None:
        item = dict(_STROKE, points=[{"x": 0, "y": 0}])
        with pytest.raises(ValueError, match="stroke requires"):
            parse_annotations([item])

    def test_rejects_non_finite_coordinates(self) -> None:
        item = dict(_TEXT, x="nan")
        with pytest.raises(ValueError, match="finite number"):
            parse_annotations([item])
        point = {"x": 1e999, "y": 0.0}
        with pytest.raises(ValueError, match="finite number"):
            parse_annotations([dict(_STROKE, points=[point, point])])

    def test_rejects_bad_color_and_size(self) -> None:
        with pytest.raises(ValueError, match="invalid annotation color"):
            parse_annotations([dict(_STROKE, color="red")])
        with pytest.raises(ValueError, match="annotation size out of range"):
            parse_annotations([dict(_STROKE, size=0.5)])

    def test_accepts_hex_color_forms(self) -> None:
        for color in ("#abc", "#aabbcc", "#aabbccdd"):
            assert parse_annotations([dict(_STROKE, color=color)])[0]["color"] == color

    def test_rejects_unknown_type(self) -> None:
        with pytest.raises(ValueError, match="unsupported annotation type"):
            parse_annotations([{"type": "html", "html": "<script>"}])

    def test_rejects_too_many_items_and_oversize_layer(self) -> None:
        with pytest.raises(ValueError, match="too many annotations"):
            parse_annotations([_TEXT] * (MAX_ITEMS_PER_LAYER + 1))
        big_text = "x" * (MAX_TEXT_LENGTH + 1)
        with pytest.raises(ValueError, match="annotation text too long"):
            parse_annotations([dict(_TEXT, text=big_text)])
        # A layer of full-length strokes must trip the byte cap, not item cap.
        long_stroke = dict(_STROKE, points=[{"x": float(i), "y": float(i)} for i in range(MAX_POINTS_PER_STROKE)])
        with pytest.raises(ValueError, match="layer too large"):
            parse_annotations([long_stroke] * MAX_ITEMS_PER_LAYER)
        assert MAX_LAYER_BYTES > 0

    def test_keeps_shape_kinds_closed(self) -> None:
        for kind in ("rect", "ellipse", "line", "arrow"):
            items = parse_annotations([dict(_SHAPE, kind=kind)])
            assert items[0]["kind"] == kind
        with pytest.raises(ValueError, match="invalid shape kind"):
            parse_annotations([dict(_SHAPE, kind="polygon")])


async def _make_lesson(db_session, presentation) -> GeneratedLesson:
    lesson = GeneratedLesson(
        presentation_id=presentation.id,
        user_id=None,
        mode="slide",
        status="ready",
        title="Annotation Lesson",
        language="en",
        difficulty="beginner",
        latest_version=1,
    )
    db_session.add(lesson)
    await db_session.flush()
    return lesson


def _service(db_session) -> PresentationAnnotationService:
    return PresentationAnnotationService(UnitOfWork(session=db_session))


class TestAnnotationLayerPersistence:
    pytestmark = pytest.mark.asyncio

    async def test_round_trip_replace_and_list(
        self, db_session, make_user, make_presentation
    ) -> None:
        user = await make_user()
        lesson = await _make_lesson(db_session, await make_presentation())
        svc = _service(db_session)

        saved = await svc.replace(
            user_id=str(user.id),
            lesson_id=lesson.id,
            player_mode="learning",
            slide_index=2,
            items=[_STROKE, _TEXT],
        )
        assert saved["player_mode"] == "learning"
        assert saved["slide_index"] == 2
        assert saved["item_count"] == 2
        assert saved["public_id"].startswith("pann_")

        layers = await svc.list_for_lesson(user_id=str(user.id), lesson_id=lesson.id)
        assert len(layers) == 1
        assert layers[0]["player_mode"] == "learning"
        assert layers[0]["slide_index"] == 2
        assert layers[0]["items"] == [_STROKE, _TEXT]

    async def test_replace_idempotent_and_layers_isolated(
        self, db_session, make_user, make_presentation
    ) -> None:
        user = await make_user()
        lesson = await _make_lesson(db_session, await make_presentation())
        svc = _service(db_session)

        first = await svc.replace(
            user_id=str(user.id), lesson_id=lesson.id,
            player_mode="source", slide_index=0, items=[_SHAPE],
        )
        second = await svc.replace(
            user_id=str(user.id), lesson_id=lesson.id,
            player_mode="source", slide_index=0, items=[_TEXT],
        )
        assert first["public_id"] == second["public_id"], "replace must upsert the same row"

        # A different layer key (mode OR slide) is its own row.
        await svc.replace(
            user_id=str(user.id), lesson_id=lesson.id,
            player_mode="visual", slide_index=0, items=[_SHAPE],
        )
        layers = await svc.list_for_lesson(user_id=str(user.id), lesson_id=lesson.id)
        assert len(layers) == 2

    async def test_empty_items_deletes_layer(
        self, db_session, make_user, make_presentation
    ) -> None:
        user = await make_user()
        lesson = await _make_lesson(db_session, await make_presentation())
        svc = _service(db_session)
        await svc.replace(
            user_id=str(user.id), lesson_id=lesson.id,
            player_mode="animation", slide_index=1, items=[_TEXT],
        )
        cleared = await svc.replace(
            user_id=str(user.id), lesson_id=lesson.id,
            player_mode="animation", slide_index=1, items=[],
        )
        assert cleared["item_count"] == 0
        assert await svc.list_for_lesson(user_id=str(user.id), lesson_id=lesson.id) == []

    async def test_layers_scoped_to_user_and_lesson(
        self, db_session, make_user, make_presentation
    ) -> None:
        owner_a = await make_user()
        owner_b = await make_user()
        lesson_a = await _make_lesson(db_session, await make_presentation())
        await _service(db_session).replace(
            user_id=str(owner_a.id), lesson_id=lesson_a.id,
            player_mode="learning", slide_index=0, items=[_TEXT],
        )
        assert await _service(db_session).list_for_lesson(
            user_id=str(owner_b.id), lesson_id=lesson_a.id
        ) == []
        assert len(
            await _service(db_session).list_for_lesson(
                user_id=str(owner_a.id), lesson_id=lesson_a.id
            )
        ) == 1

    async def test_invalid_layer_mode_rejected(
        self, db_session, make_user, make_presentation
    ) -> None:
        user = await make_user()
        lesson = await _make_lesson(db_session, await make_presentation())
        svc = _service(db_session)
        with pytest.raises(ValueError, match="invalid annotation layer mode"):
            await svc.replace(
                user_id=str(user.id), lesson_id=lesson.id,
                player_mode="critical-html", slide_index=0, items=[_TEXT],
            )

    async def test_replace_recovers_from_first_write_race(self, db_session) -> None:
        """Concurrent first-write for the same layer key must not 500.

        The loser's INSERT violates uq_lesson_annotations_layer after a stale
        SELECT; replace() must adopt the winner's committed row and fold the
        write on top, keeping the layer single and idempotent.
        """
        # Winner is created and committed through a separate connection so it
        # survives the loser's rollback inside replace().
        from app.database import session as db_session_module

        async with db_session_module.async_session_factory() as other:
            other_user = User(email="race@example.com", name="Race User", password_hash="x")
            other.add(other_user)
            presentation = Presentation(
                title="Race Presentation",
                owner_id=other_user.id,
                status="draft",
                visibility="private",
            )
            other.add(presentation)
            await other.flush()
            lesson = GeneratedLesson(
                presentation_id=presentation.id,
                user_id=None,
                mode="slide",
                status="ready",
                title="Race Lesson",
                language="en",
                difficulty="beginner",
                latest_version=1,
            )
            other.add(lesson)
            await other.flush()
            layer = PresentationAnnotation(
                public_id=generate_annotation_public_id(),
                user_id=other_user.id,
                lesson_id=lesson.id,
                player_mode="learning",
                slide_index=3,
                items=[_SHAPE],
            )
            other.add(layer)
            await other.commit()
            lesson_id, user_id, winner_id = lesson.id, other_user.id, layer.public_id

        svc = _service(db_session)
        real_execute = db_session.execute
        stale_first = {"saw_winner": False}

        async def _stale_first_execute(stmt, *args, **kwargs):
            # Simulate the loser reading the layer before the winner committed:
            # the first lookup returns no row even though the winner now exists.
            if not stale_first["saw_winner"]:
                stale_first["saw_winner"] = True

                class _Empty:
                    def scalar_one_or_none(self) -> None:
                        return None

                return _Empty()
            return await real_execute(stmt, *args, **kwargs)

        with patch.object(db_session, "execute", side_effect=_stale_first_execute):
            saved = await svc.replace(
                user_id=str(user_id),
                lesson_id=lesson_id,
                player_mode="learning",
                slide_index=3,
                items=[_TEXT, _STROKE],
            )

        assert saved["public_id"] == winner_id, "must adopt the winner's row"
        assert saved["item_count"] == 2
        result = await db_session.execute(
            select(PresentationAnnotation).where(
                PresentationAnnotation.user_id == user_id,
                PresentationAnnotation.lesson_id == lesson_id,
                PresentationAnnotation.player_mode == "learning",
                PresentationAnnotation.slide_index == 3,
            )
        )
        rows = result.scalars().all()
        assert len(rows) == 1, "layer must stay single"
        assert rows[0].public_id == winner_id
        assert rows[0].items == [_TEXT, _STROKE]
