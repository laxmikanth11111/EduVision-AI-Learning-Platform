"""P11 Personalisation API security / isolation tests.

Exercises the new plan / goal / path endpoints over the real ASGI app with
JWT-based auth, validating the full auth + ownership pipeline:

* Unauthenticated requests are rejected with 401 on every P11 endpoint.
* The owner can read/create their own path, plan and goals.
* User B (authenticated) receives 404 (never 403/500) for every cross-user
  access to A's goals and plan items.
* Completing a goal whose target is unmet is 409 (never silently "achieved").
* Goal progress is server-derived (memory average), never client-supplied.
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

_USER_A_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
_USER_B_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")


class _RealUser:
    """Lightweight user stand-in built from a decoded JWT."""

    def __init__(self, user_id: uuid.UUID, email: str, name: str) -> None:
        self.id = user_id
        self.email = email
        self.name = name


@pytest_asyncio.fixture(autouse=True)
async def _seed_two_users_and_use_jwt_auth(setup_database: None):
    from app.core.security import hash_password
    from app.models.user import User
    from tests.conftest import TestSessionLocal

    async with TestSessionLocal() as session:
        for uid, email, name in (
            (_USER_A_ID, "p11_a@test.com", "P11 User A"),
            (_USER_B_ID, "p11_b@test.com", "P11 User B"),
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
        await session.commit()

    app.dependency_overrides.pop(get_current_user, None)

    user_map = {
        str(_USER_A_ID): _RealUser(_USER_A_ID, "p11_a@test.com", "P11 User A"),
        str(_USER_B_ID): _RealUser(_USER_B_ID, "p11_b@test.com", "P11 User B"),
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


def _headers(user_id: uuid.UUID) -> dict[str, str]:
    token = create_access_token(user_id, role="user")
    return {"Authorization": f"Bearer {token}"}


async def _make_client() -> AsyncClient:
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test", follow_redirects=True)


async def _seed_learner_a() -> dict[str, str]:
    """Seed User A with a full learner profile; returns public-id lookups."""
    from tests.conftest import TestSessionLocal
    from tests.learner_progress_helpers import seed_learner

    async with TestSessionLocal() as session:
        return await seed_learner(session, _USER_A_ID, email="p11_a@test.com")


async def test_unauthenticated_p11_requests_rejected() -> None:
    async with await _make_client() as client:
        for method, url in (
            ("GET", "/api/v1/me/plan/today"),
            ("POST", "/api/v1/me/plan/today/items/review.x/complete"),
            ("GET", "/api/v1/me/goals"),
            ("POST", "/api/v1/me/goals"),
            ("POST", "/api/v1/me/goals/goal_x/complete"),
            ("GET", "/api/v1/me/path"),
        ):
            resp = await client.request(method, url)
            assert resp.status_code == 401, f"{method} {url}"


async def test_owner_reads_path_plan_and_goals() -> None:
    await _seed_learner_a()
    async with await _make_client() as client:
        a_headers = _headers(_USER_A_ID)

        resp = await client.get("/api/v1/me/path", headers=a_headers)
        assert resp.status_code == 200, resp.text
        path = resp.json()["data"]
        assert path["id"].startswith("path_")
        assert all(s["lesson_id"].startswith("lesson_") for s in path["sequence"])

        resp = await client.get("/api/v1/me/plan/today?limit=0", headers=a_headers)
        assert resp.status_code == 200, resp.text
        plan = resp.json()["data"]
        assert "items" in plan
        assert "date" in plan
        assert all(it["deep_link"].startswith("/frontend/") for it in plan["items"])

        resp = await client.post(
            "/api/v1/me/goals",
            json={
                "goal_type": "mastery_target",
                "title": "Reach 90% mastery",
                "target_value": 90.0,
            },
            headers=a_headers,
        )
        assert resp.status_code == 200, resp.text
        goal = resp.json()["data"]["goal"]
        assert goal["id"].startswith("goal_")
        # Average mastery is server-derived from memory (62.5), not client-supplied.
        assert goal["current_value"] == 62.5


async def test_cross_user_goal_access_is_404() -> None:
    await _seed_learner_a()
    async with await _make_client() as client:
        a_headers = _headers(_USER_A_ID)
        b_headers = _headers(_USER_B_ID)

        resp = await client.post(
            "/api/v1/me/goals",
            json={"goal_type": "streak_days", "title": "7 day streak", "target_value": 7.0},
            headers=a_headers,
        )
        goal_id = resp.json()["data"]["goal"]["id"]

        # User B cannot read or complete User A's goal (404-equalized).
        for method, url in (
            ("GET", f"/api/v1/me/goals/{goal_id}"),
            ("POST", f"/api/v1/me/goals/{goal_id}/complete"),
        ):
            resp = await client.request(method, url, headers=b_headers)
            assert resp.status_code == 404, f"{method} {url}"


async def test_complete_goal_conflict_then_achieved() -> None:
    await _seed_learner_a()
    async with await _make_client() as client:
        a_headers = _headers(_USER_A_ID)

        # Target above derived average mastery -> conflict (not silently passed).
        resp = await client.post(
            "/api/v1/me/goals",
            json={"goal_type": "mastery_target", "title": "90% mastery", "target_value": 90.0},
            headers=a_headers,
        )
        goal_id = resp.json()["data"]["goal"]["id"]
        resp = await client.post(
            f"/api/v1/me/goals/{goal_id}/complete", headers=a_headers
        )
        assert resp.status_code == 409, resp.text

        # A lesson_completion goal about the already-completed lesson -> achieved.
        resp = await client.post(
            "/api/v1/me/goals",
            json={"goal_type": "lesson_completion", "title": "Finish a lesson", "target_value": 1.0},
            headers=a_headers,
        )
        goal_id = resp.json()["data"]["goal"]["id"]
        resp = await client.post(
            f"/api/v1/me/goals/{goal_id}/complete", headers=a_headers
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["status"] == "achieved"


async def test_today_plan_item_completion_is_learner_scoped() -> None:
    await _seed_learner_a()
    async with await _make_client() as client:
        a_headers = _headers(_USER_A_ID)
        b_headers = _headers(_USER_B_ID)

        resp = await client.get("/api/v1/me/plan/today", headers=a_headers)
        assert resp.status_code == 200, resp.text
        items = resp.json()["data"]["items"]
        assert items, "expected at least one plan item for the seeded learner"
        a_item_key = items[0]["item_key"]

        # User A can complete their own practice/lesson item.
        resp = await client.post(
            f"/api/v1/me/plan/today/items/{a_item_key}/complete",
            headers=a_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["status"] == "completed"

        # User B cannot complete User A's plan item (no such item in B's plan).
        resp = await client.post(
            f"/api/v1/me/plan/today/items/{a_item_key}/complete",
            headers=b_headers,
        )
        assert resp.status_code == 404, resp.text
