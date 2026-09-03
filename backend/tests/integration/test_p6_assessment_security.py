"""P6 assessment integration + security coverage.

Verifies the interactive assessment flow is correctly integrated with the
existing quiz subsystem and that ownership boundaries are never crossed:

* User A can access their own quiz / attempts / results.
* User B cannot read, start, submit, or retrieve anything from User A's quiz.
* Answers are validated against each question's allowed options.
* Results never leak another user's score, answers, attempt id or metadata.
* Quiz submission updates the learner's mastery and next-action state.
* Mastery / progress / recommendations are strictly user-isolated.

Reuses the existing deterministic quiz fixtures (SQLite, same as the fast
suite) and the real HTTP app via ``client`` — no mocked 200 responses.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from tests.conftest import TEST_USER_ID

SECOND_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def owner_quiz(db_session: AsyncSession) -> dict:
    """A presentation + quiz with 2 MC questions owned by TEST_USER_ID."""
    from app.core.security import hash_password
    from app.models.answer_key import AnswerKey
    from app.models.presentation import Presentation
    from app.models.quiz import Quiz
    from app.models.quiz_content import Question, QuestionOption
    from app.models.quiz_version import QuizVersion
    from app.models.user import User

    # Ensure User A exists in the DB.
    existing = await db_session.execute(select(User).where(User.id == TEST_USER_ID))
    if existing.scalar_one_or_none() is None:
        db_session.add(
            User(
                id=TEST_USER_ID,
                email="p6_a@example.com",
                name="User A",
                password_hash=hash_password("testpassword123"),
            )
        )
        await db_session.flush()

    pres = Presentation(
        title="P6 Owner Presentation",
        owner_id=TEST_USER_ID,
        status="published",
        slide_count=2,
    )
    db_session.add(pres)
    await db_session.flush()

    quiz = Quiz(
        presentation_id=pres.id,
        user_id=TEST_USER_ID,
        status="published",
        mode="practice",
        title="P6 Knowledge Check",
        question_count=2,
        max_attempts_per_user=3,
        passing_score=50.0,
        show_feedback_after=True,
        latest_version=1,
        published_version=1,
    )
    db_session.add(quiz)
    await db_session.flush()

    version = QuizVersion(quiz_id=quiz.id, version=1, status="published", title="v1")
    db_session.add(version)
    await db_session.flush()

    questions = []
    for i, (stem, correct_pos) in enumerate(
        [("2 + 2 = ?", 2), ("Color of the sky?", 2)], start=1
    ):
        q = Question(
            quiz_version_id=version.id,
            position=i,
            question_type="multiple_choice",
            stem=stem,
            points=1,
            bloom_level="remember",
            difficulty="beginner",
        )
        db_session.add(q)
        await db_session.flush()
        opts = [
            QuestionOption(question_id=q.id, position=1, text="A", is_correct=False),
            QuestionOption(question_id=q.id, position=2, text="B", is_correct=False),
            QuestionOption(question_id=q.id, position=3, text="C", is_correct=False),
        ]
        opts[correct_pos - 1].is_correct = True
        db_session.add_all(opts)
        await db_session.flush()
        db_session.add(
            AnswerKey(
                question_id=q.id,
                answer_type="multiple_choice",
                correct_option_ids=[opts[correct_pos - 1].public_id],
            )
        )
        questions.append(q)

    await db_session.commit()
    return {
        "quiz_id": quiz.public_id,
        "presentation_id": pres.public_id,
        "question_ids": [q.public_id for q in questions],
    }


@pytest_asyncio.fixture
async def other_user_id(db_session: AsyncSession) -> uuid.UUID:
    """A second distinct user (User B) that owns nothing relevant."""
    from app.core.security import hash_password
    from app.models.user import User

    existing = await db_session.execute(select(User).where(User.id == SECOND_USER_ID))
    if existing.scalar_one_or_none() is None:
        db_session.add(
            User(
                id=SECOND_USER_ID,
                email="p6_b@example.com",
                name="User B",
                password_hash=hash_password("testpassword123"),
            )
        )
        await db_session.flush()
        await db_session.commit()
    return SECOND_USER_ID


class _OtherFakeUser:
    def __init__(self, uid: uuid.UUID) -> None:
        self.id = uid
        self.email = "p6_b@example.com"
        self.name = "User B"


@pytest.fixture
def as_other_user(other_user_id: uuid.UUID):
    """Run a block authenticated as User B by overriding get_current_user."""
    from app.core.dependencies import get_current_user

    def _install() -> None:
        async def _fake_other():
            return _OtherFakeUser(other_user_id)

        app.dependency_overrides[get_current_user] = _fake_other

    def _restore() -> None:
        app.dependency_overrides.pop(get_current_user, None)

    return _install, _restore


# ---------------------------------------------------------------------------
# Quiz / attempt ownership (A owns, B cannot)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_owner_can_read_and_start_own_quiz(client: AsyncClient, owner_quiz: dict):
    resp = await client.get("/api/v1/quizzes/" + owner_quiz["quiz_id"])
    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == owner_quiz["quiz_id"]

    resp = await client.post("/api/v1/quizzes/" + owner_quiz["quiz_id"] + "/attempts")
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["status"] == "in_progress"
    assert len(data["questions"]) == 2
    for q in data["questions"]:
        for opt in q["options"]:
            assert "is_correct" not in opt


@pytest.mark.asyncio
async def test_user_b_cannot_read_quiz(client: AsyncClient, owner_quiz: dict, as_other_user):
    install, restore = as_other_user
    install()
    try:
        resp = await client.get("/api/v1/quizzes/" + owner_quiz["quiz_id"])
        assert resp.status_code == 404
    finally:
        restore()


@pytest.mark.asyncio
async def test_user_b_cannot_start_attempt(client: AsyncClient, owner_quiz: dict, as_other_user):
    install, restore = as_other_user
    install()
    try:
        resp = await client.post("/api/v1/quizzes/" + owner_quiz["quiz_id"] + "/attempts")
        assert resp.status_code == 404
    finally:
        restore()


@pytest.mark.asyncio
async def test_user_b_cannot_submit_others_quiz(client: AsyncClient, owner_quiz: dict, as_other_user):
    # User A starts an attempt.
    resp = await client.post("/api/v1/quizzes/" + owner_quiz["quiz_id"] + "/attempts")
    attempt_id = resp.json()["data"]["attempt_id"]

    # User B tries to submit User A's attempt -> 404.
    install, restore = as_other_user
    install()
    try:
        resp = await client.post(
            f"/api/v1/quizzes/{owner_quiz['quiz_id']}/attempts/{attempt_id}/submit",
            json={"answers": [], "time_spent_seconds": 10},
        )
        assert resp.status_code == 404
    finally:
        restore()


@pytest.mark.asyncio
async def test_attempt_belongs_to_quiz_isolation(client: AsyncClient, db_session: AsyncSession):
    """A quiz is not linked. Attempt must belong to the same quiz."""
    from app.core.security import hash_password
    from app.models.presentation import Presentation
    from app.models.quiz import Quiz
    from app.models.user import User

    existing = await db_session.execute(select(User).where(User.id == TEST_USER_ID))
    if existing.scalar_one_or_none() is None:
        db_session.add(
            User(
                id=TEST_USER_ID,
                email="p6_a@example.com",
                name="User A",
                password_hash=hash_password("testpassword123"),
            )
        )
        await db_session.flush()

    pres = Presentation(title="Isolation Pres", owner_id=TEST_USER_ID, status="published")
    pres2 = Presentation(title="Second Pres", owner_id=TEST_USER_ID, status="published")
    db_session.add_all([pres, pres2])
    await db_session.flush()

    from app.models.quiz_version import QuizVersion

    q1 = Quiz(presentation_id=pres.id, status="published", latest_version=1, published_version=1)
    q2 = Quiz(presentation_id=pres2.id, status="published", latest_version=1, published_version=1)
    db_session.add_all([q1, q2])
    await db_session.flush()
    v1 = QuizVersion(quiz_id=q1.id, version=1, status="published", title="q1 v1")
    v2 = QuizVersion(quiz_id=q2.id, version=1, status="published", title="q2 v1")
    db_session.add_all([v1, v2])
    await db_session.commit()

    # Start an attempt on q1.
    resp = await client.post("/api/v1/quizzes/" + q1.public_id + "/attempts")
    attempt_id = resp.json()["data"]["attempt_id"]

    # Use q2's id with q1's attempt -> 404.
    resp = await client.post(
        f"/api/v1/quizzes/{q2.public_id}/attempts/{attempt_id}/submit",
        json={"answers": [], "time_spent_seconds": 0},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Result isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_result_isolation_across_users(client: AsyncClient, owner_quiz: dict, as_other_user):
    # User A completes the attempt with a known score.
    start = await client.post("/api/v1/quizzes/" + owner_quiz["quiz_id"] + "/attempts")
    attempt_id = start.json()["data"]["attempt_id"]
    submit = await client.post(
        f"/api/v1/quizzes/{owner_quiz['quiz_id']}/attempts/{attempt_id}/submit",
        json={"answers": [], "time_spent_seconds": 5},
    )
    assert submit.status_code == 200

    # User B retrieves User A's attempt -> 404, no score/answer leak.
    install, restore = as_other_user
    install()
    try:
        resp = await client.get(
            f"/api/v1/quizzes/{owner_quiz['quiz_id']}/attempts/{attempt_id}"
        )
        assert resp.status_code == 404
    finally:
        restore()


@pytest.mark.asyncio
async def test_list_attempts_user_scoped(client: AsyncClient, owner_quiz: dict, as_other_user):
    start = await client.post("/api/v1/quizzes/" + owner_quiz["quiz_id"] + "/attempts")
    own_attempt = start.json()["data"]["attempt_id"]

    resp = await client.get("/api/v1/quizzes/" + owner_quiz["quiz_id"] + "/attempts")
    assert resp.status_code == 200
    ids = [a["attempt_id"] for a in resp.json()["data"]]
    assert own_attempt in ids

    # User B cannot even list User A's attempts on the same quiz -> 404.
    install, restore = as_other_user
    install()
    try:
        resp = await client.get("/api/v1/quizzes/" + owner_quiz["quiz_id"] + "/attempts")
        assert resp.status_code == 404
    finally:
        restore()


# ---------------------------------------------------------------------------
# Answer validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_invalid_question_id(client: AsyncClient, owner_quiz: dict):
    start = await client.post("/api/v1/quizzes/" + owner_quiz["quiz_id"] + "/attempts")
    attempt_id = start.json()["data"]["attempt_id"]
    resp = await client.post(
        f"/api/v1/quizzes/{owner_quiz['quiz_id']}/attempts/{attempt_id}/answers/q_does_not_exist",
        json={"option_ids": ["whatever"]},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_answer_with_invalid_option_still_scores_zero(
    client: AsyncClient, owner_quiz: dict
):
    """Submitting an unknown option id must not crash and must not be correct."""
    start = await client.post("/api/v1/quizzes/" + owner_quiz["quiz_id"] + "/attempts")
    data = start.json()["data"]
    attempt_id = data["attempt_id"]
    q1 = data["questions"][0]
    invalid_opt = "opt_bogus_123"

    resp = await client.post(
        f"/api/v1/quizzes/{owner_quiz['quiz_id']}/attempts/{attempt_id}/answers/{q1['id']}",
        json={"option_ids": [invalid_opt]},
    )
    assert resp.status_code == 200

    submit = await client.post(
        f"/api/v1/quizzes/{owner_quiz['quiz_id']}/attempts/{attempt_id}/submit",
        json={"answers": [], "time_spent_seconds": 5},
    )
    result = submit.json()["data"]
    fb = next(f for f in result["question_feedback"] if f["position"] == 1)
    assert fb["is_correct"] is False
    assert fb["points_earned"] == 0


@pytest.mark.asyncio
async def test_malformed_answer_payload_rejected(client: AsyncClient, owner_quiz: dict):
    start = await client.post("/api/v1/quizzes/" + owner_quiz["quiz_id"] + "/attempts")
    attempt_id = start.json()["data"]["attempt_id"]
    resp = await client.post(
        f"/api/v1/quizzes/{owner_quiz['quiz_id']}/attempts/{attempt_id}/submit",
        json="not-json",
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_duplicate_answer_last_wins(client: AsyncClient, owner_quiz: dict):
    start = await client.post("/api/v1/quizzes/" + owner_quiz["quiz_id"] + "/attempts")
    data = start.json()["data"]
    attempt_id = data["attempt_id"]
    q1 = data["questions"][0]
    # Correct answer is at position 2.
    correct_opt = next(o for o in q1["options"] if o["position"] == 2)["id"]
    wrong_opt = next(o for o in q1["options"] if o["position"] == 1)["id"]

    await client.post(
        f"/api/v1/quizzes/{owner_quiz['quiz_id']}/attempts/{attempt_id}/answers/{q1['id']}",
        json={"option_ids": [wrong_opt]},
    )
    await client.post(
        f"/api/v1/quizzes/{owner_quiz['quiz_id']}/attempts/{attempt_id}/answers/{q1['id']}",
        json={"option_ids": [correct_opt]},
    )
    submit = await client.post(
        f"/api/v1/quizzes/{owner_quiz['quiz_id']}/attempts/{attempt_id}/submit",
        json={"answers": [], "time_spent_seconds": 5},
    )
    result = submit.json()["data"]
    fb = next(f for f in result["question_feedback"] if f["position"] == 1)
    assert fb["is_correct"] is True


@pytest.mark.asyncio
async def test_submit_completed_attempt_rejected(client: AsyncClient, owner_quiz: dict):
    start = await client.post("/api/v1/quizzes/" + owner_quiz["quiz_id"] + "/attempts")
    attempt_id = start.json()["data"]["attempt_id"]
    await client.post(
        f"/api/v1/quizzes/{owner_quiz['quiz_id']}/attempts/{attempt_id}/submit",
        json={"answers": [], "time_spent_seconds": 5},
    )
    # Submitting again -> 409 Conflict.
    resp = await client.post(
        f"/api/v1/quizzes/{owner_quiz['quiz_id']}/attempts/{attempt_id}/submit",
        json={"answers": [], "time_spent_seconds": 5},
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Mastery integration + user isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submission_updates_mastery_and_recommendation(
    client: AsyncClient, owner_quiz: dict
):
    start = await client.post("/api/v1/quizzes/" + owner_quiz["quiz_id"] + "/attempts")
    data = start.json()["data"]
    attempt_id = data["attempt_id"]

    # Answer both questions correctly.
    answers = []
    for q in data["questions"]:
        correct_opt = next(o for o in q["options"] if o["position"] == 2)["id"]
        answers.append({"question_id": q["id"], "option_ids": [correct_opt]})

    submit = await client.post(
        f"/api/v1/quizzes/{owner_quiz['quiz_id']}/attempts/{attempt_id}/submit",
        json={"answers": answers, "time_spent_seconds": 12},
    )
    assert submit.status_code == 200
    result = submit.json()["data"]
    assert result["status"] == "completed"
    assert result["percent_score"] == 100.0
    assert result["passed"] is True
    assert result["recommendations"] is not None


@pytest.mark.asyncio
async def test_mastery_is_user_scoped(
    client: AsyncClient, db_session: AsyncSession, owner_quiz: dict, other_user_id: uuid.UUID
):
    """User A's submission must not write mastery records for User B."""
    from app.models.educational_memory import EducationalMemoryRecord

    start = await client.post("/api/v1/quizzes/" + owner_quiz["quiz_id"] + "/attempts")
    data = start.json()["data"]
    attempt_id = data["attempt_id"]
    answers = []
    for q in data["questions"]:
        correct_opt = next(o for o in q["options"] if o["position"] == 2)["id"]
        answers.append({"question_id": q["id"], "option_ids": [correct_opt]})
    await client.post(
        f"/api/v1/quizzes/{owner_quiz['quiz_id']}/attempts/{attempt_id}/submit",
        json={"answers": answers, "time_spent_seconds": 12},
    )

    async def user_records(uid: uuid.UUID) -> list:
        rows = await db_session.execute(
            select(EducationalMemoryRecord).where(
                EducationalMemoryRecord.user_id == uid
            )
        )
        return list(rows.scalars().all())

    records_a = await user_records(TEST_USER_ID)
    records_b = await user_records(other_user_id)
    assert len(records_a) > 0, "User A's mastery should have been recorded"
    assert len(records_b) == 0, "User B must have no mastery records from A's submission"
