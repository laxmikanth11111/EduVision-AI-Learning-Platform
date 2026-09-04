"""Quiz delivery API tests — comprehensive coverage of the quiz pipeline."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from tests.conftest import (
    TEST_USER_EMAIL,
    TEST_USER_ID,
    TestSessionLocal,
    _FakeUser,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SECOND_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


@pytest_asyncio.fixture
async def presentation_id(db_session: AsyncSession) -> str:
    """Create a test presentation owned by TEST_USER_ID and return its public_id."""
    from app.models.presentation import Presentation

    p = Presentation(
        title="Test Presentation",
        owner_id=TEST_USER_ID,
        status="published",
        slide_count=5,
    )
    db_session.add(p)
    await db_session.flush()
    await db_session.refresh(p)
    await db_session.commit()
    return p.public_id


@pytest_asyncio.fixture
async def quiz_id(db_session: AsyncSession, presentation_id: str) -> str:
    """Create a test quiz linked to the test presentation and return its public_id."""
    from app.models.answer_key import AnswerKey

    # Get the presentation UUID
    from app.models.presentation import Presentation
    from app.models.question_explanation import QuestionExplanation
    from app.models.quiz import Quiz
    from app.models.quiz_content import Question, QuestionOption
    from app.models.quiz_version import QuizVersion
    stmt = select(Presentation).where(
        Presentation.public_id == presentation_id
    )
    result = await db_session.execute(stmt)
    pres = result.scalar_one()

    # Create quiz
    quiz = Quiz(
        presentation_id=pres.id,
        user_id=TEST_USER_ID,
        status="published",
        mode="practice",
        title="Test Quiz",
        description="A test quiz",
        difficulty="beginner",
        question_count=3,
        max_attempts_per_user=3,
        passing_score=60.0,
        shuffle_questions=False,
        shuffle_options=False,
        show_feedback_after=True,
        latest_version=1,
        published_version=1,
    )
    db_session.add(quiz)
    await db_session.flush()

    # Create version
    version = QuizVersion(
        quiz_id=quiz.id,
        version=1,
        status="published",
        title="Test Quiz v1",
    )
    db_session.add(version)
    await db_session.flush()

    # Question 1: Multiple choice
    q1 = Question(
        quiz_version_id=version.id,
        position=1,
        question_type="multiple_choice",
        stem="What is 2 + 2?",
        points=1,
        bloom_level="remember",
        difficulty="beginner",
    )
    db_session.add(q1)
    await db_session.flush()

    opt1_a = QuestionOption(question_id=q1.id, position=1, text="3", is_correct=False)
    opt1_b = QuestionOption(question_id=q1.id, position=2, text="4", is_correct=True)
    opt1_c = QuestionOption(question_id=q1.id, position=3, text="5", is_correct=False)
    db_session.add_all([opt1_a, opt1_b, opt1_c])
    await db_session.flush()

    ak1 = AnswerKey(
        question_id=q1.id,
        answer_type="multiple_choice",
        correct_option_ids=[opt1_b.public_id],
    )
    db_session.add(ak1)

    exp1 = QuestionExplanation(
        question_id=q1.id,
        explanation="2 + 2 equals 4.",
        display_timing="after_submit",
    )
    db_session.add(exp1)

    # Question 2: True/False
    q2 = Question(
        quiz_version_id=version.id,
        position=2,
        question_type="true_false",
        stem="The sky is blue.",
        points=1,
        bloom_level="remember",
        difficulty="beginner",
    )
    db_session.add(q2)
    await db_session.flush()

    opt2_t = QuestionOption(question_id=q2.id, position=1, text="True", is_correct=True)
    opt2_f = QuestionOption(question_id=q2.id, position=2, text="False", is_correct=False)
    db_session.add_all([opt2_t, opt2_f])
    await db_session.flush()

    ak2 = AnswerKey(
        question_id=q2.id,
        answer_type="true_false",
        correct_option_ids=[opt2_t.public_id],
    )
    db_session.add(ak2)

    # Question 3: Multiple select
    q3 = Question(
        quiz_version_id=version.id,
        position=3,
        question_type="multiple_select",
        stem="Which are prime numbers?",
        points=2,
        bloom_level="understand",
        difficulty="intermediate",
    )
    db_session.add(q3)
    await db_session.flush()

    opt3_a = QuestionOption(question_id=q3.id, position=1, text="2", is_correct=True)
    opt3_b = QuestionOption(question_id=q3.id, position=2, text="3", is_correct=True)
    opt3_c = QuestionOption(question_id=q3.id, position=3, text="4", is_correct=False)
    opt3_d = QuestionOption(question_id=q3.id, position=4, text="5", is_correct=True)
    db_session.add_all([opt3_a, opt3_b, opt3_c, opt3_d])
    await db_session.flush()

    ak3 = AnswerKey(
        question_id=q3.id,
        answer_type="multiple_select",
        correct_option_ids=[opt3_a.public_id, opt3_b.public_id, opt3_d.public_id],
    )
    db_session.add(ak3)

    await db_session.flush()
    await db_session.commit()
    return quiz.public_id


# ---------------------------------------------------------------------------
# Quiz Retrieval Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_quiz(client: AsyncClient, quiz_id: str):
    resp = await client.get(f"/api/v1/quizzes/{quiz_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert data["id"] == quiz_id
    assert data["title"] == "Test Quiz"
    assert data["status"] == "published"
    assert data["question_count"] == 3
    assert data["passing_score"] == 60.0


@pytest.mark.asyncio
async def test_get_quiz_not_found(client: AsyncClient):
    resp = await client.get("/api/v1/quizzes/nonexistent_quiz_123")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Attempt Lifecycle Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_attempt(client: AsyncClient, quiz_id: str):
    resp = await client.post(f"/api/v1/quizzes/{quiz_id}/attempts")
    assert resp.status_code == 201
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert data["status"] == "in_progress"
    assert data["attempt_number"] == 1
    assert len(data["questions"]) == 3
    assert data["quiz_id"] == quiz_id

    # Verify questions don't expose answers
    for q in data["questions"]:
        for opt in q["options"]:
            assert "is_correct" not in opt


@pytest.mark.asyncio
async def test_start_attempt_returns_active_if_exists(client: AsyncClient, quiz_id: str):
    resp1 = await client.post(f"/api/v1/quizzes/{quiz_id}/attempts")
    assert resp1.status_code == 201
    attempt_id_1 = resp1.json()["data"]["attempt_id"]

    resp2 = await client.post(f"/api/v1/quizzes/{quiz_id}/attempts")
    assert resp2.status_code == 201
    attempt_id_2 = resp2.json()["data"]["attempt_id"]

    # Should return the same attempt
    assert attempt_id_1 == attempt_id_2


@pytest.mark.asyncio
async def test_submit_single_answer(client: AsyncClient, quiz_id: str):
    # Start attempt
    resp = await client.post(f"/api/v1/quizzes/{quiz_id}/attempts")
    data = resp.json()["data"]
    attempt_id = data["attempt_id"]

    # Get the first question's options
    q1 = data["questions"][0]
    correct_option_id = q1["options"][1]["id"]  # "4" is the correct answer

    # Submit answer
    resp = await client.post(
        f"/api/v1/quizzes/{quiz_id}/attempts/{attempt_id}/answers/{q1['id']}",
        json={"option_ids": [correct_option_id]},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert resp.json()["data"]["saved"] is True


@pytest.mark.asyncio
async def test_submit_quiz_all_correct(client: AsyncClient, quiz_id: str):
    # Start attempt
    resp = await client.post(f"/api/v1/quizzes/{quiz_id}/attempts")
    data = resp.json()["data"]
    attempt_id = data["attempt_id"]
    questions = data["questions"]

    # Build correct answers
    answers = []
    for q in questions:
        if q["question_type"] == "multiple_choice":
            correct_opt = next(o for o in q["options"] if o["position"] == 2)
            answers.append({"question_id": q["id"], "option_ids": [correct_opt["id"]]})
        elif q["question_type"] == "true_false":
            correct_opt = next(o for o in q["options"] if o["position"] == 1)
            answers.append({"question_id": q["id"], "option_ids": [correct_opt["id"]]})
        elif q["question_type"] == "multiple_select":
            correct_opts = [o for o in q["options"] if o["position"] in (1, 2, 4)]
            answers.append({"question_id": q["id"], "option_ids": [o["id"] for o in correct_opts]})

    # Submit
    resp = await client.post(
        f"/api/v1/quizzes/{quiz_id}/attempts/{attempt_id}/submit",
        json={"answers": answers, "time_spent_seconds": 120},
    )
    assert resp.status_code == 200
    result = resp.json()["data"]
    assert result["status"] == "completed"
    assert result["score"] == 4.0  # 1 + 1 + 2
    assert result["max_score"] == 4.0
    assert result["percent_score"] == 100.0
    assert result["passed"] is True
    assert result["completed_at"] is not None
    assert len(result["question_feedback"]) == 3

    # All correct
    for fb in result["question_feedback"]:
        assert fb["is_correct"] is True


@pytest.mark.asyncio
async def test_submit_quiz_returns_lesson_public_id_deeplink(
    client: AsyncClient, quiz_id: str, db_session: AsyncSession
):
    """NG-1: submit_quiz must return the bound lesson's *public* id so the
    quiz-result CTA can deep-link to a real player route (never an internal
    UUID). The public id must also be stained onto the recommendations'
    next_action and every action so the UI has a usable destination."""
    from app.models.generated_lesson import GeneratedLesson
    from app.models.quiz import Quiz

    q = (
        await db_session.execute(select(Quiz).where(Quiz.public_id == quiz_id))
    ).scalar_one()
    lesson = GeneratedLesson(
        presentation_id=q.presentation_id,
        user_id=TEST_USER_ID,
        mode="slide",
        status="ready",
        title="NG-1 Deeplink Lesson",
        latest_version=1,
    )
    db_session.add(lesson)
    await db_session.flush()
    q.lesson_id = lesson.id
    await db_session.commit()

    # Start attempt
    resp = await client.post(f"/api/v1/quizzes/{quiz_id}/attempts")
    data = resp.json()["data"]
    attempt_id = data["attempt_id"]
    questions = data["questions"]

    answers = []
    for question in questions:
        if question["question_type"] == "multiple_choice":
            opt = next(o for o in question["options"] if o["position"] == 2)
            answers.append({"question_id": question["id"], "option_ids": [opt["id"]]})
        elif question["question_type"] == "true_false":
            opt = next(o for o in question["options"] if o["position"] == 1)
            answers.append({"question_id": question["id"], "option_ids": [opt["id"]]})
        elif question["question_type"] == "multiple_select":
            opts = [o for o in question["options"] if o["position"] in (1, 2, 4)]
            answers.append({"question_id": question["id"], "option_ids": [o["id"] for o in opts]})

    resp = await client.post(
        f"/api/v1/quizzes/{quiz_id}/attempts/{attempt_id}/submit",
        json={"answers": answers, "time_spent_seconds": 90},
    )
    assert resp.status_code == 200
    result = resp.json()["data"]

    # Top-level lesson_id is the *public* id, not the internal UUID.
    assert result["lesson_id"] == lesson.public_id
    assert result["lesson_id"] != str(lesson.id)

    # The same public id is stained onto next_action and every action.
    recs = result["recommendations"] or {}
    next_act = recs.get("next_action")
    assert next_act is not None
    assert next_act.get("metadata", {}).get("lesson_id") == lesson.public_id
    assert next_act["metadata"]["lesson_id"] == result["lesson_id"]
    for action in recs.get("actions", []) or []:
        assert action.get("metadata", {}).get("lesson_id") == lesson.public_id


@pytest.mark.asyncio
async def test_submit_quiz_returns_null_lesson_id_when_unbound(
    client: AsyncClient, quiz_id: str
):
    """NG-1 fallback: a quiz with no bound lesson yields lesson_id None so the
    frontend never renders a dead deep-link for a missing target."""
    resp = await client.post(f"/api/v1/quizzes/{quiz_id}/attempts")
    data = resp.json()["data"]
    attempt_id = data["attempt_id"]
    questions = data["questions"]

    answers = []
    for question in questions:
        if question["question_type"] == "multiple_choice":
            opt = next(o for o in question["options"] if o["position"] == 2)
            answers.append({"question_id": question["id"], "option_ids": [opt["id"]]})
        elif question["question_type"] == "true_false":
            opt = next(o for o in question["options"] if o["position"] == 1)
            answers.append({"question_id": question["id"], "option_ids": [opt["id"]]})
        elif question["question_type"] == "multiple_select":
            opts = [o for o in question["options"] if o["position"] in (1, 2, 4)]
            answers.append({"question_id": question["id"], "option_ids": [o["id"] for o in opts]})

    resp = await client.post(
        f"/api/v1/quizzes/{quiz_id}/attempts/{attempt_id}/submit",
        json={"answers": answers, "time_spent_seconds": 90},
    )
    assert resp.status_code == 200
    result = resp.json()["data"]
    assert result["lesson_id"] is None


@pytest.mark.asyncio
async def test_submit_quiz_partial_score(client: AsyncClient, quiz_id: str):
    resp = await client.post(f"/api/v1/quizzes/{quiz_id}/attempts")
    data = resp.json()["data"]
    attempt_id = data["attempt_id"]
    questions = data["questions"]

    # Answer first question correct, rest wrong
    q1 = questions[0]
    correct_opt = next(o for o in q1["options"] if o["position"] == 2)
    answers = [{"question_id": q1["id"], "option_ids": [correct_opt["id"]]}]

    for q in questions[1:]:
        if q["question_type"] == "true_false":
            wrong_opt = next(o for o in q["options"] if o["position"] == 2)
            answers.append({"question_id": q["id"], "option_ids": [wrong_opt["id"]]})
        elif q["question_type"] == "multiple_select":
            wrong_opts = [o for o in q["options"] if o["position"] in (3,)]
            answers.append({"question_id": q["id"], "option_ids": [o["id"] for o in wrong_opts]})

    resp = await client.post(
        f"/api/v1/quizzes/{quiz_id}/attempts/{attempt_id}/submit",
        json={"answers": answers, "time_spent_seconds": 60},
    )
    result = resp.json()["data"]
    assert result["status"] == "completed"
    assert result["score"] == 1.0  # Only question 1 correct
    assert result["max_score"] == 4.0
    assert result["percent_score"] == 25.0
    assert result["passed"] is False  # Passing score is 60%

    breakdown = result["score_breakdown"]
    assert breakdown["correct_count"] == 1
    assert breakdown["incorrect_count"] == 2


@pytest.mark.asyncio
async def test_submit_quiz_not_submittable_twice(client: AsyncClient, quiz_id: str):
    resp = await client.post(f"/api/v1/quizzes/{quiz_id}/attempts")
    attempt_id = resp.json()["data"]["attempt_id"]

    # Submit once
    resp = await client.post(
        f"/api/v1/quizzes/{quiz_id}/attempts/{attempt_id}/submit",
        json={"answers": [], "time_spent_seconds": 10},
    )
    assert resp.status_code == 200

    # Try to submit again
    resp = await client.post(
        f"/api/v1/quizzes/{quiz_id}/attempts/{attempt_id}/submit",
        json={"answers": [], "time_spent_seconds": 10},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_get_attempt_result(client: AsyncClient, quiz_id: str):
    # Start and submit
    resp = await client.post(f"/api/v1/quizzes/{quiz_id}/attempts")
    attempt_id = resp.json()["data"]["attempt_id"]

    await client.post(
        f"/api/v1/quizzes/{quiz_id}/attempts/{attempt_id}/submit",
        json={"answers": [], "time_spent_seconds": 30},
    )

    # Get result
    resp = await client.get(f"/api/v1/quizzes/{quiz_id}/attempts/{attempt_id}")
    assert resp.status_code == 200
    result = resp.json()["data"]
    assert result["status"] == "completed"
    assert result["score_breakdown"] is not None


@pytest.mark.asyncio
async def test_list_attempts(client: AsyncClient, quiz_id: str):
    # Start an attempt
    await client.post(f"/api/v1/quizzes/{quiz_id}/attempts")

    # List
    resp = await client.get(f"/api/v1/quizzes/{quiz_id}/attempts")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) >= 1
    assert data[0]["quiz_id"] == quiz_id


@pytest.mark.asyncio
async def test_max_attempts_limit(client: AsyncClient, quiz_id: str):
    """Submit 3 attempts (the max) then verify the 4th is rejected."""
    for _ in range(3):
        resp = await client.post(f"/api/v1/quizzes/{quiz_id}/attempts")
        assert resp.status_code == 201
        attempt_id = resp.json()["data"]["attempt_id"]
        resp = await client.post(
            f"/api/v1/quizzes/{quiz_id}/attempts/{attempt_id}/submit",
            json={"answers": []},
        )
        assert resp.status_code == 200

    # 4th attempt should fail
    resp = await client.post(f"/api/v1/quizzes/{quiz_id}/attempts")
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Ownership / Authorization Tests
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def other_user_quiz_id(
    db_session: AsyncSession,
    other_user_id: uuid.UUID,
) -> str:
    """Create a quiz owned by a different user (via their own presentation)."""
    from sqlalchemy import select as sa_select

    from app.models.presentation import Presentation
    from app.models.quiz import Quiz
    from app.models.quiz_version import QuizVersion

    p = Presentation(
        title="Other User Presentation",
        owner_id=other_user_id,
        status="published",
        slide_count=1,
    )
    db_session.add(p)
    await db_session.flush()
    await db_session.refresh(p)

    quiz = Quiz(
        presentation_id=p.id,
        user_id=other_user_id,
        status="published",
        mode="practice",
        title="Other User Quiz",
        description="Owned by another user",
        difficulty="beginner",
        question_count=1,
        max_attempts_per_user=3,
        passing_score=60.0,
        shuffle_questions=False,
        shuffle_options=False,
        show_feedback_after=True,
        latest_version=1,
        published_version=1,
    )
    db_session.add(quiz)
    await db_session.flush()

    version = QuizVersion(
        quiz_id=quiz.id,
        version=1,
        status="published",
        title="Other User Quiz v1",
    )
    db_session.add(version)
    await db_session.flush()
    await db_session.commit()
    return quiz.public_id


@pytest_asyncio.fixture
async def other_user_id(db_session: AsyncSession) -> uuid.UUID:
    """Create a second distinct test user and return their UUID."""
    from sqlalchemy import select as sa_select

    from app.core.security import hash_password
    from app.models.user import User

    uid = uuid.UUID("00000000-0000-0000-0000-000000000003")
    existing = await db_session.execute(sa_select(User).where(User.id == uid))
    if existing.scalar_one_or_none() is None:
        user = User(
            id=uid,
            email="other@example.com",
            name="Other User",
            password_hash=hash_password("testpassword123"),
        )
        db_session.add(user)
        await db_session.flush()
    await db_session.commit()
    return uid


@pytest.fixture
def as_other_user(other_user_id: uuid.UUID):
    """Run a test block authenticated as a different user via get_current_user."""
    from app.core.dependencies import get_current_user

    class _OtherFakeUser:
        def __init__(self) -> None:
            self.id = other_user_id
            self.email = "other@example.com"
            self.name = "Other User"

    def _install():
        async def _fake_other():
            return _OtherFakeUser()
        app.dependency_overrides[get_current_user] = _fake_other

    def _restore():
        app.dependency_overrides.pop(get_current_user, None)

    return _install, _restore


@pytest.mark.asyncio
async def test_other_user_denied_quiz_idor(client: AsyncClient, quiz_id: str, as_other_user):
    """IDOR: a different authenticated user cannot read another owner's quiz."""
    install, restore = as_other_user
    install()
    try:
        resp = await client.get(f"/api/v1/quizzes/{quiz_id}")
        assert resp.status_code == 404
    finally:
        restore()


@pytest.mark.asyncio
async def test_other_user_denied_start_attempt(
    client: AsyncClient, quiz_id: str, as_other_user
):
    """IDOR: a different user cannot create an attempt on another owner's quiz."""
    install, restore = as_other_user
    install()
    try:
        resp = await client.post(f"/api/v1/quizzes/{quiz_id}/attempts")
        assert resp.status_code == 404
    finally:
        restore()


@pytest.mark.asyncio
async def test_other_user_denied_list_attempts(
    client: AsyncClient, quiz_id: str, as_other_user
):
    """IDOR: a different user cannot list another owner's quiz attempts."""
    install, restore = as_other_user
    install()
    try:
        resp = await client.get(f"/api/v1/quizzes/{quiz_id}/attempts")
        assert resp.status_code == 404
    finally:
        restore()


@pytest.mark.asyncio
async def test_owner_can_access_own_quiz(client: AsyncClient, quiz_id: str):
    """The owner can read their own quiz."""
    resp = await client.get(f"/api/v1/quizzes/{quiz_id}")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_owner_can_start_attempt(client: AsyncClient, quiz_id: str):
    """The owner can start an attempt on their own quiz."""
    resp = await client.post(f"/api/v1/quizzes/{quiz_id}/attempts")
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_owner_can_list_attempts(client: AsyncClient, quiz_id: str):
    """The owner can list attempts on their own quiz."""
    await client.post(f"/api/v1/quizzes/{quiz_id}/attempts")
    resp = await client.get(f"/api/v1/quizzes/{quiz_id}/attempts")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_other_user_denied_other_quiz(client: AsyncClient, other_user_quiz_id: str):
    """The current user cannot read a quiz owned by someone else."""
    resp = await client.get(f"/api/v1/quizzes/{other_user_quiz_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_orphaned_quiz_safely_denied(
    client: AsyncClient, db_session: AsyncSession
):
    """A quiz whose presentation has a null owner is safely denied for everyone."""
    from app.models.presentation import Presentation
    from app.models.quiz import Quiz

    p = Presentation(
        title="Orphaned Presentation",
        owner_id=None,
        status="published",
        slide_count=1,
    )
    db_session.add(p)
    await db_session.flush()
    await db_session.refresh(p)

    quiz = Quiz(
        presentation_id=p.id,
        user_id=None,
        status="published",
        mode="practice",
        title="Orphaned Quiz",
        max_attempts_per_user=3,
        question_count=0,
        latest_version=1,
        published_version=1,
    )
    db_session.add(quiz)
    await db_session.flush()
    await db_session.commit()
    await db_session.refresh(quiz)

    resp = await client.get(f"/api/v1/quizzes/{quiz.public_id}")
    assert resp.status_code == 404

    resp = await client.post(f"/api/v1/quizzes/{quiz.public_id}/attempts")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_attempt_ownership_isolation(client: AsyncClient, quiz_id: str, as_other_user):
    """User B cannot get User A's attempt results via a different attempt_id."""
    # User A creates an attempt
    resp = await client.post(f"/api/v1/quizzes/{quiz_id}/attempts")
    attempt_id = resp.json()["data"]["attempt_id"]

    # Submit it
    await client.post(
        f"/api/v1/quizzes/{quiz_id}/attempts/{attempt_id}/submit",
        json={"answers": []},
    )

    # User B tries to read User A's attempt -> denied (404)
    install, restore = as_other_user
    install()
    try:
        resp = await client.get(f"/api/v1/quizzes/{quiz_id}/attempts/{attempt_id}")
        assert resp.status_code == 404
    finally:
        restore()


@pytest.mark.asyncio
async def test_unauthenticated_access_denied(client: AsyncClient, quiz_id: str):
    """Without auth, all endpoints should return 401."""
    from app.core.dependencies import get_current_user

    # Temporarily remove auth override
    app.dependency_overrides.pop(get_current_user, None)
    try:
        resp = await client.get(f"/api/v1/quizzes/{quiz_id}")
        assert resp.status_code == 401

        resp = await client.post(f"/api/v1/quizzes/{quiz_id}/attempts")
        assert resp.status_code == 401
    finally:
        # Restore auth override
        async def _fake_user():
            return _FakeUser()
        app.dependency_overrides[get_current_user] = _fake_user


# ---------------------------------------------------------------------------
# Edge Case Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_empty_quiz(client: AsyncClient, quiz_id: str):
    """Submit with empty answers list should still work (all unanswered)."""
    resp = await client.post(f"/api/v1/quizzes/{quiz_id}/attempts")
    attempt_id = resp.json()["data"]["attempt_id"]

    resp = await client.post(
        f"/api/v1/quizzes/{quiz_id}/attempts/{attempt_id}/submit",
        json={"answers": [], "time_spent_seconds": 0},
    )
    assert resp.status_code == 200
    result = resp.json()["data"]
    assert result["status"] == "completed"
    assert result["percent_score"] == 0.0
    assert result["passed"] is False


@pytest.mark.asyncio
async def test_start_attempt_on_nonexistent_quiz(client: AsyncClient):
    resp = await client.post("/api/v1/quizzes/nonexistent/attempts")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_submit_answer_on_nonexistent_attempt(client: AsyncClient, quiz_id: str):
    resp = await client.post(
        f"/api/v1/quizzes/{quiz_id}/attempts/nonexistent/answers/q_fake",
        json={"option_ids": ["fake"]},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_submit_answer_replaces_previous(client: AsyncClient, quiz_id: str):
    """Answering the same question twice should update the answer."""
    resp = await client.post(f"/api/v1/quizzes/{quiz_id}/attempts")
    data = resp.json()["data"]
    attempt_id = data["attempt_id"]
    q1 = data["questions"][0]

    # First answer
    opt_a = q1["options"][0]["id"]
    resp = await client.post(
        f"/api/v1/quizzes/{quiz_id}/attempts/{attempt_id}/answers/{q1['id']}",
        json={"option_ids": [opt_a]},
    )
    assert resp.status_code == 200

    # Second answer (different option)
    opt_c = q1["options"][2]["id"]
    resp = await client.post(
        f"/api/v1/quizzes/{quiz_id}/attempts/{attempt_id}/answers/{q1['id']}",
        json={"option_ids": [opt_c]},
    )
    assert resp.status_code == 200

    # Submit and verify the last answer is used
    resp = await client.post(
        f"/api/v1/quizzes/{quiz_id}/attempts/{attempt_id}/submit",
        json={"answers": []},
    )
    result = resp.json()["data"]
    # Question 1 should be incorrect (answered with wrong option)
    q1_fb = next(f for f in result["question_feedback"] if f["position"] == 1)
    assert q1_fb["is_correct"] is False


@pytest.mark.asyncio
async def test_time_spent_persists(client: AsyncClient, quiz_id: str):
    resp = await client.post(f"/api/v1/quizzes/{quiz_id}/attempts")
    attempt_id = resp.json()["data"]["attempt_id"]

    resp = await client.post(
        f"/api/v1/quizzes/{quiz_id}/attempts/{attempt_id}/submit",
        json={"answers": [], "time_spent_seconds": 300},
    )
    assert resp.json()["data"]["time_spent_seconds"] == 300


# ---------------------------------------------------------------------------
# Service Unit Tests (without HTTP)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_service_submit_answer(db_session: AsyncSession, quiz_id: str):
    from app.database.unit_of_work import UnitOfWork
    from app.services.quiz_attempt_service import QuizAttemptService

    async with UnitOfWork(session=db_session) as uow:
        service = QuizAttemptService(uow)
        result = await service.start_attempt(quiz_id, TEST_USER_ID)
        attempt_id = result["attempt_id"]
        q1_id = result["questions"][0]["id"]
        opt_id = result["questions"][0]["options"][1]["id"]

        answer_result = await service.submit_answer(
            quiz_id, attempt_id, q1_id, TEST_USER_ID,
            option_ids=[opt_id],
        )
        assert answer_result["saved"] is True


@pytest.mark.asyncio
async def test_service_evaluate_correct_answer(db_session: AsyncSession, quiz_id: str):
    from app.database.unit_of_work import UnitOfWork
    from app.services.quiz_attempt_service import QuizAttemptService

    async with UnitOfWork(session=db_session) as uow:
        service = QuizAttemptService(uow)
        result = await service.start_attempt(quiz_id, TEST_USER_ID)
        attempt_id = result["attempt_id"]

        # Build correct answers for all questions
        answers = []
        for q in result["questions"]:
            if q["question_type"] == "multiple_choice":
                correct_opt = next(o for o in q["options"] if o["position"] == 2)
                answers.append({"question_id": q["id"], "option_ids": [correct_opt["id"]]})
            elif q["question_type"] == "true_false":
                correct_opt = next(o for o in q["options"] if o["position"] == 1)
                answers.append({"question_id": q["id"], "option_ids": [correct_opt["id"]]})
            elif q["question_type"] == "multiple_select":
                correct_opts = [o for o in q["options"] if o["position"] in (1, 2, 4)]
                answers.append({"question_id": q["id"], "option_ids": [o["id"] for o in correct_opts]})

        submit_result = await service.submit_quiz(
            quiz_id, attempt_id, TEST_USER_ID,
            answers=answers, time_spent_seconds=90,
        )
        assert submit_result["status"] == "completed"
        assert submit_result["percent_score"] == 100.0
        assert submit_result["passed"] is True
