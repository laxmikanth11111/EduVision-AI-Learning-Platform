"""B7 Effectiveness comparison ownership-scoping tests.

The old ``GET /api/v1/effectiveness/comparison`` aggregated ``EffectivenessAssessment``
rows across *all* users by ``experiment_group`` label, exposing other learners'
aggregate performance (counts, completion, averages) to any authenticated user.
Under the individual-user foundation the comparison is scoped to the calling
user's own assessments; a foreign experiment group must be indistinguishable
from a group that contains nothing (no existence/ownership oracle).

* User A seeds their own assessment in experiment group ``secretgrp``.
* User B (authenticated) queries ``secretgrp`` and must receive the exact same
  empty-group response as for a group that never existed.
* User A still resolves their own group (the feature remains owner-usable).
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

_USER_A_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
_USER_B_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")


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
            (_USER_A_ID, "cmp_a@test.com", "Comp User A"),
            (_USER_B_ID, "cmp_b@test.com", "Comp User B"),
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
        str(_USER_A_ID): _RealUser(_USER_A_ID, "cmp_a@test.com", "Comp User A"),
        str(_USER_B_ID): _RealUser(_USER_B_ID, "cmp_b@test.com", "Comp User B"),
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


def _unique_group(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _metrics(data: dict) -> dict:
    """Comparison fields minus the echo of the group labels themselves."""
    return {k: v for k, v in data.items() if k not in ("group_a", "group_b")}


async def _seed_assessment(
    user_id: uuid.UUID,
    *,
    experiment_group: str,
    baseline: float,
    post: float,
) -> None:
    """Persist an effectiveness assessment bound to *user_id* with scores."""
    from app.models.effectiveness_assessment import EffectivenessAssessment
    from app.models.presentation import Presentation
    from tests.conftest import TestSessionLocal

    async with TestSessionLocal() as session:
        pres = Presentation(
            public_id=f"pres_{uuid.uuid4().hex[:16]}",
            title="B7 comparison security deck",
            description="B7 test presentation",
            status="ready",
            owner_id=user_id,
        )
        session.add(pres)
        await session.flush()
        assessment = EffectivenessAssessment(
            id=uuid.uuid4(),
            public_id=f"assm_{uuid.uuid4().hex[:16]}",
            user_id=user_id,
            presentation_id=pres.id,
            experiment_group=experiment_group,
            baseline_score=baseline,
            post_score=post,
            absolute_gain=post - baseline,
            normalized_gain=((post - baseline) / (100.0 - baseline)) if baseline < 100 else 0.0,
            status="completed",
            completed_at=datetime.now(UTC),
        )
        session.add(assessment)
        await session.commit()


async def test_unauthenticated_comparison_rejected() -> None:
    async with await _make_client() as client:
        resp = await client.get(
            "/api/v1/effectiveness/comparison",
            params={"group_a": "g1", "group_b": "g2"},
        )
        assert resp.status_code == 401


async def test_owner_sees_own_group_data() -> None:
    """User A's comparison resolves their own experiment group."""
    group = _unique_group("owngrp")
    await _seed_assessment(
        _USER_A_ID,
        experiment_group=group,
        baseline=50.0,
        post=90.0,
    )
    async with await _make_client() as client:
        resp = await client.get(
            "/api/v1/effectiveness/comparison",
            params={"group_a": group, "group_b": "other"},
            headers=_headers(_USER_A_ID),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["group_a_count"] == 1
        assert data["group_a_avg_absolute_gain"] == 40.0
        assert data["group_b_count"] == 0


async def test_cross_user_comparison_never_includes_victim_group() -> None:
    """User B's query for User A's experiment group must be empty (discriminator)."""
    group = _unique_group("secretgrp")
    await _seed_assessment(
        _USER_A_ID,
        experiment_group=group,
        baseline=50.0,
        post=90.0,
    )
    async with await _make_client() as client:
        b_headers = _headers(_USER_B_ID)
        resp = await client.get(
            "/api/v1/effectiveness/comparison",
            params={"group_a": group, "group_b": "other"},
            headers=b_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["group_a_count"] == 0
        assert data["group_a_avg_baseline"] is None
        assert data["group_a_avg_post"] is None
        assert data["group_a_avg_absolute_gain"] is None
        assert data["group_a_completed"] == 0


async def test_foreign_group_indistinguishable_from_nonexistent() -> None:
    """Victim group query equals nonexistent-group query — no existence oracle."""
    group = _unique_group("secretgrp")
    await _seed_assessment(
        _USER_A_ID,
        experiment_group=group,
        baseline=50.0,
        post=90.0,
    )
    async with await _make_client() as client:
        b_headers = _headers(_USER_B_ID)

        resp_foreign = await client.get(
            "/api/v1/effectiveness/comparison",
            params={"group_a": group, "group_b": "other"},
            headers=b_headers,
        )
        resp_none = await client.get(
            "/api/v1/effectiveness/comparison",
            params={"group_a": "never_existed", "group_b": "nothing_here"},
            headers=b_headers,
        )
        assert resp_foreign.status_code == 200
        assert resp_none.status_code == 200
        assert _metrics(resp_foreign.json()["data"]) == _metrics(
            resp_none.json()["data"]
        )


async def test_service_level_call_is_user_scoped() -> None:
    """Service-level comparison is also scoped to the calling user."""
    from app.database.unit_of_work import UnitOfWork
    from app.services.effectiveness_service import EffectivenessService
    from tests.conftest import TestSessionLocal

    group = _unique_group("secretgrp")
    await _seed_assessment(
        _USER_A_ID,
        experiment_group=group,
        baseline=50.0,
        post=90.0,
    )

    async with TestSessionLocal() as session:
        uow = UnitOfWork(session=session)
        service = EffectivenessService(uow.session)
        result_b = await service.compare_groups(
            user_id=_USER_B_ID,
            group_a=group,
            group_b="other",
        )
        assert result_b["group_a_count"] == 0

        result_a = await service.compare_groups(
            user_id=_USER_A_ID,
            group_a=group,
            group_b="other",
        )
        assert result_a["group_a_count"] == 1
