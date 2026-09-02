"""Integration tests for the live export flow (P4 WS2).

Exercises the /api/v1/exports router end to end against the SQLite test DB:
create an owned presentation, create an export job for it, poll its status,
list exports, and cancel. Ownership is verified across two users (uniform 404).
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
from tests.conftest import TestSessionLocal

pytestmark = pytest.mark.asyncio

_USER_A_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
_USER_B_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")


class _RealUser:
    def __init__(self, user_id: uuid.UUID, email: str, name: str) -> None:
        self.id = user_id
        self.email = email
        self.name = name


@pytest_asyncio.fixture(autouse=True)
async def _seed_two_users_and_use_jwt_auth(setup_database: None):
    """Insert two users and override get_current_user with a JWT-decoding version."""
    from app.core.security import hash_password
    from app.models.user import User

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

    from app.services.lesson_player_service import _SESSIONS

    _SESSIONS.clear()


def _headers(user_id: uuid.UUID) -> dict[str, str]:
    token = create_access_token(user_id, role="user")
    return {"Authorization": f"Bearer {token}"}


async def _make_client() -> AsyncClient:
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test", follow_redirects=True)


async def _create_presentation(client: AsyncClient, user_id: uuid.UUID, title: str) -> str:
    resp = await client.post(
        "/api/v1/presentations",
        json={"title": title},
        headers=_headers(user_id),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


async def test_create_export_job_requires_ownership() -> None:
    async with await _make_client() as client:
        deck_id = await _create_presentation(client, _USER_A_ID, "Export Ownership Deck")

        # User B cannot create an export for User A's presentation (uniform 404)
        resp = await client.post(
            "/api/v1/exports",
            json={"format": "pdf", "kind": "notes", "targetId": deck_id},
            headers=_headers(_USER_B_ID),
        )
        assert resp.status_code == 404


async def test_create_and_poll_export_job() -> None:
    async with await _make_client() as client:
        deck_id = await _create_presentation(client, _USER_A_ID, "Export Poll Deck")
        resp = await client.post(
            "/api/v1/exports",
            json={"format": "pdf", "kind": "notes", "targetId": deck_id},
            headers=_headers(_USER_A_ID),
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()["data"]
        assert data["status"] == "queued"
        export_id = data["exportId"]

        # Owner can poll status
        resp = await client.get(f"/api/v1/exports/{export_id}", headers=_headers(_USER_A_ID))
        assert resp.status_code == 200
        assert resp.json()["data"]["exportId"] == export_id

        # Non-owner cannot read the job (uniform 404)
        resp = await client.get(f"/api/v1/exports/{export_id}", headers=_headers(_USER_B_ID))
        assert resp.status_code == 404


async def test_list_exports_is_scoped_and_paginated() -> None:
    async with await _make_client() as client:
        deck_a = await _create_presentation(client, _USER_A_ID, "List Deck A")
        deck_b = await _create_presentation(client, _USER_B_ID, "List Deck B")

        r_a = await client.post(
            "/api/v1/exports",
            json={"format": "pdf", "kind": "notes", "targetId": deck_a},
            headers=_headers(_USER_A_ID),
        )
        a_export_id = r_a.json()["data"]["exportId"]
        r_b = await client.post(
            "/api/v1/exports",
            json={"format": "pdf", "kind": "notes", "targetId": deck_b},
            headers=_headers(_USER_B_ID),
        )
        b_export_id = r_b.json()["data"]["exportId"]

        # User A's listing is scoped: it contains A's own job but never B's.
        resp = await client.get("/api/v1/exports", headers=_headers(_USER_A_ID))
        assert resp.status_code == 200
        items = resp.json()["data"]
        a_ids = [item["exportId"] for item in items]
        assert a_export_id in a_ids
        assert b_export_id not in a_ids
        assert all(item["kind"] == "notes" for item in items)


async def test_cancel_export_job_owner_only() -> None:
    async with await _make_client() as client:
        deck_id = await _create_presentation(client, _USER_A_ID, "Cancel Deck")
        resp = await client.post(
            "/api/v1/exports",
            json={"format": "pdf", "kind": "notes", "targetId": deck_id},
            headers=_headers(_USER_A_ID),
        )
        export_id = resp.json()["data"]["exportId"]

        resp = await client.delete(f"/api/v1/exports/{export_id}", headers=_headers(_USER_B_ID))
        assert resp.status_code == 404

        resp = await client.delete(f"/api/v1/exports/{export_id}", headers=_headers(_USER_A_ID))
        assert resp.status_code == 200


async def test_export_missing_target_rejected() -> None:
    async with await _make_client() as client:
        resp = await client.post(
            "/api/v1/exports",
            json={"format": "pdf", "kind": "notes"},
            headers=_headers(_USER_A_ID),
        )
        assert resp.status_code == 422


async def test_unauthenticated_export_rejected() -> None:
    async with await _make_client() as client:
        resp = await client.post(
            "/api/v1/exports",
            json={"format": "pdf", "kind": "notes", "targetId": "pres_x"},
        )
        assert resp.status_code == 401
