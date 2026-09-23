"""B5 Runtime-session ownership boundary security tests.

B5 finding: the interactive video/animation **runtime write** endpoints
accepted an arbitrary client-supplied ``session_id`` and used it directly
as a global in-memory cache key without checking whether existing state
belongs to the authenticated caller:

* ``POST /api/v1/videos/runtime/sync``
* ``POST /api/v1/videos/runtime/bookmark``
* ``POST /api/v1/videos/runtime/assessment``
* ``POST /api/v1/animations/runtime/sync``

The corresponding read paths already enforce
``state.get("user_id") != str(user.id) -> data: null``.  The write paths did
not, so an authenticated user B could overwrite user A's runtime state and
inject bookmarks/assessments into A's session bucket.

These tests exercise the real ASGI app with JWT-based auth and prove the
FIXED boundary (404-equalized, victim state untouched):

* Cross-user sync/bookmark/assessment against A's session returns 404.
* A's runtime state / bookmark bucket remain byte-identical after the attack.
* The legitimate owner can still sync, update, bookmark and assess freely.
* Brand-new session keys remain creatable (first-write preserved).
* The equalized 404 exposes no ownership information.
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

_USER_A_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_USER_B_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

_SESSION_VIDEO = "b5_vid_session"
_SESSION_ANIM = "b5_anim_session"
_SESSION_FRESH = "b5_fresh_session"


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
            (_USER_A_ID, "runtime_sec_a@test.com", "Runtime Sec User A"),
            (_USER_B_ID, "runtime_sec_b@test.com", "Runtime Sec User B"),
        ):
            existing = await session.execute(
                __import__("sqlalchemy").select(User).where(User.id == uid)
            )
            if existing.scalar_one_or_none() is None:
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
        str(_USER_A_ID): _RealUser(_USER_A_ID, "runtime_sec_a@test.com", "Runtime Sec User A"),
        str(_USER_B_ID): _RealUser(_USER_B_ID, "runtime_sec_b@test.com", "Runtime Sec User B"),
    }

    async def _jwt_get_current_user(request: Request) -> _RealUser:
        token = request.headers.get("authorization", "")
        if token.startswith("Bearer "):
            token = token[7:]
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


@pytest_asyncio.fixture(autouse=True)
async def _clear_runtime_caches():
    """Reset the module-global in-memory runtime caches before each test.

    Keeps each scenario deterministic and isolated from prior/following tests
    that also exercise the shared BoundedCache stores.
    """
    from app.api.v1 import animation_runtime_router, video_runtime_router

    video_runtime_router._VIDEO_RUNTIME_STATES.clear()
    video_runtime_router._VIDEO_BOOKMARKS.clear()
    video_runtime_router._VIDEO_ASSESSMENTS.clear()
    animation_runtime_router._RUNTIME_STATES.clear()
    yield


def _headers(user_id: uuid.UUID) -> dict[str, str]:
    token = create_access_token(user_id, role="user")
    return {"Authorization": f"Bearer {token}"}


async def _make_client() -> AsyncClient:
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test", follow_redirects=True)


async def _video_sync(client: AsyncClient, user_id: uuid.UUID, session_id: str) -> None:
    resp = await client.post(
        "/api/v1/videos/runtime/sync",
        headers=_headers(user_id),
        json={
            "session_id": session_id,
            "video_id": "video_aaa",
            "scene_index": 1,
            "current_timestamp_ms": 5000.0,
        },
    )
    assert resp.status_code == 200


def _assert_equalized_404(resp) -> None:
    """The cross-user response must be a uniform, ownership-free 404."""
    assert resp.status_code == 404
    body = resp.json()
    assert body["success"] is False
    assert body["error"]["code"] == "NOT_FOUND"
    assert "user" not in body["error"]["message"].lower()
    assert "b" not in body["error"]["message"].lower()


# ── 1. Video sync cross-user isolation ────────────────────────────────────────


async def test_video_sync_cross_user_isolation() -> None:
    client = await _make_client()
    await _video_sync(client, _USER_A_ID, _SESSION_VIDEO)

    # A can read her own session.
    a_before = await client.get(
        f"/api/v1/videos/runtime/state/{_SESSION_VIDEO}", headers=_headers(_USER_A_ID)
    )
    assert a_before.status_code == 200
    a_state = a_before.json()["data"]
    assert a_state["user_id"] == str(_USER_A_ID)
    assert a_state["scene_index"] == 1

    # B attempts to overwrite A's session.
    b_sync = await client.post(
        "/api/v1/videos/runtime/sync",
        headers=_headers(_USER_B_ID),
        json={
            "session_id": _SESSION_VIDEO,
            "video_id": "video_bbb",
            "scene_index": 99,
            "current_timestamp_ms": 1.0,
        },
    )
    _assert_equalized_404(b_sync)

    # A's state is unchanged.
    a_after = await client.get(
        f"/api/v1/videos/runtime/state/{_SESSION_VIDEO}", headers=_headers(_USER_A_ID)
    )
    assert a_after.status_code == 200
    assert a_after.json()["data"] == a_state


# ── 2. Video bookmark cross-user isolation ────────────────────────────────────


async def test_video_bookmark_cross_user_isolation() -> None:
    from app.api.v1.video_runtime_router import _VIDEO_BOOKMARKS

    client = await _make_client()
    await _video_sync(client, _USER_A_ID, _SESSION_VIDEO)

    # A establishes her bookmark bucket.
    a_bm = await client.post(
        "/api/v1/videos/runtime/bookmark",
        headers=_headers(_USER_A_ID),
        json={
            "session_id": _SESSION_VIDEO,
            "video_id": "video_aaa",
            "time_ms": 12000.0,
            "title": "A's bookmark",
        },
    )
    assert a_bm.status_code == 201
    bucket_before = _VIDEO_BOOKMARKS.get(_SESSION_VIDEO)
    assert bucket_before
    assert all(item.get("user_id") == str(_USER_A_ID) for item in bucket_before)

    # B attempts to inject a bookmark into A's session bucket.
    b_bm = await client.post(
        "/api/v1/videos/runtime/bookmark",
        headers=_headers(_USER_B_ID),
        json={
            "session_id": _SESSION_VIDEO,
            "video_id": "video_bbb",
            "time_ms": 12345.0,
            "title": "Injected by B",
        },
    )
    _assert_equalized_404(b_bm)

    # A's bookmark bucket is unchanged (no B entry).
    bucket_after = _VIDEO_BOOKMARKS.get(_SESSION_VIDEO)
    assert bucket_after == bucket_before
    assert all(item.get("user_id") == str(_USER_A_ID) for item in bucket_after)


# ── 3. Video assessment cross-user isolation ──────────────────────────────────


async def test_video_assessment_cross_user_isolation() -> None:
    from app.api.v1.video_runtime_router import _VIDEO_ASSESSMENTS

    client = await _make_client()
    await _video_sync(client, _USER_A_ID, _SESSION_VIDEO)

    a_as = await client.post(
        "/api/v1/videos/runtime/assessment",
        headers=_headers(_USER_A_ID),
        json={
            "session_id": _SESSION_VIDEO,
            "video_id": "video_aaa",
            "scene_index": 1,
            "selected_option": "Decode option A",
        },
    )
    assert a_as.status_code == 200
    assessments_before = _VIDEO_ASSESSMENTS.get(_SESSION_VIDEO)
    assert assessments_before
    assert all(item.get("user_id") == str(_USER_A_ID) for item in assessments_before)

    b_as = await client.post(
        "/api/v1/videos/runtime/assessment",
        headers=_headers(_USER_B_ID),
        json={
            "session_id": _SESSION_VIDEO,
            "video_id": "video_bbb",
            "scene_index": 1,
            "selected_option": "Injected by B",
        },
    )
    _assert_equalized_404(b_as)

    assessments_after = _VIDEO_ASSESSMENTS.get(_SESSION_VIDEO)
    assert assessments_after == assessments_before
    assert all(item.get("user_id") == str(_USER_A_ID) for item in assessments_after)


# ── 4. Animation sync cross-user isolation ────────────────────────────────────


async def test_animation_sync_cross_user_isolation() -> None:
    client = await _make_client()

    a_sync = await client.post(
        "/api/v1/animations/runtime/sync",
        headers=_headers(_USER_A_ID),
        json={
            "session_id": _SESSION_ANIM,
            "blueprint_id": "anim_aaa",
            "scene_index": 2,
        },
    )
    assert a_sync.status_code == 200

    a_before = await client.get(
        f"/api/v1/animations/runtime/state/{_SESSION_ANIM}", headers=_headers(_USER_A_ID)
    )
    assert a_before.status_code == 200
    a_state = a_before.json()["data"]
    assert a_state["user_id"] == str(_USER_A_ID)

    b_sync = await client.post(
        "/api/v1/animations/runtime/sync",
        headers=_headers(_USER_B_ID),
        json={
            "session_id": _SESSION_ANIM,
            "blueprint_id": "anim_bbb",
            "scene_index": 88,
        },
    )
    _assert_equalized_404(b_sync)

    a_after = await client.get(
        f"/api/v1/animations/runtime/state/{_SESSION_ANIM}", headers=_headers(_USER_A_ID)
    )
    assert a_after.status_code == 200
    assert a_after.json()["data"] == a_state


# ── 5. Legitimate owner behavior ──────────────────────────────────────────────


async def test_legitimate_owner_video_sync_update() -> None:
    client = await _make_client()
    await _video_sync(client, _USER_A_ID, _SESSION_VIDEO)

    # Owner updates her own scene.
    update = await client.post(
        "/api/v1/videos/runtime/sync",
        headers=_headers(_USER_A_ID),
        json={
            "session_id": _SESSION_VIDEO,
            "video_id": "video_aaa",
            "scene_index": 3,
            "current_timestamp_ms": 15000.0,
        },
    )
    assert update.status_code == 200
    assert update.json()["data"]["scene_index"] == 3

    state = await client.get(
        f"/api/v1/videos/runtime/state/{_SESSION_VIDEO}", headers=_headers(_USER_A_ID)
    )
    assert state.status_code == 200
    assert state.json()["data"]["user_id"] == str(_USER_A_ID)
    assert state.json()["data"]["scene_index"] == 3


async def test_legitimate_owner_bookmark_and_assessment() -> None:
    client = await _make_client()
    await _video_sync(client, _USER_A_ID, _SESSION_VIDEO)

    bm = await client.post(
        "/api/v1/videos/runtime/bookmark",
        headers=_headers(_USER_A_ID),
        json={
            "session_id": _SESSION_VIDEO,
            "video_id": "video_aaa",
            "time_ms": 1000.0,
            "title": "Owner bookmark",
        },
    )
    assert bm.status_code == 201
    assert bm.json()["data"]["user_id"] == str(_USER_A_ID)

    asm = await client.post(
        "/api/v1/videos/runtime/assessment",
        headers=_headers(_USER_A_ID),
        json={
            "session_id": _SESSION_VIDEO,
            "video_id": "video_aaa",
            "scene_index": 1,
            "selected_option": "Decode owner answer",
        },
    )
    assert asm.status_code == 200
    assert asm.json()["data"]["user_id"] == str(_USER_A_ID)


async def test_legitimate_owner_animation_sync() -> None:
    client = await _make_client()

    sync = await client.post(
        "/api/v1/animations/runtime/sync",
        headers=_headers(_USER_A_ID),
        json={
            "session_id": _SESSION_ANIM,
            "blueprint_id": "anim_aaa",
            "scene_index": 4,
        },
    )
    assert sync.status_code == 200
    assert sync.json()["data"]["user_id"] == str(_USER_A_ID)

    state = await client.get(
        f"/api/v1/animations/runtime/state/{_SESSION_ANIM}", headers=_headers(_USER_A_ID)
    )
    assert state.status_code == 200
    assert state.json()["data"]["scene_index"] == 4


# ── 6. Fresh-key behavior ─────────────────────────────────────────────────────


async def test_fresh_key_creation_still_works() -> None:
    client = await _make_client()

    # A brand-new session key is creatable by a fresh user with no DB record.
    video = await client.post(
        "/api/v1/videos/runtime/sync",
        headers=_headers(_USER_B_ID),
        json={
            "session_id": _SESSION_FRESH,
            "video_id": "video_fresh",
            "scene_index": 0,
            "current_timestamp_ms": 10.0,
        },
    )
    assert video.status_code == 200

    anim = await client.post(
        "/api/v1/animations/runtime/sync",
        headers=_headers(_USER_B_ID),
        json={
            "session_id": _SESSION_FRESH,
            "blueprint_id": "anim_fresh",
            "scene_index": 0,
        },
    )
    assert anim.status_code == 200

    bm = await client.post(
        "/api/v1/videos/runtime/bookmark",
        headers=_headers(_USER_B_ID),
        json={
            "session_id": _SESSION_FRESH,
            "video_id": "video_fresh",
            "time_ms": 500.0,
            "title": "Fresh bookmark",
        },
    )
    assert bm.status_code == 201

    asm = await client.post(
        "/api/v1/videos/runtime/assessment",
        headers=_headers(_USER_B_ID),
        json={
            "session_id": _SESSION_FRESH,
            "video_id": "video_fresh",
            "scene_index": 0,
            "selected_option": "Decode fresh",
        },
    )
    assert asm.status_code == 200


# ── 7. 404 equalization / no ownership leak ───────────────────────────────────


async def test_equalized_404_reveals_no_ownership() -> None:
    client = await _make_client()
    await _video_sync(client, _USER_A_ID, _SESSION_VIDEO)

    # Cross-user write surfaces a uniform NOT_FOUND without ownership detail.
    resp = await client.post(
        "/api/v1/videos/runtime/sync",
        headers=_headers(_USER_B_ID),
        json={
            "session_id": _SESSION_VIDEO,
            "video_id": "video_bbb",
            "scene_index": 7,
            "current_timestamp_ms": 7.0,
        },
    )
    _assert_equalized_404(resp)
    assert "AAAAAAAA" not in str(resp.json()["error"])

    # Read side stays equalized: cross-user and nonexistent reads both render
    # the same shape (success with data:null).
    foreign_read = await client.get(
        f"/api/v1/videos/runtime/state/{_SESSION_VIDEO}", headers=_headers(_USER_B_ID)
    )
    missing_read = await client.get(
        "/api/v1/videos/runtime/state/does_not_exist_xyz", headers=_headers(_USER_B_ID)
    )
    assert foreign_read.status_code == 200
    assert missing_read.status_code == 200
    assert foreign_read.json()["data"] is None
    assert missing_read.json()["data"] is None
    assert foreign_read.json() == missing_read.json()
