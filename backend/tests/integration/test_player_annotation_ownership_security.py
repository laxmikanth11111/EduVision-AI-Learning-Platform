"""B8 player/annotations ownership-response equalization tests.

Historically the player and annotation routes answered a foreign lesson with
``403 Access denied`` while a missing lesson answered ``404``, leaking lesson
existence and ownership. ``POST /player/advance`` and ``POST /player/set-topic``
additionally let an uncaught ``ValueError`` escape as a 500. Under the
repo-wide 404-equalization convention both cases must now render identically:

* Non-owner reads/writes on an existing lesson must be byte-identical to the
  missing-lesson response (same status, same ``detail``).
* Missing/foreign session mutations must be 404, never 500.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from fastapi import HTTPException, Request
from fastapi import status as http_status
from httpx import ASGITransport, AsyncClient

from app.core.dependencies import get_current_user
from app.core.security import create_access_token, decode_access_token
from app.main import app

pytestmark = pytest.mark.asyncio

_USER_A_ID = uuid.UUID("aaaaaaaa-1111-4111-8111-aaaaaaaaaa01")
_USER_B_ID = uuid.UUID("bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb")
_MISSING_LESSON_ID = "lesson_does_not_exist"


class _RealUser:
    """Lightweight user stand-in built from a decoded JWT."""

    def __init__(self, user_id: uuid.UUID, email: str, name: str) -> None:
        self.id = user_id
        self.email = email
        self.name = name


@pytest_asyncio.fixture(autouse=True)
async def _seed_two_users_and_use_jwt_auth(setup_database: None):
    """Insert two users and override get_current_user with a JWT-decoding version."""
    from app.core.security import hash_password
    from app.models.user import User
    from tests.conftest import TestSessionLocal

    async with TestSessionLocal() as session:
        for uid, email, name in (
            (_USER_A_ID, "ply_a@test.com", "Player User A"),
            (_USER_B_ID, "ply_b@test.com", "Player User B"),
        ):
            existing = await session.execute(User.__table__.select().where(User.id == uid))
            if existing.first() is None:
                session.add(
                    User(
                        id=uid,
                        email=email,
                        name=name,
                        password_hash=hash_password("password123"),
                    )
                )
        await session.commit()

    app.dependency_overrides.pop(get_current_user, None)

    user_map = {
        str(_USER_A_ID): _RealUser(_USER_A_ID, "ply_a@test.com", "Player User A"),
        str(_USER_B_ID): _RealUser(_USER_B_ID, "ply_b@test.com", "Player User B"),
    }

    async def _jwt_get_current_user(request: Request) -> _RealUser:
        token = None
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
        if not token:
            token = request.cookies.get("access_token")
        if not token:
            raise HTTPException(
                status_code=http_status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        try:
            payload = decode_access_token(token)
        except Exception:
            raise HTTPException(
                status_code=http_status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token.",
            )
        user = user_map.get(payload.get("sub"))
        if not user:
            raise HTTPException(
                status_code=http_status.HTTP_401_UNAUTHORIZED,
                detail="User not found.",
            )
        return user

    app.dependency_overrides[get_current_user] = _jwt_get_current_user
    yield
    app.dependency_overrides.pop(get_current_user, None)


def _headers(user_id: uuid.UUID) -> dict[str, str]:
    token = create_access_token(user_id, role="user")
    return {"Authorization": f"Bearer {token}"}


def _assert_equalized_not_found(resp, lesson_id: str) -> None:
    """The expected 404 with the standard not-found phrasing (no Access denied)."""
    assert resp.status_code == 404, resp.text
    body = resp.json()
    assert body["success"] is False
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["message"] == f"Lesson {lesson_id} not found"


async def _make_client() -> AsyncClient:
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test", follow_redirects=True)


async def _seed_lesson_owned_by_a() -> str:
    """Create a lesson whose presentation is owned by user A."""
    from app.models.generated_lesson import GeneratedLesson
    from app.models.presentation import Presentation
    from tests.conftest import TestSessionLocal

    async with TestSessionLocal() as session:
        pres = Presentation(
            title="B8 ownership deck",
            owner_id=_USER_A_ID,
            status="published",
        )
        session.add(pres)
        await session.flush()
        lesson = GeneratedLesson(
            presentation_id=pres.id,
            user_id=_USER_A_ID,
            mode="slide",
            status="ready",
            title="B8 ownership lesson",
            latest_version=1,
        )
        session.add(lesson)
        await session.commit()
        await session.refresh(lesson)
        return lesson.public_id


async def test_unauthenticated_player_rejected() -> None:
    async with await _make_client() as client:
        resp = await client.get("/api/v1/lessons/lesson_x/player")
        assert resp.status_code == 401


async def test_owner_reads_player_state() -> None:
    """User A still resolves their own player state (feature preserved)."""
    lesson_id = await _seed_lesson_owned_by_a()
    async with await _make_client() as client:
        resp = await client.get(
            f"/api/v1/lessons/{lesson_id}/player",
            headers=_headers(_USER_A_ID),
        )
        assert resp.status_code == 200, resp.text


async def test_non_owner_player_state_equals_missing_lesson() -> None:
    """B's read of A's lesson equals the missing-lesson 404 (discriminator)."""
    lesson_id = await _seed_lesson_owned_by_a()
    async with await _make_client() as client:
        b_headers = _headers(_USER_B_ID)
        foreign = await client.get(
            f"/api/v1/lessons/{lesson_id}/player",
            headers=b_headers,
        )
        missing = await client.get(
            f"/api/v1/lessons/{_MISSING_LESSON_ID}/player",
            headers=b_headers,
        )
        _assert_equalized_not_found(foreign, lesson_id)
        _assert_equalized_not_found(missing, _MISSING_LESSON_ID)


async def test_non_owner_player_start_equals_missing_lesson() -> None:
    """B's session start on A's lesson equals the missing-lesson 404."""
    lesson_id = await _seed_lesson_owned_by_a()
    async with await _make_client() as client:
        b_headers = _headers(_USER_B_ID)
        foreign = await client.post(
            f"/api/v1/lessons/{lesson_id}/player/start",
            json={},
            headers=b_headers,
        )
        missing = await client.post(
            f"/api/v1/lessons/{_MISSING_LESSON_ID}/player/start",
            json={},
            headers=b_headers,
        )
        _assert_equalized_not_found(foreign, lesson_id)
        _assert_equalized_not_found(missing, _MISSING_LESSON_ID)


async def test_non_owner_checkpoint_and_mastery_equal_missing_lesson() -> None:
    """Checkpoint/mastery reads do not reveal lesson existence to a foreigner."""
    lesson_id = await _seed_lesson_owned_by_a()
    async with await _make_client() as client:
        b_headers = _headers(_USER_B_ID)
        for suffix in ("checkpoint", "mastery"):
            foreign = await client.get(
                f"/api/v1/lessons/{lesson_id}/player/{suffix}",
                headers=b_headers,
            )
            missing = await client.get(
                f"/api/v1/lessons/{_MISSING_LESSON_ID}/player/{suffix}",
                headers=b_headers,
            )
            _assert_equalized_not_found(foreign, lesson_id)
            _assert_equalized_not_found(missing, _MISSING_LESSON_ID)


async def test_non_owner_annotations_equal_missing_lesson() -> None:
    """Annotation read/write equals the missing-lesson 404 for a foreigner."""
    lesson_id = await _seed_lesson_owned_by_a()
    async with await _make_client() as client:
        b_headers = _headers(_USER_B_ID)
        foreign = await client.get(
            f"/api/v1/lessons/{lesson_id}/annotations",
            headers=b_headers,
        )
        missing = await client.get(
            f"/api/v1/lessons/{_MISSING_LESSON_ID}/annotations",
            headers=b_headers,
        )
        _assert_equalized_not_found(foreign, lesson_id)
        _assert_equalized_not_found(missing, _MISSING_LESSON_ID)


async def test_missing_session_advance_is_404_not_500() -> None:
    """Advance on an unknown session is 404 — never an unhandled 500."""
    lesson_id = await _seed_lesson_owned_by_a()
    async with await _make_client() as client:
        resp = await client.post(
            f"/api/v1/lessons/{lesson_id}/player/advance",
            json={"session_id": "session_does_not_exist"},
            headers=_headers(_USER_A_ID),
        )
        assert resp.status_code == 404, resp.text


async def test_missing_session_set_topic_is_404_not_500() -> None:
    """Set-topic on an unknown session is 404 — never an unhandled 500."""
    lesson_id = await _seed_lesson_owned_by_a()
    async with await _make_client() as client:
        resp = await client.post(
            f"/api/v1/lessons/{lesson_id}/player/set-topic",
            json={"session_id": "session_does_not_exist", "topic_index": 1},
            headers=_headers(_USER_A_ID),
        )
        assert resp.status_code == 404, resp.text
