"""P7 learner-progress dashboard integration + security coverage.

Verifies the ``GET /api/v1/me/progress`` aggregate endpoint:

* required authentication (401 without a valid user)
* returns the authenticated learner's OWN data only
* cross-user isolation — User B never sees User A's lessons/mastery/attempts
* empty-state behaviour for a user with no activity
* actual response content (mastery, weak/strong concepts, recommendations,
  recent attempts, trend, lesson progress) is asserted, not just status codes

Uses a unique user per scenario (seeding through the shared test DB) and the
real HTTP app via ``client`` — no mocked 200 responses.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.services.educational_memory_service import educational_memory_service
from tests.learner_progress_helpers import seed_learner, seed_user


def _uid() -> uuid.UUID:
    return uuid.uuid4()


class _AuthedUser:
    """A user we can authenticate as by overriding ``get_current_user``."""

    def __init__(self, uid: uuid.UUID, email: str = "lp_user@example.com") -> None:
        self.uid = uid
        self.email = email
        self.name = "Progress Learner"

    @property
    def id(self) -> uuid.UUID:
        """The router/schema expect a ``user.id`` attribute."""
        return self.uid

    def install(self) -> None:
        from app.core.dependencies import get_current_user

        async def _fake():
            return self

        app.dependency_overrides[get_current_user] = _fake

    def restore(self) -> None:
        from app.core.dependencies import get_current_user

        app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture(autouse=True)
def _reset_memory_cache():
    """Ensure a fresh, empty educational-memory cache per test.

    The module-level ``educational_memory_service`` carries an in-memory
    BoundedCache keyed by user. We seed memory directly into the DB, so we must
    start each test with an empty cache to read the seeded state.
    """
    educational_memory_service._memories.clear()  # noqa: SLF001
    return


# ---------------------------------------------------------------------------
# Auth requirement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dashboard_requires_authentication(client: AsyncClient) -> None:
    # Remove the autouse get_current_user override so no user is resolved.
    from app.core.dependencies import get_current_user

    app.dependency_overrides.pop(get_current_user, None)
    try:
        resp = await client.get("/api/v1/me/progress")
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# Empty state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_state(client: AsyncClient, db_session: AsyncSession) -> None:
    user = _AuthedUser(_uid(), "lp_empty@example.com")
    await seed_user(db_session, user.uid, email=user.email)
    user.install()
    try:
        resp = await client.get("/api/v1/me/progress")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["summary"]["lessons_completed"] == 0
        assert data["summary"]["average_mastery"] == 0.0
        assert data["summary"]["weak_concepts"] == 0
        assert data["recommendations"] == []
        assert data["recent_attempts"] == []
        assert data["trend"] == []
        assert data["weak_concepts"] == []
        assert data["strong_concepts"] == []
    finally:
        user.restore()


# ---------------------------------------------------------------------------
# Content assertions (learner sees own data)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dashboard_returns_own_progress(client: AsyncClient, db_session: AsyncSession) -> None:
    user = _AuthedUser(_uid(), "lp_full@example.com")
    lookups = await seed_learner(db_session, user.uid, email=user.email, attempt_percent=85.0)
    user.install()
    try:
        resp = await client.get("/api/v1/me/progress")
        assert resp.status_code == 200
        data = resp.json()["data"]

        # Summary
        assert data["summary"]["lessons_completed"] == 1
        assert data["summary"]["lessons_in_progress"] == 0
        assert data["summary"]["mastered_concepts"] == 1
        assert data["summary"]["weak_concepts"] == 1
        assert data["summary"]["attempts_total"] == 1

        # Lesson progress + resume surface
        assert len(data["lesson_progress"]) == 1
        lp = data["lesson_progress"][0]
        assert lp["lesson_id"] == lookups["lesson_id"]
        assert lp["completion_percentage"] == 100.0
        assert lp["status"] == "completed"

        # Mastery summaries
        statuses = {c["status"] for c in data["concept_mastery"]}
        assert "weak" in statuses
        assert "mastered" in statuses

        # Weak + strong concept lists
        assert data["weak_concepts"]
        assert data["weak_concepts"][0]["concept_name"] == "Gaussian Distributions"
        assert data["strong_concepts"]
        assert data["strong_concepts"][0]["concept_name"] == "Vector Spaces"

        # Deterministic recommendations
        assert data["recommendations_summary"]
        assert data["recommendations"], "expected at least one recommendation"
        assert all(r["priority"] for r in data["recommendations"])

        # Recent attempts + trend
        assert data["recent_attempts"][0]["attempt_id"] == lookups["attempt_id"]
        assert data["recent_attempts"][0]["percent_score"] == 85.0
        assert data["recent_attempts"][0]["passed"] is True
        assert len(data["trend"]) == 1
        assert data["trend"][0]["value"] == 85.0
    finally:
        user.restore()


# ---------------------------------------------------------------------------
# Cross-user isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_user_b_never_sees_user_a_data(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_a = _AuthedUser(_uid(), "lp_a@example.com")
    user_b = _AuthedUser(_uid(), "lp_b@example.com")
    lookups_a = await seed_learner(db_session, user_a.uid, email=user_a.email)

    # Scrub User B's memory cache so the empty state is genuinely empty for B.
    user_b.install()
    try:
        resp = await client.get("/api/v1/me/progress")
        assert resp.status_code == 200
        data = resp.json()["data"]
        # B sees none of A's data.
        assert data["summary"]["lessons_completed"] == 0
        assert data["summary"]["mastered_concepts"] == 0
        assert data["summary"]["weak_concepts"] == 0
        assert data["summary"]["attempts_total"] == 0
        assert data["recent_attempts"] == []
        assert data["weak_concepts"] == []
        assert data["strong_concepts"] == []
        lesson_ids = [lp["lesson_id"] for lp in data["lesson_progress"]]
        assert lookups_a["lesson_id"] not in lesson_ids
    finally:
        user_b.restore()

    # A still sees their own data on a fresh call.
    user_a.install()
    try:
        resp = await client.get("/api/v1/me/progress")
        data = resp.json()["data"]
        assert data["summary"]["lessons_completed"] == 1
        assert data["summary"]["attempts_total"] == 1
    finally:
        user_a.restore()


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bounded_recent_attempts_and_trend(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = _AuthedUser(_uid(), "lp_many@example.com")
    lookups = await seed_learner(db_session, user.uid, email=user.email)
    # Add several more completed attempts for the same quiz.
    from sqlalchemy import select

    from app.models.quiz import Quiz
    from app.models.quiz_attempt import QuizAttempt
    from app.models.quiz_version import QuizVersion

    quiz_row = (
        await db_session.execute(select(Quiz).where(Quiz.public_id == lookups["quiz_id"]))
    ).scalar_one()
    version = (
        (
            await db_session.execute(
                select(QuizVersion).where(QuizVersion.quiz_id == quiz_row.id)
            )
        )
        .scalars()
        .all()
    )
    for i in range(12):
        db_session.add(
            QuizAttempt(
                quiz_id=quiz_row.id,
                quiz_version_id=version[0].id,
                user_id=user.uid,
                attempt_number=2 + i,
                status="completed",
                score=0.9,
                max_score=1.0,
                percent_score=90.0,
                time_spent_seconds=100,
                is_practice=False,
            )
        )
    await db_session.commit()

    user.install()
    try:
        resp = await client.get("/api/v1/me/progress")
        data = resp.json()["data"]
        # recent_attempts and trend are bounded.
        assert len(data["recent_attempts"]) <= 20
        assert len(data["trend"]) <= 10
    finally:
        user.restore()
