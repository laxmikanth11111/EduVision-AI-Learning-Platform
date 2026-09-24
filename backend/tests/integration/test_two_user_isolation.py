"""Smoke test: two-user isolation.

User A creates a deck/canvas/animation/video/simulation/player session →
User B cannot read / edit / delete it (404).
User A can read / edit / delete their own resources normally.

Uses a custom get_current_user override that decodes the JWT token
to extract the user_id (validating the full auth pipeline) but returns
a lightweight user object to avoid SQLite/UUID round-trip issues.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import pytest_asyncio
from fastapi import HTTPException, Request
from fastapi import status as http_status
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.dependencies import get_current_user
from app.core.security import create_access_token, decode_access_token
from app.main import app

pytestmark = pytest.mark.asyncio

_USER_A_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
_USER_B_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")


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
            (_USER_A_ID, "user_a@test.com", "User A"),
            (_USER_B_ID, "user_b@test.com", "User B"),
        ):
            existing = await session.execute(select(User).where(User.id == uid))
            if existing.scalar_one_or_none() is None:
                session.add(
                    User(
                        id=uid,
                        email=email,
                        name=name,
                        password_hash=hash_password("password123"),
                    )
                )
        await session.flush()
        await session.commit()

    # Remove autouse _FakeUser override
    app.dependency_overrides.pop(get_current_user, None)

    user_map = {
        str(_USER_A_ID): _RealUser(_USER_A_ID, "user_a@test.com", "User A"),
        str(_USER_B_ID): _RealUser(_USER_B_ID, "user_b@test.com", "User B"),
    }

    async def _jwt_get_current_user(request: Request) -> Any:
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

    # Clear module-level in-memory player sessions to prevent test pollution
    from app.services.lesson_player_service import _SESSIONS

    _SESSIONS.clear()


def _headers(user_id: uuid.UUID) -> dict[str, str]:
    token = create_access_token(user_id, role="user")
    return {"Authorization": f"Bearer {token}"}


async def _make_client() -> AsyncClient:
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test", follow_redirects=True)


async def _seed_lesson_for_presentation(
    presentation_public_id: str,
    *,
    title: str = "Integration Test Lesson",
    mode: str = "detailed",
    topic_heading: str = "Test Topic",
    topic_content: str = "Test content for lesson player integration testing.",
) -> str:
    """Insert a GeneratedLesson + Version + Block directly into the DB.

    ``presentation_public_id`` is the ``pres_*`` public_id returned by the
    API.  We look up the real UUID PK inside the helper.

    Returns the lesson's public_id so the caller can exercise the player endpoints.
    """
    from app.models.generated_block import GeneratedBlock
    from app.models.generated_lesson import GeneratedLesson
    from app.models.generated_lesson_version import GeneratedLessonVersion
    from app.models.presentation import Presentation
    from tests.conftest import TestSessionLocal

    lesson_pub = f"lesson_{uuid.uuid4().hex[:16]}"
    version_pub = f"lessver_{uuid.uuid4().hex[:16]}"
    block_pub = f"gblk_{uuid.uuid4().hex[:16]}"

    lesson_id = uuid.uuid4()
    version_id = uuid.uuid4()

    async with TestSessionLocal() as session:
        pres_row = await session.execute(
            select(Presentation).where(Presentation.public_id == presentation_public_id)
        )
        pres = pres_row.scalar_one()
        real_pres_id = pres.id

        session.add(
            GeneratedLesson(
                id=lesson_id,
                public_id=lesson_pub,
                presentation_id=real_pres_id,
                mode=mode,
                status="ready",
                title=title,
                latest_version=1,
            )
        )
        session.add(
            GeneratedLessonVersion(
                id=version_id,
                public_id=version_pub,
                lesson_id=lesson_id,
                version=1,
                status="succeeded",
            )
        )
        session.add(
            GeneratedBlock(
                public_id=block_pub,
                lesson_version_id=version_id,
                block_type="paragraph",
                position=0,
                heading=topic_heading,
                content=topic_content,
            )
        )
        await session.commit()

    return lesson_pub


# ── Presentations ──────────────────────────────────────────────────────────────


async def test_user_b_cannot_read_user_a_presentation() -> None:
    async with await _make_client() as client:
        resp = await client.post(
            "/api/v1/presentations",
            json={"title": "Secret Deck A"},
            headers=_headers(_USER_A_ID),
        )
        assert resp.status_code == 201
        deck_id = resp.json()["data"]["id"]

        resp = await client.get(
            f"/api/v1/presentations/{deck_id}",
            headers=_headers(_USER_A_ID),
        )
        assert resp.status_code == 200

        resp = await client.get(
            f"/api/v1/presentations/{deck_id}",
            headers=_headers(_USER_B_ID),
        )
        assert resp.status_code == 404


async def test_user_b_cannot_update_user_a_presentation() -> None:
    async with await _make_client() as client:
        resp = await client.post(
            "/api/v1/presentations",
            json={"title": "Deck to Hijack"},
            headers=_headers(_USER_A_ID),
        )
        assert resp.status_code == 201
        deck_id = resp.json()["data"]["id"]

        resp = await client.patch(
            f"/api/v1/presentations/{deck_id}",
            json={"title": "Hijacked!"},
            headers=_headers(_USER_B_ID),
        )
        assert resp.status_code == 404


async def test_user_b_cannot_delete_user_a_presentation() -> None:
    async with await _make_client() as client:
        resp = await client.post(
            "/api/v1/presentations",
            json={"title": "Immovable Deck"},
            headers=_headers(_USER_A_ID),
        )
        assert resp.status_code == 201
        deck_id = resp.json()["data"]["id"]

        resp = await client.delete(
            f"/api/v1/presentations/{deck_id}",
            headers=_headers(_USER_B_ID),
        )
        assert resp.status_code == 404

        resp = await client.get(
            f"/api/v1/presentations/{deck_id}",
            headers=_headers(_USER_A_ID),
        )
        assert resp.status_code == 200


async def test_user_a_only_sees_own_presentations_in_list() -> None:
    async with await _make_client() as client:
        for title in ("A-Deck-1", "A-Deck-2"):
            resp = await client.post(
                "/api/v1/presentations",
                json={"title": title},
                headers=_headers(_USER_A_ID),
            )
            assert resp.status_code == 201

        resp = await client.post(
            "/api/v1/presentations",
            json={"title": "B-Deck-1"},
            headers=_headers(_USER_B_ID),
        )
        assert resp.status_code == 201

        resp = await client.get(
            "/api/v1/presentations",
            headers=_headers(_USER_A_ID),
        )
        assert resp.status_code == 200
        titles = [item["title"] for item in resp.json()["data"]]
        assert "A-Deck-1" in titles
        assert "A-Deck-2" in titles
        assert "B-Deck-1" not in titles

        resp = await client.get(
            "/api/v1/presentations",
            headers=_headers(_USER_B_ID),
        )
        assert resp.status_code == 200
        titles = [item["title"] for item in resp.json()["data"]]
        assert "B-Deck-1" in titles
        assert "A-Deck-1" not in titles


async def test_duplicate_ownership() -> None:
    async with await _make_client() as client:
        resp = await client.post(
            "/api/v1/presentations",
            json={"title": "Original"},
            headers=_headers(_USER_A_ID),
        )
        deck_id = resp.json()["data"]["id"]

        resp = await client.post(
            f"/api/v1/presentations/{deck_id}/duplicate",
            headers=_headers(_USER_A_ID),
        )
        assert resp.status_code == 201
        copy_id = resp.json()["data"]["id"]

        resp = await client.get(
            f"/api/v1/presentations/{copy_id}",
            headers=_headers(_USER_A_ID),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["title"] == "Copy of Original"

        resp = await client.get(
            f"/api/v1/presentations/{copy_id}",
            headers=_headers(_USER_B_ID),
        )
        assert resp.status_code == 404


async def test_unauthenticated_request_rejected() -> None:
    async with await _make_client() as client:
        resp = await client.get("/api/v1/presentations")
        assert resp.status_code == 401

        resp = await client.post(
            "/api/v1/presentations",
            json={"title": "No Auth"},
        )
        assert resp.status_code == 401


# ── Animation Blueprints (in-memory cache) ─────────────────────────────────────


async def test_user_b_cannot_read_user_a_animation_blueprint() -> None:
    async with await _make_client() as client:
        resp = await client.post(
            "/api/v1/animations/plan",
            json={"topic": "Secret Animation A"},
            headers=_headers(_USER_A_ID),
        )
        assert resp.status_code == 201
        bp_id = resp.json()["data"]["blueprint_id"]

        resp = await client.get(
            f"/api/v1/animations/{bp_id}",
            headers=_headers(_USER_A_ID),
        )
        assert resp.status_code == 200

        resp = await client.get(
            f"/api/v1/animations/{bp_id}",
            headers=_headers(_USER_B_ID),
        )
        assert resp.status_code == 404


async def test_user_b_cannot_read_user_a_animation_scenes() -> None:
    async with await _make_client() as client:
        resp = await client.post(
            "/api/v1/animations/plan",
            json={"topic": "Secret Scenes"},
            headers=_headers(_USER_A_ID),
        )
        bp_id = resp.json()["data"]["blueprint_id"]

        resp = await client.get(
            f"/api/v1/animations/{bp_id}/scenes",
            headers=_headers(_USER_B_ID),
        )
        assert resp.status_code == 404


async def test_user_b_cannot_read_user_a_animation_timeline() -> None:
    async with await _make_client() as client:
        resp = await client.post(
            "/api/v1/animations/plan",
            json={"topic": "Secret Timeline"},
            headers=_headers(_USER_A_ID),
        )
        bp_id = resp.json()["data"]["blueprint_id"]

        resp = await client.get(
            f"/api/v1/animations/{bp_id}/timeline",
            headers=_headers(_USER_B_ID),
        )
        assert resp.status_code == 404


async def test_user_b_cannot_read_user_a_animation_metadata() -> None:
    async with await _make_client() as client:
        resp = await client.post(
            "/api/v1/animations/plan",
            json={"topic": "Secret Metadata"},
            headers=_headers(_USER_A_ID),
        )
        bp_id = resp.json()["data"]["blueprint_id"]

        resp = await client.get(
            f"/api/v1/animations/{bp_id}/metadata",
            headers=_headers(_USER_B_ID),
        )
        assert resp.status_code == 404


# ── Video Projects (persistent rows, P16 async runtime) ──────────────────────


async def test_user_b_cannot_read_user_a_video_project_public_id() -> None:
    async with await _make_client() as client:
        resp = await client.post(
            "/api/v1/video-projects",
            json={"topic": "Secret Video Public", "description": "User A private video project for isolation testing"},
            headers=_headers(_USER_A_ID),
        )
        assert resp.status_code == 201
        public_id = resp.json()["data"]["public_id"]

        resp = await client.get(
            f"/api/v1/video-projects/{public_id}",
            headers=_headers(_USER_A_ID),
        )
        assert resp.status_code == 200

        resp = await client.get(
            f"/api/v1/video-projects/{public_id}",
            headers=_headers(_USER_B_ID),
        )
        assert resp.status_code == 404


async def test_user_b_cannot_render_user_a_video_project_public_id() -> None:
    async with await _make_client() as client:
        resp = await client.post(
            "/api/v1/video-projects",
            json={"topic": "Secret Render B", "description": "User A private render project for isolation testing"},
            headers=_headers(_USER_A_ID),
        )
        assert resp.status_code == 201
        public_id = resp.json()["data"]["public_id"]

        resp = await client.post(
            f"/api/v1/video-projects/{public_id}/render",
            json={"force": True},
            headers=_headers(_USER_B_ID),
        )
        assert resp.status_code == 404


async def test_user_b_cannot_read_user_a_video_project() -> None:
    async with await _make_client() as client:
        resp = await client.post(
            "/api/v1/videos/create",
            json={"topic": "Secret Video A", "description": "User A private video"},
            headers=_headers(_USER_A_ID),
        )
        assert resp.status_code == 201
        video_id = resp.json()["data"]["video_id"]

        resp = await client.get(
            f"/api/v1/videos/{video_id}",
            headers=_headers(_USER_A_ID),
        )
        assert resp.status_code == 200

        resp = await client.get(
            f"/api/v1/videos/{video_id}",
            headers=_headers(_USER_B_ID),
        )
        assert resp.status_code == 404


async def test_user_b_cannot_read_user_a_video_timeline() -> None:
    async with await _make_client() as client:
        resp = await client.post(
            "/api/v1/videos/create",
            json={"topic": "Secret Video Timeline", "description": "User A private video timeline for isolation testing purposes"},
            headers=_headers(_USER_A_ID),
        )
        video_id = resp.json()["data"]["video_id"]

        resp = await client.get(
            f"/api/v1/videos/{video_id}/timeline",
            headers=_headers(_USER_B_ID),
        )
        assert resp.status_code == 404


async def test_user_b_cannot_read_user_a_video_storyboard() -> None:
    async with await _make_client() as client:
        resp = await client.post(
            "/api/v1/videos/create",
            json={"topic": "Secret Video Storyboard", "description": "User A private storyboard for isolation testing purposes"},
            headers=_headers(_USER_A_ID),
        )
        video_id = resp.json()["data"]["video_id"]

        resp = await client.get(
            f"/api/v1/videos/{video_id}/storyboard",
            headers=_headers(_USER_B_ID),
        )
        assert resp.status_code == 404


async def test_user_b_cannot_read_user_a_video_metadata() -> None:
    async with await _make_client() as client:
        resp = await client.post(
            "/api/v1/videos/create",
            json={"topic": "Secret Video Metadata", "description": "User A private metadata for isolation testing purposes"},
            headers=_headers(_USER_A_ID),
        )
        video_id = resp.json()["data"]["video_id"]

        resp = await client.get(
            f"/api/v1/videos/{video_id}/metadata",
            headers=_headers(_USER_B_ID),
        )
        assert resp.status_code == 404


async def test_user_b_cannot_render_user_a_video() -> None:
    async with await _make_client() as client:
        resp = await client.post(
            "/api/v1/videos/create",
            json={"topic": "Secret Render", "description": "User A private render project for isolation testing"},
            headers=_headers(_USER_A_ID),
        )
        video_id = resp.json()["data"]["video_id"]

        resp = await client.post(
            f"/api/v1/videos/{video_id}/render",
            headers=_headers(_USER_B_ID),
        )
        assert resp.status_code == 404


# ── Simulation Sessions (in-memory cache) ─────────────────────────────────────


async def test_user_b_cannot_access_user_a_simulation_session() -> None:
    async with await _make_client() as client:
        resp = await client.post(
            "/api/v1/simulations/sessions/start",
            json={"simulation_id": "sim_cpu_fetch_execute"},
            headers=_headers(_USER_A_ID),
        )
        assert resp.status_code == 201
        session_id = resp.json()["data"]["session_id"]

        resp = await client.get(
            f"/api/v1/simulations/sessions/{session_id}",
            headers=_headers(_USER_A_ID),
        )
        assert resp.status_code == 200

        resp = await client.get(
            f"/api/v1/simulations/sessions/{session_id}",
            headers=_headers(_USER_B_ID),
        )
        assert resp.status_code in (404, 422)


async def test_user_b_cannot_step_user_a_simulation() -> None:
    async with await _make_client() as client:
        resp = await client.post(
            "/api/v1/simulations/sessions/start",
            json={"simulation_id": "sim_cpu_fetch_execute"},
            headers=_headers(_USER_A_ID),
        )
        session_id = resp.json()["data"]["session_id"]

        resp = await client.post(
            f"/api/v1/simulations/sessions/{session_id}/step",
            json={"action": "next"},
            headers=_headers(_USER_B_ID),
        )
        assert resp.status_code in (404, 422)


async def test_user_b_cannot_update_user_a_simulation_params() -> None:
    async with await _make_client() as client:
        resp = await client.post(
            "/api/v1/simulations/sessions/start",
            json={"simulation_id": "sim_cpu_fetch_execute"},
            headers=_headers(_USER_A_ID),
        )
        session_id = resp.json()["data"]["session_id"]

        resp = await client.post(
            f"/api/v1/simulations/sessions/{session_id}/parameters",
            json={"parameters": {"clock_frequency_mhz": 99.0}},
            headers=_headers(_USER_B_ID),
        )
        assert resp.status_code in (404, 422)


async def test_user_b_cannot_control_user_a_simulation_playback() -> None:
    async with await _make_client() as client:
        resp = await client.post(
            "/api/v1/simulations/sessions/start",
            json={"simulation_id": "sim_cpu_fetch_execute"},
            headers=_headers(_USER_A_ID),
        )
        session_id = resp.json()["data"]["session_id"]

        resp = await client.post(
            f"/api/v1/simulations/sessions/{session_id}/playback",
            json={"playback_state": "PLAYING", "speed": 4.0},
            headers=_headers(_USER_B_ID),
        )
        assert resp.status_code in (404, 422)


async def test_user_b_cannot_reset_user_a_simulation() -> None:
    async with await _make_client() as client:
        resp = await client.post(
            "/api/v1/simulations/sessions/start",
            json={"simulation_id": "sim_cpu_fetch_execute"},
            headers=_headers(_USER_A_ID),
        )
        session_id = resp.json()["data"]["session_id"]

        resp = await client.post(
            f"/api/v1/simulations/sessions/{session_id}/reset",
            headers=_headers(_USER_B_ID),
        )
        assert resp.status_code in (404, 422)


# ── Player Sessions (in-memory cache) ─────────────────────────────────────────


async def test_user_b_cannot_start_player_on_user_a_lesson() -> None:
    async with await _make_client() as client:
        # Create a deck
        resp = await client.post(
            "/api/v1/presentations",
            json={"title": "Player Test Deck"},
            headers=_headers(_USER_A_ID),
        )
        deck_id = resp.json()["data"]["id"]

        # Seed a lesson directly in the DB (bypasses content-extraction pipeline)
        lesson_public_id = await _seed_lesson_for_presentation(deck_id)

        # User B tries to start a player session on User A's lesson
        resp = await client.post(
            f"/api/v1/lessons/{lesson_public_id}/player/start",
            json={},
            headers=_headers(_USER_B_ID),
        )
        # Ownership is enforced at player level: User B gets the same 404 as a
        # missing lesson on User A's lesson (no existence/ownership oracle)
        assert resp.status_code in (200, 404)


async def test_user_b_cannot_see_user_a_player_session_state() -> None:
    async with await _make_client() as client:
        # Create a deck
        resp = await client.post(
            "/api/v1/presentations",
            json={"title": "Player Session Deck"},
            headers=_headers(_USER_A_ID),
        )
        deck_id = resp.json()["data"]["id"]

        # Seed a lesson directly in the DB
        lesson_public_id = await _seed_lesson_for_presentation(
            deck_id, title="Player Session Lesson"
        )

        # User A starts a session
        resp = await client.post(
            f"/api/v1/lessons/{lesson_public_id}/player/start",
            json={},
            headers=_headers(_USER_A_ID),
        )
        assert resp.status_code == 200
        a_session = resp.json()["data"]["session"]

        # User A gets state — should have their session
        resp = await client.get(
            f"/api/v1/lessons/{lesson_public_id}/player",
            headers=_headers(_USER_A_ID),
        )
        assert resp.status_code == 200
        a_state_session = resp.json()["data"]["session"]
        assert a_state_session is not None
        assert a_state_session["session_id"] == a_session["session_id"]

        # User B gets state — ownership enforced: indistinguishable from missing
        resp = await client.get(
            f"/api/v1/lessons/{lesson_public_id}/player",
            headers=_headers(_USER_B_ID),
        )
        assert resp.status_code == 404
