"""P8 Mastery Tutor API security / isolation tests (C2).

Exercises the tutor endpoints over the real ASGI app with JWT-based auth so the
full auth pipeline is validated. Confirms every tutor operation is learner-scoped:

* User A seeds a learner profile + a Gaussian concept they own.
* User A can create sessions, send messages, list messages, and remediate.
* User B (authenticated) receives 404 (never 403/500, no resource-existence
  leak) for every cross-user access to A's sessions/conversations/concepts.
* Unauthenticated requests are rejected with 401.
* Malformed / nonexistent identifiers yield 404 (404-equalized), not 500.
"""

from __future__ import annotations

import uuid
from datetime import UTC
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

_USER_A_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_USER_B_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


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
            (_USER_A_ID, "tutor_a@test.com", "Tutor User A"),
            (_USER_B_ID, "tutor_b@test.com", "Tutor User B"),
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
        str(_USER_A_ID): _RealUser(_USER_A_ID, "tutor_a@test.com", "Tutor User A"),
        str(_USER_B_ID): _RealUser(_USER_B_ID, "tutor_b@test.com", "Tutor User B"),
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


async def _seed_learner_a_concept() -> str:
    """Seed User A with a learner profile + an owned Gaussian concept.

    Returns the concept public_id owned by User A.
    """
    from app.models.concept import Concept
    from app.models.educational_memory import EducationalMemoryRecord
    from app.models.presentation import Presentation
    from tests.conftest import TestSessionLocal
    from tests.learner_progress_helpers import seed_learner

    async with TestSessionLocal() as session:
        lookups = await seed_learner(session, _USER_A_ID, email="tutor_a@test.com")

        from tests.learner_progress_helpers import build_memory_json

        concept_id = f"concept_{uuid.uuid4().hex[:12]}"

        # Always rebuild the memory from a fresh baseline so repeated test
        # invocations never reference a stale concept id across the shared DB.
        base = build_memory_json(str(_USER_A_ID))
        records = {str(k): dict(v) for k, v in base["concept_records"].items()}
        records[concept_id] = records.pop("concept_gauss")
        new_mem = dict(base)
        new_mem["weak_concepts"] = [concept_id]
        new_mem["concept_records"] = records

        rec = (
            await session.execute(
                select(EducationalMemoryRecord).where(
                    EducationalMemoryRecord.user_id == _USER_A_ID
                )
            )
        ).scalar_one_or_none()
        if rec is None:
            rec = EducationalMemoryRecord(
                user_id=_USER_A_ID, memory_data=new_mem
            )
            session.add(rec)
        else:
            rec.memory_data = new_mem
        await session.flush()

        # Anchor the concept to the presentation created by THIS seed call.
        pres = (
            await session.execute(
                select(Presentation).where(
                    Presentation.public_id == lookups["presentation_id"]
                )
            )
        ).scalar_one()

        existing = await session.execute(
            select(Concept).where(Concept.public_id == concept_id)
        )
        if existing.scalar_one_or_none() is None:
            session.add(
                Concept(
                    public_id=concept_id,
                    name="Gaussian Distributions",
                    description="Normal distribution functions.",
                    presentation_id=pres.id,
                    lesson_id=None,
                )
            )
        await session.commit()
        return concept_id


async def _create_session(client: AsyncClient, headers: dict[str, str], **body: Any):
    payload = {"title": "Tutor Isolation Chat", **body}
    resp = await client.post("/api/v1/tutor/sessions", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def test_unauthenticated_tutor_requests_rejected() -> None:
    async with await _make_client() as client:
        resp = await client.get("/api/v1/tutor/sessions")
        assert resp.status_code == 401
        resp = await client.post("/api/v1/tutor/sessions", json={"title": "No Auth"})
        assert resp.status_code == 401


async def test_cross_user_session_isolation() -> None:
    await _seed_learner_a_concept()
    async with await _make_client() as client:
        a_headers = _headers(_USER_A_ID)
        b_headers = _headers(_USER_B_ID)

        session_obj = await _create_session(client, a_headers)
        session_id = session_obj["id"]

        # User A can read their own session.
        resp = await client.get(
            f"/api/v1/tutor/sessions/{session_id}", headers=a_headers
        )
        assert resp.status_code == 200

        # User B cannot read User A's session (404-equalized).
        resp = await client.get(
            f"/api/v1/tutor/sessions/{session_id}", headers=b_headers
        )
        assert resp.status_code == 404

        # User B cannot send a message into User A's session.
        resp = await client.post(
            f"/api/v1/tutor/sessions/{session_id}/messages",
            json={"content": "intruder"},
            headers=b_headers,
        )
        assert resp.status_code == 404


async def test_list_sessions_is_learner_scoped() -> None:
    await _seed_learner_a_concept()
    async with await _make_client() as client:
        a_headers = _headers(_USER_A_ID)
        b_headers = _headers(_USER_B_ID)

        s1 = await _create_session(client, a_headers, title="A-only chat")
        s2 = await _create_session(client, a_headers, title="A-second chat")

        resp = await client.get("/api/v1/tutor/sessions", headers=a_headers)
        assert resp.status_code == 200
        a_ids = {item["id"] for item in resp.json()["data"]}
        assert s1["id"] in a_ids
        assert s2["id"] in a_ids

        resp = await client.get("/api/v1/tutor/sessions", headers=b_headers)
        assert resp.status_code == 200
        assert resp.json()["data"] == []


async def test_cross_user_message_listing_isolation() -> None:
    concept_id = await _seed_learner_a_concept()
    async with await _make_client() as client:
        a_headers = _headers(_USER_A_ID)
        b_headers = _headers(_USER_B_ID)

        session_obj = await _create_session(client, a_headers)
        send = await client.post(
            f"/api/v1/tutor/sessions/{session_obj['id']}/messages",
            json={"content": f"explain {concept_id}"},
            headers=a_headers,
        )
        assert send.status_code == 201, send.text
        conversation_id = send.json()["data"]["conversation_id"]

        # User A can list their own conversation messages.
        resp = await client.get(
            f"/api/v1/tutor/conversations/{conversation_id}/messages",
            headers=a_headers,
        )
        assert resp.status_code == 200
        roles = {msg["role"] for msg in resp.json()["data"]}
        assert roles == {"user", "assistant"}

        # User B cannot list User A's conversation messages.
        resp = await client.get(
            f"/api/v1/tutor/conversations/{conversation_id}/messages",
            headers=b_headers,
        )
        assert resp.status_code == 404


async def test_cross_user_remediation_isolation() -> None:
    concept_id = await _seed_learner_a_concept()
    async with await _make_client() as client:
        a_headers = _headers(_USER_A_ID)
        b_headers = _headers(_USER_B_ID)

        # User A can remediate their own concept.
        resp = await client.post(
            "/api/v1/tutor/remediate",
            json={"target_concept_id": concept_id},
            headers=a_headers,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["data"]["target_concept_name"] == "Gaussian Distributions"

        # User B cannot remediate User A's concept.
        resp = await client.post(
            "/api/v1/tutor/remediate",
            json={"target_concept_id": concept_id},
            headers=b_headers,
        )
        assert resp.status_code == 404


async def test_nonexistent_and_malformed_ids_are_404() -> None:
    await _seed_learner_a_concept()
    async with await _make_client() as client:
        a_headers = _headers(_USER_A_ID)

        resp = await client.get(
            "/api/v1/tutor/sessions/nope-404", headers=a_headers
        )
        assert resp.status_code == 404

        resp = await client.post(
            "/api/v1/tutor/sessions/nope-404/messages",
            json={"content": "hi"},
            headers=a_headers,
        )
        assert resp.status_code == 404

        resp = await client.get(
            "/api/v1/tutor/conversations/nope-404/messages", headers=a_headers
        )
        assert resp.status_code == 404

        resp = await client.post(
            "/api/v1/tutor/remediate",
            json={"target_concept_id": "concept_does_not_exist"},
            headers=a_headers,
        )
        assert resp.status_code == 404


async def test_remediate_deleted_presentation_is_404() -> None:
    concept_id = await _seed_learner_a_concept()
    async with await _make_client() as client:
        a_headers = _headers(_USER_A_ID)

        # Soft-delete the presentation that owns the concept so ownership
        # resolution fails (404).
        from datetime import datetime, timezone

        from app.models.concept import Concept
        from app.models.presentation import Presentation
        from tests.conftest import TestSessionLocal

        async with TestSessionLocal() as session:
            concept = (
                await session.execute(
                    select(Concept).where(Concept.public_id == concept_id)
                )
            ).scalar_one()
            pres = (
                await session.execute(
                    select(Presentation).where(Presentation.id == concept.presentation_id)
                )
            ).scalar_one()
            pres.deleted_at = datetime.now(UTC)
            await session.commit()

        resp = await client.post(
            "/api/v1/tutor/remediate",
            json={"target_concept_id": concept_id},
            headers=a_headers,
        )
        assert resp.status_code == 404
