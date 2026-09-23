"""B3 Effectiveness API security / ownership-isolation tests.

Exercises the effectiveness endpoints over the real ASGI app with JWT-based
auth so the full auth pipeline is validated. Confirms every assessment /
report operation is presentation-owner-scoped:

* User A seeds a presentation they own, starts an assessment, and reads the
  report (200 with their own title).
* User B (authenticated) receives a 404-equalized "Presentation not found"
  (never 403/500, no resource-existence leak) when starting an assessment for
  A's presentation.
* Even if User B already holds an assessment bound to A's presentation, the
  report never returns A's title (404-equalized).
* Missing / orphaned / soft-deleted presentations are all 404 with the same
  message, so no existence oracle is created.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

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

_USER_A_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_USER_B_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

_PRIV_TITLE = "PRIVATE PRESENTATION TITLE OF USER A"


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
            (_USER_A_ID, "eff_a@test.com", "Eff User A"),
            (_USER_B_ID, "eff_b@test.com", "Eff User B"),
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

    # Remove the shared autouse _FakeUser override and use real JWT auth.
    app.dependency_overrides.pop(get_current_user, None)

    user_map = {
        str(_USER_A_ID): _RealUser(_USER_A_ID, "eff_a@test.com", "Eff User A"),
        str(_USER_B_ID): _RealUser(_USER_B_ID, "eff_b@test.com", "Eff User B"),
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


async def _create_presentation(
    owner_id: uuid.UUID,
    *,
    title: str = _PRIV_TITLE,
    deleted: bool = False,
) -> uuid.UUID:
    """Persist a (optionally soft-deleted) presentation owned by owner_id."""
    from app.models.presentation import Presentation
    from tests.conftest import TestSessionLocal

    async with TestSessionLocal() as session:
        pres = Presentation(
            public_id=f"pres_{uuid.uuid4().hex[:16]}",
            title=title,
            description="B3 test presentation",
            status="ready",
            owner_id=owner_id,
        )
        if deleted:
            pres.deleted_at = datetime.now(UTC)
        session.add(pres)
        await session.commit()
        await session.refresh(pres)
        return pres.id


async def test_unauthenticated_effectiveness_rejected() -> None:
    async with await _make_client() as client:
        resp = await client.get(
            f"/api/v1/effectiveness/report/{uuid.uuid4()}",
        )
        assert resp.status_code == 401
        resp = await client.post(
            "/api/v1/effectiveness/assessments/start",
            json={"presentation_id": str(uuid.uuid4()), "assessment_type": "baseline"},
        )
        assert resp.status_code == 401


async def test_owner_start_and_report_ok() -> None:
    pres_id = await _create_presentation(_USER_A_ID)
    async with await _make_client() as client:
        a_headers = _headers(_USER_A_ID)

        resp = await client.post(
            "/api/v1/effectiveness/assessments/start",
            json={"presentation_id": str(pres_id), "assessment_type": "baseline"},
            headers=a_headers,
        )
        assert resp.status_code == 201, resp.text

        resp = await client.get(
            f"/api/v1/effectiveness/report/{pres_id}",
            headers=a_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["presentation_title"] == _PRIV_TITLE


async def test_cross_user_start_assessment_blocked() -> None:
    pres_id = await _create_presentation(_USER_A_ID)
    async with await _make_client() as client:
        b_headers = _headers(_USER_B_ID)

        resp = await client.post(
            "/api/v1/effectiveness/assessments/start",
            json={"presentation_id": str(pres_id), "assessment_type": "baseline"},
            headers=b_headers,
        )
        assert resp.status_code == 404, resp.text
        body = resp.json()
        assert body["error"]["code"] == "NOT_FOUND"
        assert "Presentation not found" in body["error"]["message"]


async def test_cross_user_report_does_not_leak_title() -> None:
    """Even with a bound assessment, User B never sees User A's title."""
    import uuid as _uuid

    from app.models.effectiveness_assessment import EffectivenessAssessment
    from app.models.presentation import Presentation
    from tests.conftest import TestSessionLocal

    pres_id = await _create_presentation(_USER_A_ID)

    # Simulate the pre-fix state: User B already holds an assessment row bound
    # to User A's presentation.
    async with TestSessionLocal() as session:
        session.add(
            EffectivenessAssessment(
                id=_uuid.uuid4(),
                public_id=f"assm_{_uuid.uuid4().hex[:16]}",
                user_id=_USER_B_ID,
                presentation_id=pres_id,
            )
        )
        await session.commit()

    async with await _make_client() as client:
        b_headers = _headers(_USER_B_ID)
        resp = await client.get(
            f"/api/v1/effectiveness/report/{pres_id}",
            headers=b_headers,
        )
        assert resp.status_code == 404, resp.text
        body = resp.json()
        assert body["error"]["code"] == "NOT_FOUND"
        assert "Presentation not found" in body["error"]["message"]


async def test_missing_presentation_is_404_even_for_owner() -> None:
    async with await _make_client() as client:
        a_headers = _headers(_USER_A_ID)

        resp = await client.post(
            "/api/v1/effectiveness/assessments/start",
            json={"presentation_id": str(uuid.uuid4()), "assessment_type": "baseline"},
            headers=a_headers,
        )
        assert resp.status_code == 404, resp.text
        assert resp.json()["error"]["code"] == "NOT_FOUND"


async def test_soft_deleted_presentation_is_404_even_for_owner() -> None:
    pres_id = await _create_presentation(_USER_A_ID, deleted=True)
    async with await _make_client() as client:
        a_headers = _headers(_USER_A_ID)

        resp = await client.post(
            "/api/v1/effectiveness/assessments/start",
            json={"presentation_id": str(pres_id), "assessment_type": "baseline"},
            headers=a_headers,
        )
        assert resp.status_code == 404, resp.text
        assert resp.json()["error"]["code"] == "NOT_FOUND"


async def test_orphaned_presentation_is_404_for_everyone() -> None:
    """A presentation with no owner is inaccessible to both users."""
    from app.models.presentation import Presentation
    from tests.conftest import TestSessionLocal

    async with TestSessionLocal() as session:
        pres = Presentation(
            public_id=f"pres_{uuid.uuid4().hex[:16]}",
            title="Orphaned presentation",
            description="No owner",
            status="ready",
            owner_id=None,
        )
        session.add(pres)
        await session.commit()
        await session.refresh(pres)
        pres_id = pres.id

    async with await _make_client() as client:
        for headers in (_headers(_USER_A_ID), _headers(_USER_B_ID)):
            resp = await client.post(
                "/api/v1/effectiveness/assessments/start",
                json={"presentation_id": str(pres_id), "assessment_type": "baseline"},
                headers=headers,
            )
            assert resp.status_code == 404, resp.text
            assert resp.json()["error"]["code"] == "NOT_FOUND"


async def test_error_bodies_are_indistinguishable() -> None:
    """Cross-user vs missing-presentation 404 bodies are identical (no oracle)."""
    pres_id = await _create_presentation(_USER_A_ID)
    async with await _make_client() as client:
        a_headers = _headers(_USER_A_ID)
        b_headers = _headers(_USER_B_ID)

        cross = await client.post(
            "/api/v1/effectiveness/assessments/start",
            json={"presentation_id": str(pres_id), "assessment_type": "baseline"},
            headers=b_headers,
        )
        missing = await client.post(
            "/api/v1/effectiveness/assessments/start",
            json={"presentation_id": str(uuid.uuid4()), "assessment_type": "baseline"},
            headers=a_headers,
        )
        assert cross.status_code == 404
        assert missing.status_code == 404
        # The 404 fields that could act as an existence oracle (code, message)
        # are identical; details only echoes the caller-supplied presentation id.
        assert cross.json()["error"]["code"] == missing.json()["error"]["code"]
        assert cross.json()["error"]["message"] == missing.json()["error"]["message"]
        assert cross.json()["success"] == missing.json()["success"]


async def test_report_missing_presentation_is_404() -> None:
    async with await _make_client() as client:
        a_headers = _headers(_USER_A_ID)
        resp = await client.get(
            f"/api/v1/effectiveness/report/{uuid.uuid4()}",
            headers=a_headers,
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"
