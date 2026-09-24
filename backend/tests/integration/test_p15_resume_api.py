"""P15 resume API integration/security tests.

Exercises the real ASGI app with JWT-based auth over the SQLite test database
(exactly as ``test_p14_retention_api.py``), validating the P15 resume spine:

  * ``POST /lessons/{lesson}/player/start`` creates a persistent session
  * ``POST /lessons/{lesson}/player/position`` persists the learner's exact
    slide position (slide-accurate resume) and the response carries
    ``slide_index``/``topic_index``/``completion_percentage``
  * ``GET /lessons/{lesson}/player`` reads the saved position back
  * ``GET /me/progress`` lesson rows advertise ``resume_slide`` + ``resume_link``
  * unauthenticated 401 + cross-user 404 (no leaks, no writes)

Each behavioral test seeds a fresh learner + lesson + succeeded version (so the
player resolves real topics), matching the P13/P14 convention that keeps the
shared SQLite file from leaking rows between scenarios.
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

_JWT_USERS: dict[str, Any] = {}


class _RealUser:
    """Lightweight user stand-in built from a decoded JWT."""

    def __init__(self, user_id: uuid.UUID, email: str, name: str) -> None:
        self.id = user_id
        self.email = email
        self.name = name


@pytest_asyncio.fixture(autouse=True)
async def _jwt_users(setup_database: None) -> None:
    from app.core.security import hash_password
    from app.models.user import User
    from tests.conftest import TestSessionLocal

    async with TestSessionLocal() as session:
        for uid, email, name in (
            (uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"), "p15_a@test.com", "P15 User A"),
            (uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"), "p15_b@test.com", "P15 User B"),
        ):
            existing = await session.execute(select_user(uid))
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
    _JWT_USERS.clear()
    _JWT_USERS.update(
        {
            "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa": _RealUser(
                uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
                "p15_a@test.com",
                "P15 User A",
            ),
            "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb": _RealUser(
                uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
                "p15_b@test.com",
                "P15 User B",
            ),
        }
    )

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
        user = _JWT_USERS.get(payload.get("sub"))
        if not user:
            raise HTTPException(
                status_code=http_status.HTTP_401_UNAUTHORIZED,
                detail="User not found.",
            )
        return user

    app.dependency_overrides[get_current_user] = _jwt_get_current_user
    yield
    app.dependency_overrides.pop(get_current_user, None)


def select_user(uid: uuid.UUID) -> Any:
    from sqlalchemy import select

    from app.models.user import User

    return select(User).where(User.id == uid)


def _headers(user_id: uuid.UUID) -> dict[str, str]:
    token = create_access_token(user_id, role="user")
    return {"Authorization": f"Bearer {token}"}


async def _make_client() -> AsyncClient:
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test", follow_redirects=True)


async def _seed_resume_learner() -> dict[str, str]:
    """Seed a user-owned lesson + succeeded version with 2 topics (4 slides)."""
    from app.core.security import hash_password
    from app.models.generated_block import GeneratedBlock
    from app.models.generated_lesson import GeneratedLesson
    from app.models.generated_lesson_version import GeneratedLessonVersion
    from app.models.presentation import Presentation
    from app.models.user import User
    from tests.conftest import TestSessionLocal

    user_id = uuid.uuid4()

    async with TestSessionLocal() as session:
        session.add(
            User(
                id=user_id,
                email=f"p15_{uuid.uuid4().hex[:8]}@test.com",
                name="P15 Resume Learner",
                password_hash=hash_password("password123"),
            )
        )
        await session.flush()

        pres = Presentation(
            title="P15 Resume Deck",
            owner_id=user_id,
            status="published",
            slide_count=1,
        )
        session.add(pres)
        await session.flush()

        lesson = GeneratedLesson(
            presentation_id=pres.id,
            user_id=user_id,
            mode="slide",
            status="ready",
            title="P15 Resume Lesson",
            latest_version=1,
        )
        session.add(lesson)
        await session.flush()

        lv = GeneratedLessonVersion(
            lesson_id=lesson.id,
            version=1,
            status="succeeded",
            title=lesson.title,
            language="en",
            difficulty="beginner",
        )
        session.add(lv)
        await session.flush()
        for pos, heading in enumerate(["Resume: First Topic", "Resume: Second Topic"]):
            session.add(
                GeneratedBlock(
                    lesson_version_id=lv.id,
                    block_type="paragraph",
                    position=pos,
                    heading=heading,
                    content=f"Body for {heading}.",
                )
            )
        await session.commit()
        await session.refresh(lesson)

    _JWT_USERS[str(user_id)] = _RealUser(user_id, "p15_auto@test.com", "P15 Auto Learner")
    return {
        "user_id": str(user_id),
        "lesson_id": lesson.public_id,
    }


async def _start_session(client: AsyncClient, lookups: dict[str, str]) -> str:
    """POST /player/start and return the created session_id."""
    resp = await client.post(
        f"/api/v1/lessons/{lookups['lesson_id']}/player/start",
        json={},
        headers=_headers(uuid.UUID(lookups["user_id"])),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["session"]["session_id"]


async def _position(
    client: AsyncClient, lookups: dict[str, str], session_id: str, slide_index: int,
    mode: str = "learning",
) -> Any:
    return await client.post(
        f"/api/v1/lessons/{lookups['lesson_id']}/player/position",
        json={"session_id": session_id, "slide_index": slide_index, "mode": mode},
        headers=_headers(uuid.UUID(lookups["user_id"])),
    )


async def _seed_surplus_source_units(lookups: dict[str, str], count: int = 6) -> None:
    """Attach extra source units so source count outnumbers ``2 * topics``.

    This is the drift scenario behind F1: a lesson whose uploaded source deck is
    larger than the learning deck. Learning-mode completion must be indexed
    against ``topics * 2`` slides, never the source-unit count.
    """
    from app.models.content_unit import ContentUnit
    from app.models.generated_lesson import GeneratedLesson
    from tests.conftest import TestSessionLocal

    async with TestSessionLocal() as session:
        lesson = (
            await session.execute(
                select(GeneratedLesson).where(GeneratedLesson.public_id == lookups["lesson_id"])
            )
        ).scalar_one()
        for position in range(1, count + 1):
            session.add(
                ContentUnit(
                    presentation_id=lesson.presentation_id,
                    unit_type="slide",
                    position=position,
                    title=f"Surplus Unit {position}",
                    raw_text=f"Raw text for surplus unit {position}.",
                )
            )
        await session.commit()


async def _seed_source_material(lookups: dict[str, str]) -> None:
    """Attach 4 source units + a 4-topic outline to the seeded lesson's deck.

    The lesson is padded to 4 lesson blocks so ``_topic_count_for_lesson``
    reports 4 topics (matching the 4 source slides the deck maps onto).
    Unit ``position`` is 1-based, matching the outline's 1-based
    ``slide_ranges`` so the source topic map resolves through outline ranges.
    """
    from app.models.content_unit import ContentUnit
    from app.models.generated_block import GeneratedBlock
    from app.models.generated_lesson import GeneratedLesson
    from app.models.generated_lesson_version import GeneratedLessonVersion
    from app.models.topic_outline import TopicOutline
    from tests.conftest import TestSessionLocal

    async with TestSessionLocal() as session:
        lesson = (
            await session.execute(
                select(GeneratedLesson).where(GeneratedLesson.public_id == lookups["lesson_id"])
            )
        ).scalar_one()
        for pos in range(1, 5):
            session.add(
                ContentUnit(
                    presentation_id=lesson.presentation_id,
                    unit_type="slide",
                    position=pos,
                    title=f"Source Unit {pos}",
                    raw_text=f"Raw text for source unit {pos}.",
                )
            )
        lesson_version = (
            await session.execute(
                select(GeneratedLessonVersion)
                .where(GeneratedLessonVersion.lesson_id == lesson.id)
                .order_by(GeneratedLessonVersion.version.desc())
            )
        ).scalars().first()
        for pos in (2, 3):
            session.add(
                GeneratedBlock(
                    lesson_version_id=lesson_version.id,
                    block_type="paragraph",
                    position=pos,
                    heading=f"Resume: Source Topic {pos + 1}",
                    content=f"Body for source topic {pos + 1}.",
                )
            )
        session.add(
            TopicOutline(
                presentation_id=lesson.presentation_id,
                title="P15 Resume Deck",
                topics=[
                    {"title": f"Topic {pos}", "slide_ranges": [pos, pos]}
                    for pos in range(1, 5)
                ],
                status="succeeded",
            )
        )
        await session.commit()


# ---------------------------------------------------------------------------
# Auth / validation guards
# ---------------------------------------------------------------------------


async def test_unauthenticated_resume_requests_rejected() -> None:
    async with await _make_client() as client:
        resp = await client.post(
            "/api/v1/lessons/x/player/position",
            json={"session_id": "lsess_x", "slide_index": 2},
        )
        assert resp.status_code == 401
        resp = await client.get("/api/v1/lessons/x/player")
        assert resp.status_code == 401


async def test_invalid_position_body_is_422() -> None:
    lookups = await _seed_resume_learner()
    async with await _make_client() as client:
        headers = _headers(uuid.UUID(lookups["user_id"]))
        # Negative slide index violates the schema bound.
        resp = await client.post(
            f"/api/v1/lessons/{lookups['lesson_id']}/player/position",
            json={"session_id": "lsess_x", "slide_index": -1},
            headers=headers,
        )
        assert resp.status_code == 422
        # Missing session_id.
        resp = await client.post(
            f"/api/v1/lessons/{lookups['lesson_id']}/player/position",
            json={"slide_index": 2},
            headers=headers,
        )
        assert resp.status_code == 422


async def test_position_for_unknown_session_is_404() -> None:
    lookups = await _seed_resume_learner()
    async with await _make_client() as client:
        resp = await _position(client, lookups, "lsess_does_not_exist", 2)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Slide-accurate resume pipeline
# ---------------------------------------------------------------------------


async def test_position_saves_slide_and_state_reads_back() -> None:
    lookups = await _seed_resume_learner()
    async with await _make_client() as client:
        session_id = await _start_session(client, lookups)

        # Slide 2 == first topic's visual slide (topic 0), of 4 total slides.
        resp = await _position(client, lookups, session_id, 2)
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["session_id"] == session_id
        assert data["slide_index"] == 2
        assert data["topic_index"] == 1
        assert data["completion_percentage"] == 100.0

        # GET /player returns the persisted position for a cold reload path.
        state_resp = await client.get(
            f"/api/v1/lessons/{lookups['lesson_id']}/player",
            headers=_headers(uuid.UUID(lookups["user_id"])),
        )
        assert state_resp.status_code == 200
        session = state_resp.json()["data"]["session"]
        assert session["slide_index"] == 2
        assert session["topic_index"] == 1

        # Out-of-range slide is clamped server-side (never crashes, stays valid).
        clamped = await _position(client, lookups, session_id, 999)
        assert clamped.status_code == 200
        assert clamped.json()["data"]["slide_index"] == 3  # last slide of 4


async def test_progress_endpoint_advertises_resume() -> None:
    lookups = await _seed_resume_learner()
    async with await _make_client() as client:
        session_id = await _start_session(client, lookups)
        await _position(client, lookups, session_id, 3)

        resp = await client.get(
            "/api/v1/me/progress",
            headers=_headers(uuid.UUID(lookups["user_id"])),
        )
        assert resp.status_code == 200, resp.text
        items = resp.json()["data"]["lesson_progress"]
        assert items, "seeded lesson with a started session must appear"
        item = items[0]
        assert item["lesson_id"] == lookups["lesson_id"]
        assert item["resume_slide"] == 3
        assert item["resume_link"] == (
            f"/frontend/player.html?lesson={lookups['lesson_id']}&slide=3&mode=learning"
        )
        assert item["status"] == "completed"


async def test_cross_user_position_is_404_with_no_write() -> None:
    lookups = await _seed_resume_learner()
    uid_a = uuid.UUID(lookups["user_id"])
    uid_b = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
    async with await _make_client() as client:
        session_id = await _start_session(client, lookups)

        # User B attempts to move A's session.
        resp = await client.post(
            f"/api/v1/lessons/{lookups['lesson_id']}/player/position",
            json={"session_id": session_id, "slide_index": 2},
            headers=_headers(uid_b),
        )
        assert resp.status_code == 404

        # A's position is untouched (still slide 0 from start).
        state_resp = await client.get(
            f"/api/v1/lessons/{lookups['lesson_id']}/player",
            headers=_headers(uid_a),
        )
        assert state_resp.status_code == 200
        session = state_resp.json()["data"]["session"]
        assert session["slide_index"] == 0

        # B's own GET /player is indistinguishable from a missing lesson: the
        # lesson belongs to A, so B can neither read nor even see that a lesson
        # or session exists (no info leak).
        b_view = await client.get(
            f"/api/v1/lessons/{lookups['lesson_id']}/player",
            headers=_headers(uid_b),
        )
        assert b_view.status_code == 404


async def test_source_mode_final_slide_reaches_full_completion() -> None:
    lookups = await _seed_resume_learner()
    await _seed_source_material(lookups)
    async with await _make_client() as client:
        session_id = await _start_session(client, lookups)

        # A mid-deck source slide must not report the deck finished.
        resp = await _position(client, lookups, session_id, 1, mode="source")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["slide_index"] == 1
        assert data["completion_percentage"] < 100.0

        # The FINAL source slide is pinned to the last topic on the mapping, so
        # completion reaches 100% (previously capped at the ~50% ceiling).
        resp = await _position(client, lookups, session_id, 3, mode="source")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["slide_index"] == 3
        assert data["topic_index"] == 3
        assert data["completion_percentage"] == 100.0

        # The session carries the mode its position belongs to.
        state_resp = await client.get(
            f"/api/v1/lessons/{lookups['lesson_id']}/player",
            headers=_headers(uuid.UUID(lookups["user_id"])),
        )
        assert state_resp.status_code == 200
        session = state_resp.json()["data"]["session"]
        assert session["player_mode"] == "source"
        assert session["slide_index"] == 3
        assert session["completion_percentage"] == 100.0


async def test_learning_mode_completion_ignores_surplus_source_units() -> None:
    """F1: learning-mode completion is indexed against the topic deck only.

    A 2-topic lesson (4 learning slides) with 6 source units (6 > 2 * 2) must
    reach 100% on its final learning slide, and the readback must never
    re-inflate the deck from the surplus source count. Previously the start /
    get-state readback folded ``len(source_units)`` into the learning
    denominator (``max(6, 4) = 6``), re-surfacing phantom slides on resume.
    """
    from app.models.generated_lesson import GeneratedLesson
    from app.models.learning_session import LearningSession
    from tests.conftest import TestSessionLocal

    lookups = await _seed_resume_learner()
    await _seed_surplus_source_units(lookups, count=6)
    async with await _make_client() as client:
        session_id = await _start_session(client, lookups)

        # Slide 1 is the first topic's visual slide (topic 0 of 2) -> 50%.
        resp = await _position(client, lookups, session_id, slide_index=1)
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["slide_index"] == 1
        assert data["topic_index"] == 0
        assert data["completion_percentage"] == 50.0

        # The final learning slide (3) reaches 100% regardless of source count.
        resp = await _position(client, lookups, session_id, slide_index=3)
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["slide_index"] == 3
        assert data["topic_index"] == 1
        assert data["completion_percentage"] == 100.0
        assert data["player_mode"] == "learning"

        # Simulate a stale position persisted under the OLD inflated
        # denominator (learning interpreted as max(6, 4) = 6 slides, so slide 5
        # was "valid"). Reading it back must clamp back into the real deck
        # (4 slides -> index 3), never re-surface the phantom slide 5.
        async with TestSessionLocal() as session:
            row = (
                await session.execute(
                    select(LearningSession).where(LearningSession.public_id == session_id)
                )
            ).scalar_one()
            row.current_slide_position = 5
            row.current_block_position = 2
            row.completion_percentage = round((3 / 5) * 100.0, 1)
            row.player_mode = "learning"
            await session.commit()

        state_resp = await client.get(
            f"/api/v1/lessons/{lookups['lesson_id']}/player",
            headers=_headers(uuid.UUID(lookups["user_id"])),
        )
        assert state_resp.status_code == 200, state_resp.text
        session = state_resp.json()["data"]["session"]
        assert session["slide_index"] == 3, (
            f"readback must clamp the stale inflated-denominator slide into the "
            f"real deck, got {session['slide_index']}"
        )
        assert session["completion_percentage"] == 60.0  # stored value, untouched

        # The /start resume path is subject to the same clamp.
        start_resp = await client.post(
            f"/api/v1/lessons/{lookups['lesson_id']}/player/start",
            json={},
            headers=_headers(uuid.UUID(lookups["user_id"])),
        )
        assert start_resp.status_code == 200, start_resp.text
        assert start_resp.json()["data"]["session"]["slide_index"] == 3

        # And out-of-range requests clamp to the real final learning slide, not
        # a phantom slide derived from the surplus source count.
        clamped = await _position(client, lookups, session_id, 999)
        assert clamped.status_code == 200
        assert clamped.json()["data"]["slide_index"] == 3
        assert clamped.json()["data"]["completion_percentage"] == 100.0

        # The cold reload (get_state) then reflects the repaired position.
        state_resp = await client.get(
            f"/api/v1/lessons/{lookups['lesson_id']}/player",
            headers=_headers(uuid.UUID(lookups["user_id"])),
        )
        assert state_resp.status_code == 200
        session = state_resp.json()["data"]["session"]
        assert session["player_mode"] == "learning"
        assert session["slide_index"] == 3
        assert session["completion_percentage"] == 100.0


async def test_position_mode_switches_session_representation() -> None:
    lookups = await _seed_resume_learner()
    await _seed_source_material(lookups)
    async with await _make_client() as client:
        session_id = await _start_session(client, lookups)

        # Learning-mode position first (concept+visual pairs over 4 slides).
        resp = await _position(client, lookups, session_id, 2, mode="learning")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["slide_index"] == 2
        assert data["topic_index"] == 1
        assert data["player_mode"] == "learning"

        # Switching to source-mode position rewrites the representation.
        resp = await _position(client, lookups, session_id, 1, mode="source")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["slide_index"] == 1
        assert data["player_mode"] == "source"

        # Source slide 1 maps onto topic 1 of the 4-source-slide mapping.
        assert data["topic_index"] == 1
        assert data["completion_percentage"] < 100.0
