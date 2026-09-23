"""B4 Tutor retention security / ownership-isolation tests.

B4 finding: ``MasteryTutorService.enforce_retention`` ran as a global,
learner-unscoped sweep at the top of ``GET /api/v1/tutor/sessions``. Any
authenticated user listing their own sessions also archived *every tenant's*
idle sessions and **hard-deleted the aged ``tutor_messages`` and soft-deleted
the aged ``tutor_conversations`` of all users** — a cross-user destructive
mutation with no ownership boundary (mission issue #5: "a route has
authentication but the underlying service lacks an ownership boundary").

These tests exercise the real ASGI app with JWT-based auth and prove the FIXED
boundary:

* User A seeds an idle active session + an expired conversation with messages.
* A's own read still enforces retention on her own rows (storage bound kept).
* User B (authenticated, unrelated) listing her own sessions leaves A's
  session, conversation and messages completely untouched — a user's read can
  never archive, soft-delete or hard-delete another learner's rows.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from fastapi import HTTPException, Request
from fastapi import status as http_status
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.core.dependencies import get_current_user
from app.core.security import create_access_token, decode_access_token
from app.main import app

pytestmark = pytest.mark.asyncio

_USER_A_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_USER_B_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

_TUTOR_TITLE = "B4 Retention test session"
_CONV_TITLE = "B4 Retention conversation"


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
            (_USER_A_ID, "tutor_ret_a@test.com", "Tutor Ret User A"),
            (_USER_B_ID, "tutor_ret_b@test.com", "Tutor Ret User B"),
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

    # Remove the shared autouse _FakeUser override and use real JWT auth.
    app.dependency_overrides.pop(get_current_user, None)

    user_map = {
        str(_USER_A_ID): _RealUser(_USER_A_ID, "tutor_ret_a@test.com", "Tutor Ret User A"),
        str(_USER_B_ID): _RealUser(_USER_B_ID, "tutor_ret_b@test.com", "Tutor Ret User B"),
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


_NOW = datetime(2026, 9, 4, tzinfo=UTC)


async def _seed_aged_tutor_rows(owner_id: uuid.UUID) -> dict[str, uuid.UUID]:
    """Seed an idle active session + an expired conversation with messages.

    ``updated_at`` is back-dated past both retention cutoffs
    (30 idle days / 90 conversation-cleanup days). Returns the three row ids.
    """
    from app.models.tutor_conversation import TutorConversation
    from app.models.tutor_message import TutorMessage
    from app.models.tutor_session import TutorSession
    from shared.constants import TutorConversationStatus, TutorSessionStatus
    from tests.conftest import TestSessionLocal

    until = _NOW - timedelta(days=100)

    async with TestSessionLocal() as session:
        tutor_session = TutorSession(
            user_id=owner_id,
            title=_TUTOR_TITLE,
            status=TutorSessionStatus.ACTIVE.value,
        )
        session.add(tutor_session)
        await session.flush()
        tutor_session.updated_at = until
        tutor_session.created_at = until
        await session.flush()

        conversation = TutorConversation(
            user_id=owner_id,
            session_id=tutor_session.id,
            session_public_id=tutor_session.public_id,
            title=_CONV_TITLE,
            status=TutorConversationStatus.ACTIVE.value,
        )
        session.add(conversation)
        await session.flush()
        conversation.updated_at = until
        conversation.created_at = until
        await session.flush()

        message_ids: list[uuid.UUID] = []
        for i in range(3):
            msg = TutorMessage(
                conversation_id=conversation.id,
                user_id=owner_id,
                role="user" if i % 2 == 0 else "assistant",
                content=f"B4 aged message {i}",
                status="completed",
            )
            session.add(msg)
            await session.flush()
            msg.updated_at = until
            msg.created_at = until
            await session.flush()
            message_ids.append(msg.id)

        await session.commit()
        return {
            "session_id": tutor_session.id,
            "conversation_id": conversation.id,
            "message_ids": message_ids,  # type: ignore[dict-item]
        }


async def _conversation_message_count(conversation_id: uuid.UUID) -> int:
    from app.models.tutor_message import TutorMessage
    from tests.conftest import TestSessionLocal

    async with TestSessionLocal() as session:
        result = await session.execute(
            select(func.count()).select_from(TutorMessage).where(
                TutorMessage.conversation_id == conversation_id
            )
        )
        return int(result.scalar_one() or 0)


async def _fetch_conversation(conversation_id: uuid.UUID):
    from app.models.tutor_conversation import TutorConversation
    from tests.conftest import TestSessionLocal

    async with TestSessionLocal() as session:
        result = await session.execute(
            select(TutorConversation).where(TutorConversation.id == conversation_id)
        )
        return result.scalar_one_or_none()


async def _fetch_session(session_id: uuid.UUID):
    from app.models.tutor_session import TutorSession
    from tests.conftest import TestSessionLocal

    async with TestSessionLocal() as session:
        result = await session.execute(
            select(TutorSession).where(TutorSession.id == session_id)
        )
        return result.scalar_one_or_none()


async def _cleanup_seeded_rows() -> None:
    from sqlalchemy import delete

    from app.models.tutor_conversation import TutorConversation
    from app.models.tutor_message import TutorMessage
    from app.models.tutor_session import TutorSession
    from tests.conftest import TestSessionLocal

    async with TestSessionLocal() as session:
        conv_ids = list(
            (await session.execute(select(TutorConversation.id).where(TutorConversation.title == _CONV_TITLE)))
            .scalars().all()
        )
        if conv_ids:
            await session.execute(
                delete(TutorMessage).where(TutorMessage.conversation_id.in_(conv_ids))
            )
            await session.execute(
                delete(TutorConversation).where(TutorConversation.id.in_(conv_ids))
            )
        await session.execute(
            delete(TutorSession).where(TutorSession.title == _TUTOR_TITLE)
        )
        await session.commit()


async def test_unauthenticated_tutor_sessions_rejected() -> None:
    async with await _make_client() as client:
        resp = await client.get("/api/v1/tutor/sessions")
        assert resp.status_code == 401


async def test_owner_read_cleans_own_aged_rows() -> None:
    """POST-FIX GUARANTEE: retention still bounds the OWNER's storage on their own read."""
    await _cleanup_seeded_rows()
    seeded = await _seed_aged_tutor_rows(_USER_A_ID)

    async with await _make_client() as client:
        resp = await client.get("/api/v1/tutor/sessions", headers=_headers(_USER_A_ID))
        assert resp.status_code == 200, resp.text

    conv = await _fetch_conversation(seeded["conversation_id"])
    assert conv is not None
    assert conv.deleted_at is not None
    assert await _conversation_message_count(seeded["conversation_id"]) == 0
    session = await _fetch_session(seeded["session_id"])
    assert session is not None
    assert session.status != "active"
    await _cleanup_seeded_rows()


async def test_cross_user_read_never_touches_victim_rows() -> None:
    """POST-FIX GUARANTEE: User B's read leaves User A's rows completely untouched."""
    await _cleanup_seeded_rows()
    seeded = await _seed_aged_tutor_rows(_USER_A_ID)

    async with await _make_client() as client:
        resp = await client.get("/api/v1/tutor/sessions", headers=_headers(_USER_B_ID))
        assert resp.status_code == 200, resp.text

    conv = await _fetch_conversation(seeded["conversation_id"])
    assert conv is not None
    assert conv.deleted_at is None
    assert await _conversation_message_count(seeded["conversation_id"]) == 3

    session = await _fetch_session(seeded["session_id"])
    assert session is not None
    assert session.status == "active"
    await _cleanup_seeded_rows()
