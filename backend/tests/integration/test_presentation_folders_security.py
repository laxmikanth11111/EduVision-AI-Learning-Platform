"""B9 presentation-folder ownership-response equalization tests.

``PresentationFolderService._assert_folder_owner`` answered a foreign folder with
``403 FORBIDDEN "You do not have access to this folder"`` while a missing folder
answered ``404 NOT_FOUND "Folder not found"`` — an existence/ownership oracle on
every folder operation (create-under-parent, update, delete, breadcrumbs).
Foreign folders must now be byte-equivalent to missing folders at the API
boundary (same status, code, and message), while the owner's own operations keep
working.

Folder ids are server-generated UUIDs; the discriminator seeds a folder for user A
and probes it as user B against a never-existing folder of the same shape.
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

_USER_A_ID = uuid.UUID("aaaaaaa1-1111-4111-8111-aaaaaaaaaaaa")
_USER_B_ID = uuid.UUID("bbbbbbb1-2222-4222-8222-bbbbbbbbbbbb")
_MISSING_FOLDER_ID = uuid.UUID("ffffffff-ffff-4fff-8fff-ffffffffffff")


class _RealUser:
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
            (_USER_A_ID, "fld_a@test.com", "Folder User A"),
            (_USER_B_ID, "fld_b@test.com", "Folder User B"),
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
        str(_USER_A_ID): _RealUser(_USER_A_ID, "fld_a@test.com", "Folder User A"),
        str(_USER_B_ID): _RealUser(_USER_B_ID, "fld_b@test.com", "Folder User B"),
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


async def _make_client() -> AsyncClient:
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test", follow_redirects=True)


def _assert_equalized_folder_not_found(resp, message: str = "Folder not found") -> None:
    """The 404 contract shared by missing and foreign folders (same context)."""
    assert resp.status_code == 404, resp.text
    body = resp.json()
    assert body["success"] is False
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["message"] == message


async def _create_folder(client: AsyncClient, name: str, *, owner: uuid.UUID) -> uuid.UUID:
    resp = await client.post(
        "/api/v1/folders",
        json={"name": name},
        headers=_headers(owner),
    )
    assert resp.status_code == 201, resp.text
    return uuid.UUID(resp.json()["data"]["id"])


async def test_owner_folder_operations_work() -> None:
    """User A can create, read breadcrumbs, update, and create children."""
    async with await _make_client() as client:
        a_headers = _headers(_USER_A_ID)
        folder_id = await _create_folder(client, "My Deck", owner=_USER_A_ID)

        crumbs = await client.get(
            f"/api/v1/folders/{folder_id}/breadcrumbs",
            headers=a_headers,
        )
        assert crumbs.status_code == 200, crumbs.text
        assert crumbs.json()["data"][0]["id"] == str(folder_id)

        updated = await client.patch(
            f"/api/v1/folders/{folder_id}",
            json={"name": "Renamed"},
            headers=a_headers,
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["data"]["name"] == "Renamed"

        child = await client.post(
            "/api/v1/folders",
            json={"name": "Child Folder", "parent_id": str(folder_id)},
            headers=a_headers,
        )
        assert child.status_code == 201, child.text


async def test_foreign_folder_update_matches_missing_folder() -> None:
    """B's PATCH of A's folder equals the missing-folder 404 (discriminator)."""
    async with await _make_client() as client:
        folder_id = await _create_folder(client, "Victim Folder", owner=_USER_A_ID)
        b_headers = _headers(_USER_B_ID)
        foreign = await client.patch(
            f"/api/v1/folders/{folder_id}",
            json={"name": "Hacked"},
            headers=b_headers,
        )
        missing = await client.patch(
            f"/api/v1/folders/{_MISSING_FOLDER_ID}",
            json={"name": "Hacked"},
            headers=b_headers,
        )
        _assert_equalized_folder_not_found(foreign)
        _assert_equalized_folder_not_found(missing)


async def test_foreign_folder_delete_matches_missing_folder() -> None:
    """B's DELETE of A's folder equals the missing-folder 404."""
    async with await _make_client() as client:
        folder_id = await _create_folder(client, "Victim Folder 2", owner=_USER_A_ID)
        b_headers = _headers(_USER_B_ID)
        foreign = await client.delete(f"/api/v1/folders/{folder_id}", headers=b_headers)
        missing = await client.delete(f"/api/v1/folders/{_MISSING_FOLDER_ID}", headers=b_headers)
        _assert_equalized_folder_not_found(foreign)
        _assert_equalized_folder_not_found(missing)


async def test_foreign_folder_breadcrumbs_match_missing_folder() -> None:
    """B's breadcrumbs read of A's folder equals the missing-folder 404."""
    async with await _make_client() as client:
        folder_id = await _create_folder(client, "Secret Tree", owner=_USER_A_ID)
        b_headers = _headers(_USER_B_ID)
        foreign = await client.get(
            f"/api/v1/folders/{folder_id}/breadcrumbs",
            headers=b_headers,
        )
        missing = await client.get(
            f"/api/v1/folders/{_MISSING_FOLDER_ID}/breadcrumbs",
            headers=b_headers,
        )
        _assert_equalized_folder_not_found(foreign)
        _assert_equalized_folder_not_found(missing)


async def test_create_under_foreign_parent_matches_missing_parent() -> None:
    """Creating under A's folder as B equals creating under a missing parent."""
    async with await _make_client() as client:
        folder_id = await _create_folder(client, "Parent Tree", owner=_USER_A_ID)
        b_headers = _headers(_USER_B_ID)
        foreign = await client.post(
            "/api/v1/folders",
            json={"name": "Child", "parent_id": str(folder_id)},
            headers=b_headers,
        )
        missing = await client.post(
            "/api/v1/folders",
            json={"name": "Child", "parent_id": str(_MISSING_FOLDER_ID)},
            headers=b_headers,
        )
        _assert_equalized_folder_not_found(foreign, message="Parent folder not found")
        _assert_equalized_folder_not_found(missing, message="Parent folder not found")
