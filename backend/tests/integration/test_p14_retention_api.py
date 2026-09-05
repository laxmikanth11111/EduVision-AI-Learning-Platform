"""P14 Retention & outcome-driven review API integration/security tests.

Exercises the real ASGI app with JWT-based auth over the SQLite test database
(exactly as ``test_p13_analytics_api.py`` / ``test_review_api_security.py``),
validating the full P14 pipeline:

  * outcome-driven ``POST /me/review/{schedule}/complete`` (optional body):
    again/hard/good/easy spacing, 422 on invalid outcomes, no-body == legacy
  * the mastery invariant — review NEVER rewrites the quiz-owned mastery scalar
  * outcome history/counts persisted in ``review_metadata`` (versioned, capped)
  * queue items advertise additive ``retention_status`` + ``review_accuracy``
  * ``GET /me/analytics/retention`` aggregation, ordering, and learner scope
  * unauthenticated 401 + cross-user 404 / B sees nothing (no leaks, no writes)
  * ``p14_*`` counters appear on ``/api/v1/metrics``

Each behavioral test seeds a freshly-created learner (unique user id), matching
the P13 convention that keeps the in-process ``educational_memory_service``
cache and the shared SQLite file from leaking rows between scenarios.
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
from app.services import retention

pytestmark = pytest.mark.asyncio

_WEAK_NAME = "Retention Weak"
_STRONG_NAME = "Retention Strong"
_LADDER = (1, 3, 7, 14)

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
            (uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"), "p14_a@test.com", "P14 User A"),
            (uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"), "p14_b@test.com", "P14 User B"),
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
            "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa": _RealUser(
                uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
                "p14_a@test.com",
                "P14 User A",
            ),
            "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb": _RealUser(
                uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
                "p14_b@test.com",
                "P14 User B",
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


def _headers(user_id: uuid.UUID) -> dict[str, str]:
    token = create_access_token(user_id, role="user")
    return {"Authorization": f"Bearer {token}"}


async def _make_client() -> AsyncClient:
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test", follow_redirects=True)


async def _create_user(user_id: uuid.UUID, email: str, name: str) -> None:
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


async def _seed_review_learner(
    *,
    weak_mastery: float = 55.0,
    strong_mastery: float = 90.0,
    seed_schedule_weak: bool = True,
    step_weak: int = 1,
    due_offset_days: float = -1.0,
) -> dict[str, Any]:
    """Seed a learner with a weak + strong concept and real memory + schedules.

    Owns a presentation/lesson chain so practice deep-links resolve. Returns
    public ids the test can use for API calls.
    """
    from app.core.security import hash_password
    from app.models.concept import Concept
    from app.models.educational_memory import EducationalMemoryRecord
    from app.models.generated_lesson import GeneratedLesson
    from app.models.presentation import Presentation
    from app.models.review_schedule import ReviewSchedule
    from app.models.user import User
    from tests.conftest import TestSessionLocal

    user_id = uuid.uuid4()
    now = time.time()

    async with TestSessionLocal() as session:
        session.add(
            User(
                id=user_id,
                email=f"p14_{uuid.uuid4().hex[:8]}@test.com",
                name="P14 Retention Learner",
                password_hash=hash_password("password123"),
            )
        )
        await session.flush()

        pres = Presentation(
            title="P14 Retention Deck",
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
            title="P14 Retention Lesson",
            latest_version=1,
        )
        session.add(lesson)
        await session.flush()

        weak = Concept(
            name=_WEAK_NAME, topic="probability", presentation_id=pres.id, lesson_id=lesson.id
        )
        strong = Concept(
            name=_STRONG_NAME, topic="linear-algebra", presentation_id=pres.id, lesson_id=lesson.id
        )
        session.add_all([weak, strong])
        await session.flush()

        memory = {
            "user_id": str(user_id),
            "profile": {
                "user_id": str(user_id),
                "learning_pace": "moderate",
                "total_study_minutes": 0.0,
                "average_mastery": 50.0,
                "streak_days": 1,
            },
            "completed_courses": [],
            "completed_lessons": [],
            "completed_topics": [],
            "mastered_concepts": [strong.public_id],
            "developing_concepts": [],
            "weak_concepts": [weak.public_id],
            "concept_records": {
                weak.public_id: {
                    "concept_id": weak.public_id,
                    "concept_name": _WEAK_NAME,
                    "first_learned_at": now - 3600,
                    "last_reviewed_at": now,
                    "mastery_score": weak_mastery,
                    "review_count": 1,
                    "trend": "improving",
                    "confidence_score": 0.4,
                },
                strong.public_id: {
                    "concept_id": strong.public_id,
                    "concept_name": _STRONG_NAME,
                    "first_learned_at": now - 86400,
                    "last_reviewed_at": now,
                    "mastery_score": strong_mastery,
                    "review_count": 2,
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
        session.add(EducationalMemoryRecord(user_id=user_id, memory_data=memory))
        await session.flush()

        schedule_weak = None
        if seed_schedule_weak:
            schedule_weak = ReviewSchedule(
                user_id=user_id,
                concept_id=weak.id,
                lesson_id=lesson.id,
                topic=_WEAK_NAME,
                status="scheduled",
                scheduled_date=datetime.now(UTC).date(),
                interval_days=_LADDER[step_weak],
                mastery_at_schedule=weak_mastery,
                due_at=datetime.now(UTC) + timedelta(days=due_offset_days),
                review_metadata={"step": step_weak},
            )
            session.add(schedule_weak)
            await session.flush()

        await session.commit()
        # Re-read public ids after commit (public_id is server-generated).
        if schedule_weak is not None:
            await session.refresh(schedule_weak)

    _JWT_USERS[str(user_id)] = _RealUser(user_id, "p14_auto@test.com", "P14 Auto Learner")
    return {
        "user_id": str(user_id),
        "lesson_id": lesson.public_id,
        "weak_id": weak.public_id,
        "strong_id": strong.public_id,
        "schedule_weak_id": schedule_weak.public_id if schedule_weak else None,
    }


async def _read_schedule(user_id: uuid.UUID, schedule_public_id: str) -> Any:
    from app.models.review_schedule import ReviewSchedule
    from tests.conftest import TestSessionLocal

    async with TestSessionLocal() as session:
        row = (
            await session.execute(
                select(ReviewSchedule).where(
                    ReviewSchedule.user_id == user_id,
                    ReviewSchedule.public_id == schedule_public_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return {
            "review_metadata": dict(row.review_metadata or {}),
            "status": row.status,
            "interval_days": int(row.interval_days),
        }


async def _read_memory_mastery(user_id: uuid.UUID, concept_public_id: str) -> float | None:
    from app.models.educational_memory import EducationalMemoryRecord
    from tests.conftest import TestSessionLocal

    async with TestSessionLocal() as session:
        row = (
            await session.execute(
                select(EducationalMemoryRecord).where(EducationalMemoryRecord.user_id == user_id)
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        record = (row.memory_data or {}).get("concept_records", {}).get(concept_public_id)
        return float(record["mastery_score"]) if record else None


# ---------------------------------------------------------------------------
# Auth / validation guards
# ---------------------------------------------------------------------------


async def test_unauthenticated_p14_requests_rejected() -> None:
    async with await _make_client() as client:
        resp = await client.post(
            "/api/v1/me/review/some-schedule/complete", json={"outcome": "good"}
        )
        assert resp.status_code == 401
        resp = await client.post("/api/v1/me/review/some-schedule/complete")
        assert resp.status_code == 401
        resp = await client.get("/api/v1/me/analytics/retention")
        assert resp.status_code == 401


async def test_invalid_outcome_is_422() -> None:
    lookups = await _seed_review_learner()
    async with await _make_client() as client:
        headers = _headers(uuid.UUID(lookups["user_id"]))
        for invalid in ("gonzo", "GOOD", "I-forgot", ""):
            resp = await client.post(
                f"/api/v1/me/review/{lookups['schedule_weak_id']}/complete",
                json={"outcome": invalid},
                headers=headers,
            )
            assert resp.status_code == 422, f"outcome={invalid!r} -> {resp.status_code}"
        # Nonexistent schedule still 404 with a valid body.
        resp = await client.post(
            "/api/v1/me/review/does-not-exist/complete",
            json={"outcome": "easy"},
            headers=headers,
        )
        assert resp.status_code == 404


async def test_cross_user_complete_is_404_with_no_writes() -> None:
    lookups = await _seed_review_learner()
    uid_a = uuid.UUID(lookups["user_id"])
    uid_b = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
    async with await _make_client() as client:
        resp = await client.post(
            f"/api/v1/me/review/{lookups['schedule_weak_id']}/complete",
            json={"outcome": "easy"},
            headers=_headers(uid_b),
        )
        assert resp.status_code == 404
    # No row mutated for user B (nor for A by B's attempt).
    row = await _read_schedule(uid_a, lookups["schedule_weak_id"])
    assert row["status"] == "scheduled"
    assert "history" not in row["review_metadata"]


# ---------------------------------------------------------------------------
# Outcome-driven spacing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("outcome", "expected_interval", "expected_step"),
    [
        ("again", 1, 0),  # lapse resets to the tightest interval
        ("hard", 3, 1),  # hold the interval at step 1
        ("good", 7, 2),  # default-equivalent advance
        ("easy", 14, 3),  # skip ahead, bounded by the ladder top
    ],
)
async def test_outcome_spacing_step1(
    outcome: str, expected_interval: int, expected_step: int
) -> None:
    lookups = await _seed_review_learner(weak_mastery=55.0, step_weak=1)
    uid = uuid.UUID(lookups["user_id"])
    async with await _make_client() as client:
        resp = await client.post(
            f"/api/v1/me/review/{lookups['schedule_weak_id']}/complete",
            json={"outcome": outcome},
            headers=_headers(uid),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["outcome"] == outcome
        assert data["next_interval_days"] == expected_interval
        assert data["next_due_at"] is not None
        # The response carries the retention signal for this concept.
        assert data["retained_strength"] is None or 0.0 <= data["retained_strength"] <= 100.0

    row = await _read_schedule(uid, lookups["schedule_weak_id"])
    assert row["interval_days"] == expected_interval
    assert row["review_metadata"]["step"] == expected_step
    assert row["review_metadata"]["v"] == 2
    counts = row["review_metadata"]["counts"]
    assert counts == {"again": 0, "hard": 0, "good": 0, "easy": 0} | {outcome: 1}
    history = row["review_metadata"]["history"]
    assert len(history) == 1
    assert history[0]["outcome"] == outcome
    assert history[0]["at"], "history entries must carry a timestamp"


async def test_no_body_completes_like_legacy_good() -> None:
    """Backward-compat regression: empty body reproduces today's interval."""
    lookups = await _seed_review_learner(weak_mastery=55.0, step_weak=1)
    uid = uuid.UUID(lookups["user_id"])
    async with await _make_client() as client:
        resp = await client.post(
            f"/api/v1/me/review/{lookups['schedule_weak_id']}/complete",
            headers=_headers(uid),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["outcome"] == "good"
        assert data["next_interval_days"] == 7
        assert data["status"] == "scheduled"
        # Explicit good == no-body (bit-for-bit identical spacing).
        resp2 = await client.post(
            f"/api/v1/me/review/{lookups['schedule_weak_id']}/complete",
            json={"outcome": "good"},
            headers=_headers(uid),
        )
        assert resp2.status_code == 200
        assert resp2.json()["data"]["next_interval_days"] == 14


async def test_mastery_scalar_is_never_rewritten_by_review() -> None:
    """The invariant: completing with ANY outcome must not touch quiz mastery."""
    lookups = await _seed_review_learner(weak_mastery=55.0, step_weak=1)
    uid = uuid.UUID(lookups["user_id"])
    async with await _make_client() as client:
        for outcome in ("again", "hard", "good", "easy"):
            resp = await client.post(
                f"/api/v1/me/review/{lookups['schedule_weak_id']}/complete",
                json={"outcome": outcome},
                headers=_headers(uid),
            )
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["mastery_score"] == 55.0, f"{outcome} rewrote mastery in the response"
        # Persisted memory is untouched too.
        assert await _read_memory_mastery(uid, lookups["weak_id"]) == 55.0
        assert await _read_memory_mastery(uid, lookups["strong_id"]) == 90.0


async def test_history_is_capped_at_max() -> None:
    lookups = await _seed_review_learner(weak_mastery=55.0, step_weak=0)
    uid = uuid.UUID(lookups["user_id"])
    async with await _make_client() as client:
        for _ in range(25):
            resp = await client.post(
                f"/api/v1/me/review/{lookups['schedule_weak_id']}/complete",
                json={"outcome": "good"},
                headers=_headers(uid),
            )
            assert resp.status_code == 200
    row = await _read_schedule(uid, lookups["schedule_weak_id"])
    history = row["review_metadata"]["history"]
    assert len(history) == retention.MAX_HISTORY
    assert sum(row["review_metadata"]["counts"].values()) == retention.MAX_HISTORY


# ---------------------------------------------------------------------------
# Queue enrichment + retention endpoint
# ---------------------------------------------------------------------------


async def test_queue_items_advertise_retention_fields() -> None:
    lookups = await _seed_review_learner(weak_mastery=55.0, step_weak=1)
    uid = uuid.UUID(lookups["user_id"])
    async with await _make_client() as client:
        resp = await client.get("/api/v1/me/review?limit=10", headers=_headers(uid))
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        assert items, "seeded weak concept must appear in the due queue"
        for item in items:
            assert "retention_status" in item
            assert "review_accuracy" in item
        due = next(i for i in items if i["schedule_id"] == lookups["schedule_weak_id"])
        assert due["retention_status"] == "overdue"
        assert due["review_accuracy"] is None


async def test_retention_endpoint_aggregates_and_orders() -> None:
    lookups = await _seed_review_learner(weak_mastery=55.0, strong_mastery=90.0)
    uid = uuid.UUID(lookups["user_id"])
    async with await _make_client() as client:
        resp = await client.get("/api/v1/me/analytics/retention", headers=_headers(uid))
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert "summary" in data
        assert "concepts" in data
        assert data["max"] == 100
        assert len(data["concepts"]) == 2

        by_id = {c["concept_public_id"]: c for c in data["concepts"]}
        weak = by_id[lookups["weak_id"]]
        strong = by_id[lookups["strong_id"]]

        # Due + unreviewed -> overdue (scope rule), with a decayed anchor.
        assert weak["status"] == "overdue"
        assert weak["band"] == "developing"
        assert weak["mastery_score"] == 55.0
        assert weak["retained_strength"] is None or weak["retained_strength"] <= 55.0
        assert weak["deep_link_practice"] is not None
        assert weak["due_at"] is not None

        # Never entered the review loop -> new, no fabricated strength.
        assert strong["status"] == "new"
        assert strong["retained_strength"] is None
        assert strong["review_accuracy"] is None
        assert strong["due_at"] is None
        assert strong["days_since_review"] is None

        # Deterministic ordering: overdue bucket precedes new.
        statuses = [c["status"] for c in data["concepts"]]
        assert statuses == ["overdue", "new"]
        assert data["summary"]["overdue_count"] == 1
        assert data["summary"]["new_count"] == 1
        assert data["summary"]["at_risk_count"] == 0
        assert data["summary"]["on_track_count"] == 0


async def test_retention_history_drives_accuracy() -> None:
    """A reviewed concept with recall history reports bounded accuracy."""
    from app.models.concept import Concept
    from app.models.generated_lesson import GeneratedLesson
    from app.models.presentation import Presentation
    from app.models.review_schedule import ReviewSchedule
    from tests.conftest import TestSessionLocal

    lookups = await _seed_review_learner(seed_schedule_weak=False)
    uid = uuid.UUID(lookups["user_id"])
    now = datetime.now(UTC)

    async with TestSessionLocal() as session:
        concept = (
            await session.execute(select(Concept).where(Concept.public_id == lookups["weak_id"]))
        ).scalar_one()
        lesson = (
            await session.execute(
                select(GeneratedLesson).where(GeneratedLesson.public_id == lookups["lesson_id"])
            )
        ).scalar_one()
        schedule = ReviewSchedule(
            user_id=uid,
            concept_id=concept.id,
            lesson_id=lesson.id,
            topic=_WEAK_NAME,
            status="scheduled",
            scheduled_date=now.date(),
            interval_days=7,
            mastery_at_schedule=55.0,
            due_at=now + timedelta(days=7),
            review_metadata={
                "step": 2,
                "v": 2,
                "history": [
                    {"outcome": "hard", "at": (now - timedelta(days=10)).isoformat()},
                    {"outcome": "good", "at": (now - timedelta(days=5)).isoformat()},
                ],
                "counts": {"again": 0, "hard": 1, "good": 1, "easy": 0},
            },
        )
        session.add(schedule)
        await session.commit()

    async with await _make_client() as client:
        resp = await client.get("/api/v1/me/analytics/retention", headers=_headers(uid))
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        concept_row = next(
            c for c in data["concepts"] if c["concept_public_id"] == lookups["weak_id"]
        )
        # 1 of 2 recalls (good) -> 50% (hard is NOT a success).
        assert concept_row["review_accuracy"] == 50.0
        assert concept_row["review_count"] == 1  # memory review count, not JSONB length
        # Recent good, not due, strength < 80 -> at_risk.
        assert concept_row["status"] == "at_risk"
        assert concept_row["retained_strength"] is not None
        assert 0.0 <= concept_row["retained_strength"] <= 100.0
        assert concept_row["days_since_review"] is not None


async def test_retention_is_learner_scoped_b_gets_own_empty_result() -> None:
    await _seed_review_learner(weak_mastery=55.0)
    uid_b = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
    async with await _make_client() as client:
        resp = await client.get("/api/v1/me/analytics/retention", headers=_headers(uid_b))
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["concepts"] == []
        assert data["summary"] == {
            "retention_average": None,
            "on_track_count": 0,
            "at_risk_count": 0,
            "overdue_count": 0,
            "new_count": 0,
        }
        assert data["max"] == 100


async def test_p14_metrics_counters_appear_after_activity() -> None:
    lookups = await _seed_review_learner(weak_mastery=55.0, step_weak=1)
    uid = uuid.UUID(lookups["user_id"])
    async with await _make_client() as client:
        resp = await client.post(
            f"/api/v1/me/review/{lookups['schedule_weak_id']}/complete",
            json={"outcome": "again"},
            headers=_headers(uid),
        )
        assert resp.status_code == 200
        await client.get("/api/v1/me/analytics/retention", headers=_headers(uid))

        metrics_resp = await client.get("/api/v1/metrics")
        assert metrics_resp.status_code == 200
        body = metrics_resp.text
        assert 'p14_review_outcomes_total{outcome="again"' in body
        assert "p14_retention_views_total" in body
