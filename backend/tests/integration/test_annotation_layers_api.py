"""Annotation layer API: per-view-layer persistence + ownership (teaching continuity).

Covers the real HTTP endpoints ``GET/PUT /api/v1/lessons/{id}/annotations``:

* every allowed view layer (source / learning / visual / animation) round-trips
  its own items independently of the other layers
* storing an empty item list delegates (deletes) that layer
* a non-owner cannot read or write through these endpoints (403)
* invalid layer modes and negative slide indexes are rejected (422)
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app

pytestmark = pytest.mark.asyncio

_STROKE = {
    "type": "stroke",
    "tool": "pen",
    "color": "#F2A623",
    "size": 4,
    "points": [{"x": 1.0, "y": 2.0}, {"x": 3.0, "y": 4.0}],
}
_TEXT = {
    "type": "text",
    "x": 5.0,
    "y": 6.0,
    "text": "label",
    "color": "#ffffff",
    "size": 12,
}


class _AuthedUser:
    """A user we can authenticate as by overriding ``get_current_user``."""

    def __init__(self, uid: uuid.UUID, email: str | None = None) -> None:
        self.id = uid
        self.email = email or f"annot_{uid.hex[:12]}@example.com"
        self.name = "Annot Owner"

    def install(self) -> None:
        from app.core.dependencies import get_current_user

        async def _fake() -> _AuthedUser:
            return self

        app.dependency_overrides[get_current_user] = _fake

    def restore(self) -> None:
        from app.core.dependencies import get_current_user

        app.dependency_overrides.pop(get_current_user, None)


@pytest_asyncio.fixture
async def owner(client: AsyncClient) -> AsyncGenerator[_AuthedUser]:
    from app.core.security import hash_password
    from app.models.generated_lesson import GeneratedLesson
    from app.models.presentation import Presentation
    from app.models.user import User
    from tests.conftest import TestSessionLocal

    user = _AuthedUser(uuid.uuid4())
    async with TestSessionLocal() as session:
        session.add(
            User(
                id=user.id,
                email=user.email,
                name=user.name,
                password_hash=hash_password("password123"),
            )
        )
        await session.flush()
        pres = Presentation(
            title="Annot Deck",
            owner_id=user.id,
            status="published",
        )
        session.add(pres)
        await session.flush()
        lesson = GeneratedLesson(
            presentation_id=pres.id,
            user_id=user.id,
            mode="slide",
            status="ready",
            title="Annot Lesson",
            latest_version=1,
        )
        session.add(lesson)
        await session.commit()
        await session.refresh(lesson)
        user.lesson_id = lesson.public_id  # type: ignore[attr-defined]

    user.install()
    yield user
    user.restore()


async def _url(lesson_id: str) -> str:
    return f"/api/v1/lessons/{lesson_id}/annotations"


async def test_annotation_layers_round_trip_and_are_isolated_per_mode(
    client: AsyncClient, owner: _AuthedUser
) -> None:
    lesson_id = owner.lesson_id  # type: ignore[attr-defined]
    payloads = {
        "source": ([_STROKE], 0),
        "learning": ([_TEXT], 3),
        "visual": ([_STROKE, _TEXT], 1),
        "animation": ([_TEXT], 2),
    }
    for mode, (items, index) in payloads.items():
        resp = await client.put(
            f"{await _url(lesson_id)}/{mode}/{index}",
            json={"items": items},
        )
        assert resp.status_code == 200, resp.text

    listed = await client.get(await _url(lesson_id))
    assert listed.status_code == 200, listed.text
    layers = listed.json()["data"]["layers"]
    by_key = {f"{x['player_mode']}:{x['slide_index']}": x["items"] for x in layers}
    for mode, (items, index) in payloads.items():
        assert by_key[f"{mode}:{index}"] == items, f"layer {mode}:{index}"

    # Layers never bleed into each other: learning holds only its own items.
    assert by_key["learning:3"] == [_TEXT]


async def test_storing_empty_items_deletes_the_layer(
    client: AsyncClient, owner: _AuthedUser
) -> None:
    lesson_id = owner.lesson_id  # type: ignore[attr-defined]
    url = await _url(lesson_id)
    assert (await client.put(f"{url}/visual/0", json={"items": [_TEXT]})).status_code == 200
    assert (await client.get(url)).json()["data"]["layers"][0]["items"] == [_TEXT]
    cleared = await client.put(f"{url}/visual/0", json={"items": []})
    assert cleared.status_code == 200
    assert cleared.json()["data"]["item_count"] == 0
    assert (await client.get(url)).json()["data"]["layers"] == []


async def test_non_owner_is_denied(client: AsyncClient, owner: _AuthedUser) -> None:
    """A user who does not own the presentation gets 403 on both read + write."""
    lesson_id = owner.lesson_id  # type: ignore[attr-defined]
    other = _AuthedUser(uuid.uuid4())
    other.install()
    try:
        url = await _url(lesson_id)
        write = await client.put(f"{url}/learning/1", json={"items": [_TEXT]})
        assert write.status_code == 403, write.text
        read = await client.get(url)
        assert read.status_code == 403, read.text
    finally:
        other.restore()


async def test_invalid_mode_and_negative_index_rejected(
    client: AsyncClient, owner: _AuthedUser
) -> None:
    lesson_id = owner.lesson_id  # type: ignore[attr-defined]
    url = await _url(lesson_id)
    bad_mode = await client.put(f"{url}/critical-html/0", json={"items": [_TEXT]})
    assert bad_mode.status_code == 422
    bad_index = await client.put(f"{url}/learning/-1", json={"items": [_TEXT]})
    assert bad_index.status_code == 422
