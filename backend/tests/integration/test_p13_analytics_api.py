"""P13 Learner Analytics API integration tests.

Exercises the real ASGI app with JWT-based auth over the SQLite test database
(exactly as ``test_p11_api_security.py`` does), validating the full pipeline
for ``GET /me/analytics/{overview,trend,concepts,effort}``:

  * unauthenticated requests are rejected with 401 on every P13 endpoint
  * the owner reads their own deterministic aggregates (attempts, accuracy,
    mastery bands, per-date trend, concept up/flat/down + deep-links, effort)
  * user B (authenticated) never sees any of A's rows — aggregations are
    learner-scoped at the query layer (B's analytics are genuinely empty)
  * empty-state payloads are well-formed (zeroes / empty lists, no null-crash)
  * the trend window is clamped server-side
  * ``p13_analytics_views_total`` appears on ``/api/v1/metrics`` after a read

Each behavioral test uses its own freshly-created learner (unique user id), so
the in-process ``educational_memory_service`` cache and the shared SQLite file
never leak rows between scenarios.
"""

from __future__ import annotations

import time
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

# Module-level user registry so behavioral tests can register freshly-seeded
# learners with the JWT override without threading a fixture through helpers
# (the fixture refreshes this map before every test).
_JWT_USERS: dict[str, _RealUser] = {}

_WEAK_NAME = "Gaussian Foundations"
_STRONG_NAME = "Vector Spaces"


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
            (_USER_A_ID, "p13_a@test.com", "P13 User A"),
            (_USER_B_ID, "p13_b@test.com", "P13 User B"),
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

    _JWT_USERS.clear()
    _JWT_USERS.update(
        {
            str(_USER_A_ID): _RealUser(_USER_A_ID, "p13_a@test.com", "P13 User A"),
            str(_USER_B_ID): _RealUser(_USER_B_ID, "p13_b@test.com", "P13 User B"),
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


def _headers(user_id: uuid.UUID) -> dict[str, str]:
    token = create_access_token(user_id, role="user")
    return {"Authorization": f"Bearer {token}"}


async def _make_client() -> AsyncClient:
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test", follow_redirects=True)


def _analytic_urls() -> list[tuple[str, str]]:
    return [
        ("GET", "/api/v1/me/analytics"),
        ("GET", "/api/v1/me/analytics/trend"),
        ("GET", "/api/v1/me/analytics/concepts"),
        ("GET", "/api/v1/me/analytics/effort"),
    ]


async def _create_bare_user(user_id: uuid.UUID, email: str, name: str) -> None:
    """Create a learner with zero history (no presentation/lesson/attempts)."""
    from app.core.security import hash_password
    from app.models.user import User
    from tests.conftest import TestSessionLocal

    async with TestSessionLocal() as session:
        existing = await session.execute(select(User).where(User.id == user_id))
        if existing.scalar_one_or_none() is None:
            session.add(
                User(
                    id=user_id,
                    email=email,
                    name=name,
                    password_hash=hash_password("password123"),
                )
            )
            await session.commit()
    _JWT_USERS[str(user_id)] = _RealUser(user_id, email, name)


async def _seed_analytics_learner(
    user_map: dict[str, _RealUser], user_id: uuid.UUID, email: str
) -> dict[str, Any]:
    """Seed a fresh learner with a deterministic three-attempt history.

    Two concepts (weak + mastered) are real ``Concept`` rows linked to a lesson
    owned by the learner, so practice deep-links resolve and effort is
    attributable. The learner is registered with the JWT auth override.
    """
    from app.core.security import hash_password
    from app.models.concept import Concept
    from app.models.educational_memory import EducationalMemoryRecord
    from app.models.generated_lesson import GeneratedLesson
    from app.models.learning_session import LearningSession
    from app.models.presentation import Presentation
    from app.models.quiz import Quiz
    from app.models.quiz_attempt import QuizAttempt
    from app.models.quiz_version import QuizVersion
    from app.models.score_summary import ScoreSummary
    from app.models.user import User
    from tests.conftest import TestSessionLocal

    async with TestSessionLocal() as session:
        existing = await session.execute(select(User).where(User.id == user_id))
        if existing.scalar_one_or_none() is None:
            session.add(
                User(
                    id=user_id,
                    email=email,
                    name="P13 Analytics Learner",
                    password_hash=hash_password("password123"),
                )
            )
            await session.flush()

        pres = Presentation(
            title="P13 Analytics Deck",
            owner_id=user_id,
            status="published",
            slide_count=2,
        )
        session.add(pres)
        await session.flush()

        lesson = GeneratedLesson(
            presentation_id=pres.id,
            user_id=user_id,
            mode="slide",
            status="ready",
            title="P13 Analytics Lesson",
            latest_version=1,
        )
        session.add(lesson)
        await session.flush()

        lsession = LearningSession(
            user_id=user_id,
            lesson_id=lesson.id,
            status="completed",
            completion_percentage=100.0,
            total_time_seconds=600,
            current_slide_position=0,
            current_block_position=0,
            resume_version=0,
            last_activity_at=None,
        )
        session.add(lsession)
        await session.flush()

        weak = Concept(
            name=_WEAK_NAME,
            topic="probability",
            presentation_id=pres.id,
            lesson_id=lesson.id,
        )
        strong = Concept(
            name=_STRONG_NAME,
            topic="linear-algebra",
            presentation_id=pres.id,
            lesson_id=lesson.id,
        )
        session.add_all([weak, strong])
        await session.flush()

        quiz = Quiz(
            presentation_id=pres.id,
            lesson_id=lesson.id,
            user_id=user_id,
            status="published",
            mode="practice",
            title="P13 Checkpoint",
            question_count=2,
            max_attempts_per_user=3,
            passing_score=50.0,
            show_feedback_after=True,
            latest_version=1,
            published_version=1,
        )
        session.add(quiz)
        await session.flush()

        version = QuizVersion(quiz_id=quiz.id, version=1, status="published", title="v1")
        session.add(version)
        await session.flush()

        now = datetime.now(UTC)
        percents = [40.0, 65.0, 90.0]
        correct_counts = [4, 8, 9]
        incorrect_counts = [6, 2, 1]
        for index, percent in enumerate(percents):
            attempt = QuizAttempt(
                quiz_id=quiz.id,
                quiz_version_id=version.id,
                user_id=user_id,
                attempt_number=index + 1,
                status="completed",
                score=percent / 100.0,
                max_score=1.0,
                percent_score=percent,
                time_spent_seconds=240 + index * 15,
                is_practice=False,
                started_at=None,
                completed_at=now - timedelta(days=2 - index),
            )
            session.add(attempt)
            await session.flush()
            session.add(
                ScoreSummary(
                    attempt_id=attempt.id,
                    total_points=10,
                    earned_points=percent / 10.0,
                    percent=percent,
                    correct_count=correct_counts[index],
                    incorrect_count=incorrect_counts[index],
                    partially_correct_count=0,
                    unanswered_count=0,
                )
            )

        memory = _build_memory_json(str(user_id), weak.public_id, strong.public_id)
        existing_mem = await session.execute(
            select(EducationalMemoryRecord).where(
                EducationalMemoryRecord.user_id == user_id
            )
        )
        if existing_mem.scalar_one_or_none() is None:
            session.add(EducationalMemoryRecord(user_id=user_id, memory_data=memory))

        await session.commit()

    user_map[str(user_id)] = _RealUser(user_id, email, "P13 Analytics Learner")
    return {
        "user_id": str(user_id),
        "lesson_id": lesson.public_id,
        "weak_concept_id": weak.public_id,
        "strong_concept_id": strong.public_id,
    }


def _build_memory_json(user_id: str, weak_id: str, strong_id: str) -> dict[str, Any]:
    now = time.time()
    return {
        "user_id": user_id,
        "profile": {
            "user_id": user_id,
            "learning_pace": "moderate",
            "total_study_minutes": 0.0,
            "average_mastery": 62.5,
            "streak_days": 1,
        },
        "completed_courses": [],
        "completed_lessons": [],
        "completed_topics": [],
        "mastered_concepts": [strong_id],
        "developing_concepts": [],
        "weak_concepts": [weak_id],
        "concept_records": {
            weak_id: {
                "concept_id": weak_id,
                "concept_name": _WEAK_NAME,
                "first_learned_at": now - 3600,
                "last_reviewed_at": now,
                "mastery_score": 35.0,
                "review_count": 2,
                "trend": "improving",
                "confidence_score": 0.4,
            },
            strong_id: {
                "concept_id": strong_id,
                "concept_name": _STRONG_NAME,
                "first_learned_at": now - 86400,
                "last_reviewed_at": now - 100,
                "mastery_score": 90.0,
                "review_count": 6,
                "trend": "stable",
                "confidence_score": 0.9,
            },
        },
        "preferences": {
            "preferred_visualization_type": None,
            "preferred_explanation_style": "concise",
            "preferred_difficulty": "Intermediate",
            "preferred_simulation_speed": 1.0,
        },
        "revision_queue": [],
        "milestones": [],
        "created_at": now - 86400,
        "updated_at": now,
    }


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------


async def test_unauthenticated_analytics_requests_rejected() -> None:
    async with await _make_client() as client:
        for method, url in _analytic_urls():
            resp = await client.request(method, url)
            assert resp.status_code == 401, f"{method} {url}"


async def test_analytics_are_learner_scoped_user_b_sees_empty() -> None:
    # Fresh ids + unique emails for both learners so this test never collides
    # with the module fixture's reserved p13_a/p13_b users (or with any other
    # test module reusing the same well-known ids/emails in the shared DB).
    uid_a = uuid.uuid4()
    lookups = await _seed_analytics_learner(_JWT_USERS, uid_a, f"p13_scope_a_{uuid.uuid4().hex[:8]}@test.com")

    uid_b = uuid.uuid4()
    await _create_bare_user(uid_b, f"p13_scope_b_{uuid.uuid4().hex[:8]}@test.com", "P13 User B")

    async with await _make_client() as client:
        a_resp = await client.get("/api/v1/me/analytics", headers=_headers(uid_a))
        assert a_resp.status_code == 200, a_resp.text
        assert a_resp.json()["data"]["attempts_taken"] == 3
        assert (
            a_resp.json()["data"]["current_focus"]["concept_public_id"]
            == lookups["weak_concept_id"]
        )

        b_resp = await client.get("/api/v1/me/analytics", headers=_headers(uid_b))
        assert b_resp.status_code == 200, b_resp.text
        b_data = b_resp.json()["data"]
        assert b_data["attempts_taken"] == 0
        assert b_data["avg_percent"] is None
        assert b_data["mastered_count"] == 0
        assert b_data["developing_count"] == 0
        assert b_data["weak_count"] == 0
        assert b_data["session_count"] == 0
        assert b_data["trend_percent"] is None
        assert b_data["current_focus"] is None

        for method, url in _analytic_urls():
            if url.endswith("/trend"):
                b_trend = await client.request(method, url, headers=_headers(uid_b))
                assert b_trend.status_code == 200
                assert b_trend.json()["data"]["points"] == []
                continue
            b_resp = await client.request(method, url, headers=_headers(uid_b))
            assert b_resp.status_code == 200, f"{method} {url}"
            payload = b_resp.json()["data"]
            key = "concepts" if "/concepts" in url else ("effort" if "/effort" in url else "")
            if key:
                assert payload[key] == []


async def test_empty_learner_gets_well_formed_empty_state() -> None:
    uid = uuid.uuid4()
    await _create_bare_user(uid, "p13_inactive@test.com", "P13 Inactive Learner")

    async with await _make_client() as client:
        overview = await client.get("/api/v1/me/analytics", headers=_headers(uid))
        assert overview.status_code == 200, overview.text
        data = overview.json()["data"]
        assert data["attempts_taken"] == 0
        assert data["avg_percent"] is None
        assert data["mastered_count"] == 0
        assert data["developing_count"] == 0
        assert data["weak_count"] == 0
        assert data["session_count"] == 0
        assert data["trend_percent"] is None
        assert data["current_focus"] is None

        trend = await client.get("/api/v1/me/analytics/trend", headers=_headers(uid))
        assert trend.status_code == 200
        assert trend.json()["data"]["points"] == []

        concepts = await client.get("/api/v1/me/analytics/concepts", headers=_headers(uid))
        assert concepts.status_code == 200, concepts.text
        assert concepts.json()["data"]["concepts"] == []
        assert concepts.json()["data"]["max"] == 100

        effort = await client.get("/api/v1/me/analytics/effort", headers=_headers(uid))
        assert effort.status_code == 200, effort.text
        assert effort.json()["data"]["effort"] == []
        assert effort.json()["data"]["max"] == 100


async def test_analytics_metrics_appear_after_read() -> None:
    uid = uuid.uuid4()
    await _seed_analytics_learner(_JWT_USERS, uid, "p13_metrics@test.com")
    async with await _make_client() as client:
        resp = await client.get("/api/v1/me/analytics", headers=_headers(uid))
        assert resp.status_code == 200, resp.text
        metrics_resp = await client.get("/api/v1/metrics")
        assert metrics_resp.status_code == 200, metrics_resp.text
        body = metrics_resp.text
        assert "p13_analytics_views_total" in body
        assert 'p13_analytics_views_total{endpoint="overview",outcome="ok"}' in body


# ---------------------------------------------------------------------------
# Behavior: owner aggregates
# ---------------------------------------------------------------------------


async def test_owner_overview_matches_seeded_history() -> None:
    uid = uuid.uuid4()
    lookups = await _seed_analytics_learner(_JWT_USERS, uid, "p13_ov@test.com")
    async with await _make_client() as client:
        resp = await client.get("/api/v1/me/analytics", headers=_headers(uid))
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]

        assert data["attempts_taken"] == 3
        assert data["avg_percent"] == 65.0
        assert data["mastered_count"] == 1
        assert data["developing_count"] == 0
        assert data["weak_count"] == 1
        assert data["session_count"] == 1
        # recent (65, 90) vs earlier (40) -> +37.5
        assert data["trend_percent"] == 37.5

        focus = data["current_focus"]
        assert focus["concept_public_id"] == lookups["weak_concept_id"]
        assert focus["name"] == _WEAK_NAME
        assert focus["band"] == "weak"
        assert focus["deep_link"] == f"/frontend/player.html?lesson={lookups['lesson_id']}"


async def test_owner_trend_bounded_and_chronological() -> None:
    uid = uuid.uuid4()
    await _seed_analytics_learner(_JWT_USERS, uid, "p13_trend@test.com")
    async with await _make_client() as client:
        resp = await client.get("/api/v1/me/analytics/trend", headers=_headers(uid))
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["window"] == 30, "default window clamps to the documented maximum"
        assert len(data["points"]) == 3
        dates = [p["date"] for p in data["points"]]
        assert dates == sorted(dates), "trend points must be oldest -> newest"
        percents = [p["percent"] for p in data["points"]]
        assert percents == [40.0, 65.0, 90.0]
        assert [p["attempts"] for p in data["points"]] == [1, 1, 1]
        assert all(p["correct"] + p["incorrect"] > 0 for p in data["points"])

        # An explicit smaller window keeps only the most recent dates.
        narrow = await client.get(
            "/api/v1/me/analytics/trend?window=2", headers=_headers(uid)
        )
        assert narrow.status_code == 200, narrow.text
        assert narrow.json()["data"]["window"] == 2
        assert [p["percent"] for p in narrow.json()["data"]["points"]] == [65.0, 90.0]

        # The OpenAPI contract rejects windows above 30 before reaching the service.
        too_wide = await client.get(
            "/api/v1/me/analytics/trend?window=31", headers=_headers(uid)
        )
        assert too_wide.status_code == 422, too_wide.text


async def test_owner_concepts_include_band_arrow_and_deep_links() -> None:
    uid = uuid.uuid4()
    lookups = await _seed_analytics_learner(_JWT_USERS, uid, "p13_concepts@test.com")
    async with await _make_client() as client:
        resp = await client.get("/api/v1/me/analytics/concepts", headers=_headers(uid))
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["max"] == 100
        assert len(data["concepts"]) == 2

        weak, strong = data["concepts"]
        assert weak["concept_public_id"] == lookups["weak_concept_id"]
        assert weak["name"] == _WEAK_NAME
        assert weak["band"] == "weak"
        assert weak["trend"] == "up"
        assert weak["current_mastery"] == 35.0
        assert weak["delta_mastery"] == 37.5
        assert weak["review_count"] == 2
        assert weak["deep_link_practice"] == (
            f"/frontend/player.html?lesson={lookups['lesson_id']}"
        )
        assert weak["deep_link_tutor"] == (
            f"/frontend/tutor.html?concept={lookups['weak_concept_id']}"
        )

        assert strong["concept_public_id"] == lookups["strong_concept_id"]
        assert strong["band"] == "mastered"
        assert strong["trend"] == "flat"
        assert strong["current_mastery"] == 90.0


async def test_owner_effort_maps_attempts_sessions_and_time() -> None:
    uid = uuid.uuid4()
    lookups = await _seed_analytics_learner(_JWT_USERS, uid, "p13_effort@test.com")
    async with await _make_client() as client:
        resp = await client.get("/api/v1/me/analytics/effort", headers=_headers(uid))
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["max"] == 100
        assert len(data["effort"]) == 2

        weak = data["effort"][0]
        assert weak["concept_public_id"] == lookups["weak_concept_id"]
        assert weak["attempts"] == 3
        assert weak["sessions"] == 1
        assert weak["time_seconds"] == 240 + 255 + 270
        assert weak["mastery_delta"] == 37.5
        assert weak["efficiency"] == 12.5
