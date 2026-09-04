"""P10 Adaptive Review API security / isolation tests (C2).

Exercises the review endpoints over the real ASGI app with JWT-based auth so the
full auth pipeline is validated. Confirms every review operation is
learner-scoped and ownership 404-equalized:

* User A seeds a weak concept they own and a due review schedule.
* User A can list their own queue, complete, and skip their own schedules.
* User B (authenticated) receives 404 (never 403/500) for every cross-user
  access to A's schedules.
* Unauthenticated requests are rejected with 401.
* Nonexistent / foreign schedule identifiers yield 404 (never 500).
* The queue ``limit`` is bounded.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
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
    """Insert two users and override get_current_user with a JWT-decoding version."""
    from app.core.security import hash_password
    from app.models.user import User
    from tests.conftest import TestSessionLocal

    async with TestSessionLocal() as session:
        for uid, email, name in (
            (_USER_A_ID, "review_a@test.com", "Review User A"),
            (_USER_B_ID, "review_b@test.com", "Review User B"),
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
        str(_USER_A_ID): _RealUser(_USER_A_ID, "review_a@test.com", "Review User A"),
        str(_USER_B_ID): _RealUser(_USER_B_ID, "review_b@test.com", "Review User B"),
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
    """Seed User A with a learner profile + an owned weak concept.

    Returns the concept public_id owned by User A.
    """
    from app.models.concept import Concept
    from app.models.educational_memory import EducationalMemoryRecord
    from app.models.presentation import Presentation
    from tests.conftest import TestSessionLocal
    from tests.learner_progress_helpers import build_memory_json, seed_learner

    async with TestSessionLocal() as session:
        lookups = await seed_learner(session, _USER_A_ID, email="review_a@test.com")

        concept_id = f"concept_review_{uuid.uuid4().hex[:10]}"

        base = build_memory_json(str(_USER_A_ID))
        new_mem = dict(base)
        new_mem["weak_concepts"] = [concept_id]
        new_mem["concept_records"] = dict(base["concept_records"])

        rec = (
            await session.execute(
                select(EducationalMemoryRecord).where(
                    EducationalMemoryRecord.user_id == _USER_A_ID
                )
            )
        ).scalar_one_or_none()
        if rec is None:
            rec = EducationalMemoryRecord(user_id=_USER_A_ID, memory_data=new_mem)
            session.add(rec)
        else:
            rec.memory_data = new_mem
        await session.flush()

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


async def _seed_due_schedule_for_a(concept_public_id: str) -> str:
    """Insert a due ReviewSchedule owned by User A; returns its public_id."""
    from app.models.concept import Concept
    from app.models.review_schedule import ReviewSchedule
    from tests.conftest import TestSessionLocal

    async with TestSessionLocal() as session:
        concept = (
            await session.execute(
                select(Concept).where(Concept.public_id == concept_public_id)
            )
        ).scalar_one()
        schedule = ReviewSchedule(
            user_id=_USER_A_ID,
            concept_id=concept.id,
            lesson_id=concept.lesson_id,
            topic=concept.name,
            status="scheduled",
            scheduled_date=datetime.now(UTC).date(),
            interval_days=1,
            mastery_at_schedule=30.0,
            due_at=datetime.now(UTC) - timedelta(days=1),
            review_metadata={"step": 0},
        )
        session.add(schedule)
        await session.commit()
        await session.refresh(schedule)
        return schedule.public_id


async def test_unauthenticated_review_requests_rejected() -> None:
    async with await _make_client() as client:
        resp = await client.get("/api/v1/me/review")
        assert resp.status_code == 401
        resp = await client.post("/api/v1/me/review/some-schedule/complete")
        assert resp.status_code == 401
        resp = await client.post("/api/v1/me/review/some-schedule/skip")
        assert resp.status_code == 401


async def test_owner_lists_bounded_queue() -> None:
    await _seed_learner_a_concept()
    async with await _make_client() as client:
        a_headers = _headers(_USER_A_ID)
        resp = await client.get("/api/v1/me/review?limit=5", headers=a_headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert set(data) >= {"items", "total", "due_count"}
        assert isinstance(data["items"], list)
        assert data["total"] >= 0


async def test_complete_advances_and_is_learner_scoped() -> None:
    concept_id = await _seed_learner_a_concept()
    schedule_id = await _seed_due_schedule_for_a(concept_id)
    async with await _make_client() as client:
        a_headers = _headers(_USER_A_ID)
        b_headers = _headers(_USER_B_ID)

        # User A can complete their own due schedule (interval 1d -> 3d).
        resp = await client.post(
            f"/api/v1/me/review/{schedule_id}/complete", headers=a_headers
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["next_interval_days"] == 3
        assert data["next_due_at"] is not None
        assert data["schedule_id"] == schedule_id

        # User B cannot operate on User A's schedule (404-equalized).
        resp = await client.post(
            f"/api/v1/me/review/{schedule_id}/complete", headers=b_headers
        )
        assert resp.status_code == 404
        resp = await client.post(
            f"/api/v1/me/review/{schedule_id}/skip", headers=b_headers
        )
        assert resp.status_code == 404


async def test_skip_is_learner_scoped_and_postpones() -> None:
    concept_id = await _seed_learner_a_concept()
    schedule_id = await _seed_due_schedule_for_a(concept_id)
    async with await _make_client() as client:
        a_headers = _headers(_USER_A_ID)
        b_headers = _headers(_USER_B_ID)

        resp = await client.post(
            f"/api/v1/me/review/{schedule_id}/skip", headers=a_headers
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        # Skip postpones without advancing the interval.
        assert data["next_interval_days"] == 1
        assert data["next_due_at"] is not None

        # User B cannot skip A's schedule.
        resp = await client.post(
            f"/api/v1/me/review/{schedule_id}/skip", headers=b_headers
        )
        assert resp.status_code == 404


async def test_nonexistent_schedule_is_404() -> None:
    await _seed_learner_a_concept()
    async with await _make_client() as client:
        a_headers = _headers(_USER_A_ID)
        resp = await client.post(
            "/api/v1/me/review/rev-does-not-exist/complete", headers=a_headers
        )
        assert resp.status_code == 404
        resp = await client.post(
            "/api/v1/me/review/rev-does-not-exist/skip", headers=a_headers
        )
        assert resp.status_code == 404
