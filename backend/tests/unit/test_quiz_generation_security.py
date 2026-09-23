"""B1 — quiz-generation IDOR authorization-boundary regression tests.

Security requirement (AUTHENTICATION != AUTHORIZATION): the quiz-generation
endpoint must refuse to generate a quiz from a lesson the authenticated user
does not own. Ownership is enforced through the lesson's parent presentation
owner (the single top-level ownership unit) OR the lesson's direct
``user_id``, 404-equalized exactly like the repository's established
ownership helpers (``assert_quiz_ownership`` / ``_get_owned_lesson``): a
missing lesson, an orphaned/soft-deleted presentation, and a non-owner lesson
all produce the same ``Lesson not found`` response so no cross-user existence
leak occurs.

These tests are deliberately discriminating: against the pre-fix
implementation the cross-user case succeeded (a quiz was generated and
persisted from another user's lesson through the real AI path), so the
denial assertions below fail on the vulnerable code.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.generated_block import GeneratedBlock
from app.models.generated_lesson import GeneratedLesson
from app.models.generated_lesson_version import GeneratedLessonVersion
from app.models.presentation import Presentation
from app.models.quiz import Quiz
from app.services.quiz_generation_service import QuizGenerationService
from tests.conftest import TEST_USER_ID, _FakeUser

USER_B_ID = uuid.UUID("00000000-0000-0000-0000-00000000000b")

GENERATED_QUIZ_JSON = json.dumps(
    {
        "title": "Generated Security Quiz",
        "description": "Knowledge check for the lesson",
        "difficulty": "intermediate",
        "passing_score": 70.0,
        "shuffle_questions": True,
        "shuffle_options": True,
        "show_feedback_after": True,
        "max_attempts_per_user": 3,
        "questions": [
            {
                "id": "q1",
                "type": "multiple_choice",
                "stem": "What is 2 + 2?",
                "difficulty": "beginner",
                "bloom_level": "remember",
                "points": 1,
                "options": [
                    {"id": "o1", "text": "3", "is_correct": False},
                    {"id": "o2", "text": "4", "is_correct": True},
                    {"id": "o3", "text": "5", "is_correct": False},
                ],
                "answer_key": {
                    "answer_type": "multiple_choice",
                    "correct_option_idxs": [1],
                },
                "explanation": "2 + 2 equals 4.",
            },
            {
                "id": "q2",
                "type": "true_false",
                "stem": "Photosynthesis uses sunlight.",
                "difficulty": "beginner",
                "bloom_level": "remember",
                "points": 1,
                "options": [
                    {"id": "o4", "text": "True", "is_correct": True},
                    {"id": "o5", "text": "False", "is_correct": False},
                ],
                "answer_key": {
                    "answer_type": "true_false",
                    "correct_option_idxs": [0],
                    "value": True,
                },
                "explanation": "Photosynthesis requires light energy.",
            },
        ],
    }
)


async def _fake_call_ai(self, prompt: str) -> str:  # noqa: ARG001
    """Deterministic stand-in for the AI call so tests exercise persistence."""
    return GENERATED_QUIZ_JSON


async def _seed_lesson(
    session: AsyncSession,
    *,
    presentation_owner: uuid.UUID | None = TEST_USER_ID,
    lesson_user_id: uuid.UUID | None = TEST_USER_ID,
    presentation_deleted: bool = False,
) -> dict:
    """Create a presentation + lesson + version + block and return ids."""
    pres = Presentation(
        title="Security Test Deck",
        owner_id=presentation_owner,
        status="published",
        slide_count=3,
    )
    session.add(pres)
    await session.flush()
    if presentation_deleted:
        pres.deleted_at = datetime.now(UTC)

    lesson = GeneratedLesson(
        public_id=f"lesson_{uuid.uuid4().hex[:16]}",
        presentation_id=pres.id,
        user_id=lesson_user_id,
        mode="detailed",
        status="ready",
        title="Owned Lesson",
        latest_version=1,
    )
    session.add(lesson)
    await session.flush()

    version = GeneratedLessonVersion(
        public_id=f"lessver_{uuid.uuid4().hex[:16]}",
        lesson_id=lesson.id,
        version=1,
        status="succeeded",
    )
    session.add(version)
    await session.flush()

    block = GeneratedBlock(
        public_id=f"gblk_{uuid.uuid4().hex[:16]}",
        lesson_version_id=version.id,
        block_type="paragraph",
        position=0,
        heading="Photosynthesis",
        content="Photosynthesis converts light energy into chemical energy.",
    )
    session.add(block)
    await session.commit()
    await session.refresh(lesson)
    return {
        "lesson_public_id": lesson.public_id,
        "lesson_id": lesson.id,
        "presentation_public_id": pres.public_id,
        "presentation_id": pres.id,
    }


@pytest_asyncio.fixture
async def owned_lesson(db_session: AsyncSession) -> dict:
    """Lesson A owned by the authenticated test user."""
    return await _seed_lesson(db_session)


@pytest_asyncio.fixture
async def user_b(db_session: AsyncSession) -> uuid.UUID:
    """Ensure a distinct user B row exists (the Quiz FK references users)."""
    from app.core.security import hash_password
    from app.models.user import User

    existing = await db_session.execute(select(User).where(User.id == USER_B_ID))
    if existing.scalar_one_or_none() is None:
        db_session.add(
            User(
                id=USER_B_ID,
                email="user_b@test.com",
                name="User B",
                password_hash=hash_password("password123"),
            )
        )
        await db_session.commit()
    return USER_B_ID


async def _count_quizzes_for_lesson(db_session: AsyncSession, lesson_id: uuid.UUID) -> int:
    return await db_session.scalar(
        select(func.count())
        .select_from(Quiz)
        .where(Quiz.lesson_id == lesson_id)
    )


# ── HTTP route: owner → success ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_owner_generates_quiz_from_own_lesson(
    client: AsyncClient,
    owned_lesson: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Owner (A) generating a quiz from lesson A succeeds (201)."""
    monkeypatch.setattr(QuizGenerationService, "_call_ai", _fake_call_ai)
    resp = await client.post(
        "/api/v1/quizzes/generate",
        json={"lesson_id": owned_lesson["lesson_public_id"], "num_questions": 2},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert data["question_count"] == 2
    assert data["quiz_id"]
    assert data["status"] == "ready"


@pytest.mark.asyncio
async def test_owner_generated_quiz_bound_to_owner(
    client: AsyncClient,
    owned_lesson: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The generated quiz is bound to the owner's presentation/lesson/user."""
    monkeypatch.setattr(QuizGenerationService, "_call_ai", _fake_call_ai)
    resp = await client.post(
        "/api/v1/quizzes/generate",
        json={"lesson_id": owned_lesson["lesson_public_id"]},
    )
    assert resp.status_code == 201
    quiz_id = resp.json()["data"]["quiz_id"]

    quiz = (
        await db_session.execute(select(Quiz).where(Quiz.public_id == quiz_id))
    ).scalar_one()
    assert quiz.presentation_id == owned_lesson["presentation_id"]
    assert quiz.lesson_id == owned_lesson["lesson_id"]
    assert quiz.user_id == TEST_USER_ID


# ── HTTP route: cross-user → authorization failure ───────────────────────────


@pytest.mark.asyncio
async def test_cross_user_cannot_generate_quiz_from_other_lesson(
    client: AsyncClient,
    db_session: AsyncSession,
    owned_lesson: dict,
    user_b: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """User B calling generation against lesson A is denied with 404."""
    from app.core.dependencies import get_current_user
    from app.main import app

    class _UserB:
        id = user_b
        email = "user_b@test.com"
        name = "User B"

    async def _fake_user_b():
        return _UserB()

    app.dependency_overrides[get_current_user] = _fake_user_b
    monkeypatch.setattr(QuizGenerationService, "_call_ai", _fake_call_ai)
    try:
        resp = await client.post(
            "/api/v1/quizzes/generate",
            json={"lesson_id": owned_lesson["lesson_public_id"]},
        )
        assert resp.status_code == 404
        body = resp.json()
        assert body["success"] is False
        assert body["error"]["code"] == "NOT_FOUND"
        assert body["error"]["message"] == "Lesson not found"
        assert (await _count_quizzes_for_lesson(db_session, owned_lesson["lesson_id"])) == 0
    finally:
        async def _restore_test_user():
            return _FakeUser()

        app.dependency_overrides[get_current_user] = _restore_test_user


@pytest.mark.asyncio
async def test_cross_user_error_identical_to_missing_lesson(
    client: AsyncClient,
    owned_lesson: dict,
    user_b: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-owner denial is indistinguishable from a missing lesson (no leak)."""
    from app.core.dependencies import get_current_user
    from app.main import app

    class _UserB:
        id = user_b
        email = "user_b@test.com"
        name = "User B"

    async def _fake_user_b():
        return _UserB()

    monkeypatch.setattr(QuizGenerationService, "_call_ai", _fake_call_ai)
    cross_user_resp = None
    app.dependency_overrides[get_current_user] = _fake_user_b
    try:
        cross_user_resp = await client.post(
            "/api/v1/quizzes/generate",
            json={"lesson_id": owned_lesson["lesson_public_id"]},
        )
    finally:
        async def _restore_test_user():
            return _FakeUser()

        app.dependency_overrides[get_current_user] = _restore_test_user

    missing_resp = await client.post(
        "/api/v1/quizzes/generate",
        json={"lesson_id": "lesson_does_not_exist"},
    )

    assert cross_user_resp.status_code == 404
    assert missing_resp.status_code == 404
    cross_user_err = cross_user_resp.json()["error"]
    missing_err = missing_resp.json()["error"]
    assert cross_user_err["code"] == missing_err["code"] == "NOT_FOUND"
    assert cross_user_err["message"] == missing_err["message"] == "Lesson not found"


@pytest.mark.asyncio
async def test_missing_lesson_returns_404(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nonexistent public_id follows the repo's 404 equalization convention."""
    monkeypatch.setattr(QuizGenerationService, "_call_ai", _fake_call_ai)
    resp = await client.post(
        "/api/v1/quizzes/generate",
        json={"lesson_id": "lesson_does_not_exist"},
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["success"] is False
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["message"] == "Lesson not found"


@pytest.mark.asyncio
async def test_orphaned_lesson_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A lesson whose presentation has no owner is denied for everyone."""
    orphaned = await _seed_lesson(
        db_session, presentation_owner=None, lesson_user_id=None
    )
    monkeypatch.setattr(QuizGenerationService, "_call_ai", _fake_call_ai)
    resp = await client.post(
        "/api/v1/quizzes/generate",
        json={"lesson_id": orphaned["lesson_public_id"]},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["message"] == "Lesson not found"


@pytest.mark.asyncio
async def test_deleted_presentation_lesson_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A lesson owned only via a soft-deleted presentation is denied."""
    deleted_lesson = await _seed_lesson(
        db_session, presentation_deleted=True, lesson_user_id=None
    )
    monkeypatch.setattr(QuizGenerationService, "_call_ai", _fake_call_ai)
    resp = await client.post(
        "/api/v1/quizzes/generate",
        json={"lesson_id": deleted_lesson["lesson_public_id"]},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["message"] == "Lesson not found"


# ── Service boundary (the authoritative security layer) ──────────────────────


@pytest.mark.asyncio
async def test_service_allows_owner(
    db_session: AsyncSession,
    owned_lesson: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Service-level: the owner can still generate a quiz."""
    from app.database.unit_of_work import UnitOfWork

    monkeypatch.setattr(QuizGenerationService, "_call_ai", _fake_call_ai)
    async with UnitOfWork(session=db_session) as uow:
        service = QuizGenerationService(uow)
        result = await service.generate_quiz(
            user_id=TEST_USER_ID,
            lesson_public_id=owned_lesson["lesson_public_id"],
        )
    assert result["quiz_id"]
    assert result["question_count"] == 2
    assert result["status"] == "ready"


@pytest.mark.asyncio
async def test_service_rejects_cross_user_lesson(
    db_session: AsyncSession,
    owned_lesson: dict,
    user_b: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Service-level: a different owner cannot generate from lesson A."""
    from app.database.unit_of_work import UnitOfWork

    monkeypatch.setattr(QuizGenerationService, "_call_ai", _fake_call_ai)
    async with UnitOfWork(session=db_session) as uow:
        service = QuizGenerationService(uow)
        with pytest.raises(NotFoundError) as excinfo:
            await service.generate_quiz(
                user_id=user_b,
                lesson_public_id=owned_lesson["lesson_public_id"],
            )
        assert excinfo.value.status_code == 404
        assert excinfo.value.message == "Lesson not found"

    assert (await _count_quizzes_for_lesson(db_session, owned_lesson["lesson_id"])) == 0


@pytest.mark.asyncio
async def test_service_rejects_missing_lesson(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Service-level: a nonexistent lesson public_id is 404-equalized."""
    from app.database.unit_of_work import UnitOfWork

    monkeypatch.setattr(QuizGenerationService, "_call_ai", _fake_call_ai)
    async with UnitOfWork(session=db_session) as uow:
        service = QuizGenerationService(uow)
        with pytest.raises(NotFoundError) as excinfo:
            await service.generate_quiz(
                user_id=TEST_USER_ID,
                lesson_public_id="lesson_does_not_exist",
            )
        assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_service_owner_via_lesson_user_id(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Legacy semantics: ownership via direct lesson.user_id is preserved."""
    from app.database.unit_of_work import UnitOfWork

    lesson = await _seed_lesson(
        db_session, presentation_owner=None, lesson_user_id=TEST_USER_ID
    )
    monkeypatch.setattr(QuizGenerationService, "_call_ai", _fake_call_ai)
    async with UnitOfWork(session=db_session) as uow:
        service = QuizGenerationService(uow)
        result = await service.generate_quiz(
            user_id=TEST_USER_ID,
            lesson_public_id=lesson["lesson_public_id"],
        )
    assert result["quiz_id"]
