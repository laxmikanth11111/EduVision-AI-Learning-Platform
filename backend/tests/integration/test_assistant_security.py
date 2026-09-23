"""B2 — AI assistant lesson-context IDOR authorization-boundary regression tests.

Security requirement (AUTHENTICATION != AUTHORIZATION): the AI assistant
endpoints that anchor a session or conversation to a lesson (``POST
/api/v1/assistant/sessions`` and ``POST /api/v1/assistant/conversations``)
must refuse to bind a lesson the authenticated user does not own. Ownership is
enforced through the lesson's parent presentation owner (the single top-level
ownership unit) OR the lesson's direct ``user_id``, 404-equalized exactly like
the repository's established ownership helpers (``assert_quiz_ownership`` /
``_get_owned_lesson``): a missing lesson, an orphaned/soft-deleted
presentation, and a non-owner lesson all produce the same ``Lesson not found``
response so no cross-user existence leak occurs.

Risk: without the ownership check the assistant binds another user's lesson
into the caller's session; the message-send path then pulls the victim's
lesson content and source-material RAG chunks into the caller's AI context
(``_build_context_text`` / ``_retrieve_relevant_chunks``).

These tests are deliberately discriminating: against the pre-fix
implementation the cross-user binds succeeded (201) and stored the victim's
``lesson_id``, so the denial assertions below fail on the vulnerable code.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.assistant_conversation import AssistantConversation
from app.models.assistant_session import AssistantSession
from app.models.generated_block import GeneratedBlock
from app.models.generated_lesson import GeneratedLesson
from app.models.generated_lesson_version import GeneratedLessonVersion
from app.models.presentation import Presentation
from app.services.learning_assistant_service import LearningAssistantService
from tests.conftest import TEST_USER_ID, _FakeUser

USER_B_ID = uuid.UUID("00000000-0000-0000-0000-00000000000b")


async def _seed_lesson(
    session: AsyncSession,
    *,
    presentation_owner: uuid.UUID | None = TEST_USER_ID,
    lesson_user_id: uuid.UUID | None = TEST_USER_ID,
    presentation_deleted: bool = False,
    heading: str = "Assistant Context Heading",
    content: str = "Authorized lesson content owned by user A.",
) -> dict:
    """Create a presentation + lesson + version + block and return ids."""
    pres = Presentation(
        title="Assistant Security Deck",
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
        title="Assistant Owned Lesson",
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
        heading=heading,
        content=content,
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
    """Ensure a distinct user B row exists (mirrors the B1 fixtures)."""
    from app.core.security import hash_password
    from app.models.user import User

    existing = await db_session.execute(select(User).where(User.id == USER_B_ID))
    if existing.scalar_one_or_none() is None:
        db_session.add(
            User(
                id=USER_B_ID,
                email="assistant_b@test.com",
                name="User B",
                password_hash=hash_password("password123"),
            )
        )
        await db_session.commit()
    return USER_B_ID


async def _session_is_bound(db_session: AsyncSession, session_public_id: str) -> bool:
    row = await db_session.execute(
        select(AssistantSession).where(AssistantSession.public_id == session_public_id)
    )
    session = row.scalar_one_or_none()
    return bool(session and session.lesson_id is not None)


async def _conversation_is_bound(db_session: AsyncSession, conversation_public_id: str) -> bool:
    row = await db_session.execute(
        select(AssistantConversation).where(AssistantConversation.public_id == conversation_public_id)
    )
    conversation = row.scalar_one_or_none()
    return bool(conversation and conversation.lesson_id is not None)


class _UserB:
    id = USER_B_ID
    email = "assistant_b@test.com"
    name = "User B"


# ── HTTP route: owner → success ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_owner_creates_session_anchored_to_own_lesson(
    client: AsyncClient,
    owned_lesson: dict,
    db_session: AsyncSession,
) -> None:
    """Owner (A) can anchor a session to lesson A (201)."""
    resp = await client.post(
        "/api/v1/assistant/sessions",
        json={"lesson_id": owned_lesson["lesson_public_id"], "title": "A's session"},
    )
    assert resp.status_code == 201
    session_id = resp.json()["data"]["id"]
    assert await _session_is_bound(db_session, session_id)


@pytest.mark.asyncio
async def test_owner_creates_conversation_anchored_to_own_lesson(
    client: AsyncClient,
    owned_lesson: dict,
    db_session: AsyncSession,
) -> None:
    """Owner (A) can anchor a conversation to lesson A (201)."""
    resp = await client.post(
        "/api/v1/assistant/conversations",
        json={"lesson_id": owned_lesson["lesson_public_id"], "title": "A's conversation"},
    )
    assert resp.status_code == 201
    conversation_id = resp.json()["data"]["id"]
    assert await _conversation_is_bound(db_session, conversation_id)


# ── HTTP route: cross-user → authorization failure ───────────────────────────


@pytest.mark.asyncio
async def test_cross_user_cannot_anchor_session_to_other_lesson(
    client: AsyncClient,
    db_session: AsyncSession,
    owned_lesson: dict,
    user_b: uuid.UUID,  # noqa: ARG001
) -> None:
    """User B anchoring a session to lesson A is denied with 404."""
    from app.core.dependencies import get_current_user
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: _UserB()
    try:
        resp = await client.post(
            "/api/v1/assistant/sessions",
            json={"lesson_id": owned_lesson["lesson_public_id"], "title": "B's session"},
        )
        assert resp.status_code == 404
        body = resp.json()
        assert body["success"] is False
        assert body["error"]["code"] == "NOT_FOUND"
        assert body["error"]["message"] == "Lesson not found"
    finally:
        app.dependency_overrides[get_current_user] = lambda: _FakeUser()


@pytest.mark.asyncio
async def test_cross_user_cannot_anchor_conversation_to_other_lesson(
    client: AsyncClient,
    db_session: AsyncSession,
    owned_lesson: dict,
    user_b: uuid.UUID,  # noqa: ARG001
) -> None:
    """User B anchoring a conversation to lesson A is denied with 404."""
    from app.core.dependencies import get_current_user
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: _UserB()
    try:
        resp = await client.post(
            "/api/v1/assistant/conversations",
            json={"lesson_id": owned_lesson["lesson_public_id"], "title": "B's conversation"},
        )
        assert resp.status_code == 404
        body = resp.json()
        assert body["success"] is False
        assert body["error"]["code"] == "NOT_FOUND"
        assert body["error"]["message"] == "Lesson not found"
    finally:
        app.dependency_overrides[get_current_user] = lambda: _FakeUser()


@pytest.mark.asyncio
async def test_cross_user_error_identical_to_missing_lesson(
    client: AsyncClient,
    owned_lesson: dict,
    user_b: uuid.UUID,  # noqa: ARG001
) -> None:
    """Non-owner denial is indistinguishable from a missing lesson (no leak)."""
    from app.core.dependencies import get_current_user
    from app.main import app

    cross_user_resp = None
    app.dependency_overrides[get_current_user] = lambda: _UserB()
    try:
        cross_user_resp = await client.post(
            "/api/v1/assistant/conversations",
            json={"lesson_id": owned_lesson["lesson_public_id"], "title": "B's conversation"},
        )
    finally:
        app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    resp_user_b = cross_user_resp
    missing_resp = await client.post(
        "/api/v1/assistant/conversations",
        json={"lesson_id": "lesson_does_not_exist", "title": "missing"},
    )

    assert resp_user_b.status_code == 404
    assert missing_resp.status_code == 404
    cross_user_err = resp_user_b.json()["error"]
    missing_err = missing_resp.json()["error"]
    assert cross_user_err["code"] == missing_err["code"] == "NOT_FOUND"
    assert cross_user_err["message"] == missing_err["message"] == "Lesson not found"


@pytest.mark.asyncio
async def test_missing_lesson_returns_404(
    client: AsyncClient,
) -> None:
    """Nonexistent public_id follows the repo's 404 equalization convention."""
    resp = await client.post(
        "/api/v1/assistant/sessions",
        json={"lesson_id": "lesson_does_not_exist", "title": "missing"},
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
) -> None:
    """A lesson whose presentation has no owner is denied for everyone."""
    orphaned = await _seed_lesson(
        db_session, presentation_owner=None, lesson_user_id=None
    )
    resp = await client.post(
        "/api/v1/assistant/conversations",
        json={"lesson_id": orphaned["lesson_public_id"], "title": "orphaned"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["message"] == "Lesson not found"


@pytest.mark.asyncio
async def test_deleted_presentation_lesson_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """A lesson owned only via a soft-deleted presentation is denied."""
    deleted_lesson = await _seed_lesson(
        db_session, presentation_deleted=True, lesson_user_id=None
    )
    resp = await client.post(
        "/api/v1/assistant/conversations",
        json={"lesson_id": deleted_lesson["lesson_public_id"], "title": "deleted pres"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["message"] == "Lesson not found"


# ── Service boundary (the authoritative security layer) ──────────────────────


@pytest.mark.asyncio
async def test_service_allows_owner(
    db_session: AsyncSession,
    owned_lesson: dict,
) -> None:
    """Service-level: the owner can still anchor to their own lesson."""
    from app.database.unit_of_work import UnitOfWork

    async with UnitOfWork(session=db_session) as uow:
        service = LearningAssistantService(uow)
        lesson_id = await service._get_owned_lesson_id(  # noqa: SLF001
            TEST_USER_ID, owned_lesson["lesson_public_id"]
        )
    assert lesson_id == owned_lesson["lesson_id"]


@pytest.mark.asyncio
async def test_service_rejects_cross_user_lesson(
    db_session: AsyncSession,
    owned_lesson: dict,
    user_b: uuid.UUID,
) -> None:
    """Service-level: a different owner cannot anchor to lesson A."""
    from app.database.unit_of_work import UnitOfWork

    async with UnitOfWork(session=db_session) as uow:
        service = LearningAssistantService(uow)
        with pytest.raises(NotFoundError) as excinfo:
            await service._get_owned_lesson_id(  # noqa: SLF001
                user_b, owned_lesson["lesson_public_id"]
            )
    assert excinfo.value.status_code == 404
    assert excinfo.value.message == "Lesson not found"


@pytest.mark.asyncio
async def test_service_rejects_missing_lesson(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Service-level: a nonexistent lesson public_id is 404-equalized."""
    from app.database.unit_of_work import UnitOfWork

    async with UnitOfWork(session=db_session) as uow:
        service = LearningAssistantService(uow)
        with pytest.raises(NotFoundError) as excinfo:
            await service._get_owned_lesson_id(  # noqa: SLF001
                TEST_USER_ID, "lesson_does_not_exist"
            )
    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_service_owner_via_lesson_user_id(
    db_session: AsyncSession,
) -> None:
    """Legacy semantics: ownership via direct lesson.user_id is preserved."""
    from app.database.unit_of_work import UnitOfWork

    lesson = await _seed_lesson(
        db_session, presentation_owner=None, lesson_user_id=TEST_USER_ID
    )
    async with UnitOfWork(session=db_session) as uow:
        service = LearningAssistantService(uow)
        lesson_id = await service._get_owned_lesson_id(  # noqa: SLF001
            TEST_USER_ID, lesson["lesson_public_id"]
        )
    assert lesson_id == lesson["lesson_id"]


@pytest.mark.asyncio
async def test_service_none_lesson_id_passes_through(
    db_session: AsyncSession,
) -> None:
    """Unanchored sessions (no lesson_id) still create successfully."""
    from app.database.unit_of_work import UnitOfWork

    async with UnitOfWork(session=db_session) as uow:
        service = LearningAssistantService(uow)
        lesson_id = await service._get_owned_lesson_id(TEST_USER_ID, None)
    assert lesson_id is None
