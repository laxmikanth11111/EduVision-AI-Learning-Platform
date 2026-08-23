"""Integration tests for the AI learning assistant endpoints (Phase 4D.6).

Verifies the full session → conversation → message → summary cycle
through the HTTP API using real database persistence.

Uses the conftest autouse _override_get_current_user fixture (which returns
TEST_USER_ID for all requests). For isolation tests we temporarily override
the dependency with different user IDs.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app

pytestmark = pytest.mark.asyncio


class _FakeUser:
    def __init__(self, uid: uuid.UUID) -> None:
        self.id = uid
        self.email = f"{uid}@test.com"
        self.name = f"User {uid}"


async def _make_client() -> AsyncClient:
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test", follow_redirects=True)


def _set_user(uid: uuid.UUID) -> None:
    from app.core.dependencies import get_current_user

    async def _fake(_request=None):
        return _FakeUser(uid)

    app.dependency_overrides[get_current_user] = _fake


def _clear_user_override() -> None:
    from app.core.dependencies import get_current_user
    app.dependency_overrides.pop(get_current_user, None)


class TestAssistantSessions:
    async def test_create_and_get_session(self) -> None:
        async with await _make_client() as client:
            resp = await client.post(
                "/api/v1/assistant/sessions",
                json={"title": "My Study Session"},
            )
            assert resp.status_code == 201
            data = resp.json()["data"]
            assert data["id"].startswith("asess_")
            assert data["title"] == "My Study Session"
            assert data["status"] == "active"

            session_id = data["id"]

            resp = await client.get(f"/api/v1/assistant/sessions/{session_id}")
            assert resp.status_code == 200
            assert resp.json()["data"]["id"] == session_id

    async def test_list_sessions(self) -> None:
        async with await _make_client() as client:
            initial_resp = await client.get("/api/v1/assistant/sessions")
            initial_count = initial_resp.json()["pagination"]["total"]

            for i in range(3):
                resp = await client.post(
                    "/api/v1/assistant/sessions",
                    json={"title": f"Session {i}"},
                )
                assert resp.status_code == 201

            resp = await client.get("/api/v1/assistant/sessions")
            assert resp.status_code == 200
            assert resp.json()["pagination"]["total"] == initial_count + 3

    async def test_close_session(self) -> None:
        async with await _make_client() as client:
            resp = await client.post(
                "/api/v1/assistant/sessions",
                json={"title": "Close Me"},
            )
            session_id = resp.json()["data"]["id"]

            resp = await client.post(f"/api/v1/assistant/sessions/{session_id}/close")
            assert resp.status_code == 200
            assert resp.json()["data"]["status"] == "archived"

    async def test_user_isolation(self) -> None:
        user_a = uuid.uuid4()
        user_b = uuid.uuid4()

        async with await _make_client() as client:
            # Override auth to return User A
            _set_user(user_a)

            resp = await client.post(
                "/api/v1/assistant/sessions",
                json={"title": "User A Session"},
            )
            assert resp.status_code == 201
            session_id = resp.json()["data"]["id"]

            # Switch to User B
            _set_user(user_b)

            resp = await client.get(f"/api/v1/assistant/sessions/{session_id}")
            assert resp.status_code == 404

            _clear_user_override()


class TestAssistantConversations:
    async def test_create_conversation(self) -> None:
        async with await _make_client() as client:
            resp = await client.post(
                "/api/v1/assistant/sessions",
                json={"title": "Conv Test"},
            )
            session_id = resp.json()["data"]["id"]

            resp = await client.post(
                "/api/v1/assistant/conversations",
                json={"session_id": session_id, "title": "Test Conv"},
            )
            assert resp.status_code == 201
            data = resp.json()["data"]
            assert data["id"].startswith("aconv_")
            assert data["title"] == "Test Conv"

    async def test_list_conversations(self) -> None:
        async with await _make_client() as client:
            initial_resp = await client.get("/api/v1/assistant/conversations")
            initial_count = initial_resp.json()["pagination"]["total"]

            for i in range(2):
                resp = await client.post(
                    "/api/v1/assistant/conversations",
                    json={"title": f"Conv {i}"},
                )
                assert resp.status_code == 201

            resp = await client.get("/api/v1/assistant/conversations")
            assert resp.status_code == 200
            assert resp.json()["pagination"]["total"] == initial_count + 2


class TestAssistantMessages:
    async def test_send_and_receive_message(self) -> None:
        async with await _make_client() as client:
            resp = await client.post(
                "/api/v1/assistant/conversations",
                json={"title": "Message Test"},
            )
            conv_id = resp.json()["data"]["id"]

            resp = await client.post(
                f"/api/v1/assistant/conversations/{conv_id}/messages",
                json={"content": "What is machine learning?"},
            )
            assert resp.status_code == 201
            data = resp.json()["data"]
            assert data["user_message"] is not None
            assert data["user_message"]["content"] == "What is machine learning?"
            assert data["assistant_message"] is not None
            assert data["conversation_id"] == conv_id

    async def test_idempotent_message(self) -> None:
        async with await _make_client() as client:
            resp = await client.post(
                "/api/v1/assistant/conversations",
                json={"title": "Idempotent Test"},
            )
            conv_id = resp.json()["data"]["id"]

            payload = {"content": "Test idempotency", "client_message_id": "msg_123"}
            resp1 = await client.post(
                f"/api/v1/assistant/conversations/{conv_id}/messages",
                json=payload,
            )
            assert resp1.status_code == 201

            resp2 = await client.post(
                f"/api/v1/assistant/conversations/{conv_id}/messages",
                json=payload,
            )
            assert resp2.status_code == 201
            assert resp2.json()["data"]["user_message"]["content"] == "Test idempotency"

    async def test_list_messages(self) -> None:
        async with await _make_client() as client:
            resp = await client.post(
                "/api/v1/assistant/conversations",
                json={"title": "List Msg Test"},
            )
            conv_id = resp.json()["data"]["id"]

            await client.post(
                f"/api/v1/assistant/conversations/{conv_id}/messages",
                json={"content": "Hello"},
            )

            resp = await client.get(
                f"/api/v1/assistant/conversations/{conv_id}/messages",
            )
            assert resp.status_code == 200
            assert resp.json()["pagination"]["total"] >= 2  # user + assistant

    async def test_message_user_isolation(self) -> None:
        user_a = uuid.uuid4()
        user_b = uuid.uuid4()

        async with await _make_client() as client:
            _set_user(user_a)

            resp = await client.post(
                "/api/v1/assistant/conversations",
                json={"title": "A's Conv"},
            )
            assert resp.status_code == 201
            conv_id = resp.json()["data"]["id"]

            resp = await client.post(
                f"/api/v1/assistant/conversations/{conv_id}/messages",
                json={"content": "Secret message"},
            )
            assert resp.status_code == 201

            # Switch to User B
            _set_user(user_b)

            resp = await client.post(
                f"/api/v1/assistant/conversations/{conv_id}/messages",
                json={"content": "Hijack attempt"},
            )
            assert resp.status_code == 404

            _clear_user_override()


class TestAssistantSummarize:
    async def test_summarize_conversation(self) -> None:
        async with await _make_client() as client:
            resp = await client.post(
                "/api/v1/assistant/conversations",
                json={"title": "Summary Test"},
            )
            conv_id = resp.json()["data"]["id"]

            await client.post(
                f"/api/v1/assistant/conversations/{conv_id}/messages",
                json={"content": "Tell me about neural networks"},
            )

            resp = await client.post(
                f"/api/v1/assistant/conversations/{conv_id}/summarize",
            )
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["summary"] is not None
            assert data["conversation_id"] == conv_id


class TestAssistantFullCycle:
    async def test_complete_assistant_lifecycle(self) -> None:
        """Test session → conversation → messages → summarize → close."""
        async with await _make_client() as client:
            # 1. Create session
            resp = await client.post(
                "/api/v1/assistant/sessions",
                json={"title": "Full Cycle Session"},
            )
            assert resp.status_code == 201
            session_id = resp.json()["data"]["id"]

            # 2. Create conversation
            resp = await client.post(
                "/api/v1/assistant/conversations",
                json={"session_id": session_id, "title": "Full Cycle Conv"},
            )
            assert resp.status_code == 201
            conv_id = resp.json()["data"]["id"]

            # 3. Send multiple messages
            questions = [
                "What is Python?",
                "How do I use lists?",
                "What are list comprehensions?",
            ]
            for q in questions:
                resp = await client.post(
                    f"/api/v1/assistant/conversations/{conv_id}/messages",
                    json={"content": q},
                )
                assert resp.status_code == 201

            # 4. List messages
            resp = await client.get(
                f"/api/v1/assistant/conversations/{conv_id}/messages",
            )
            assert resp.status_code == 200
            assert resp.json()["pagination"]["total"] >= 6  # 3 user + 3 assistant

            # 5. Summarize
            resp = await client.post(
                f"/api/v1/assistant/conversations/{conv_id}/summarize",
            )
            assert resp.status_code == 200
            assert resp.json()["data"]["summary"] is not None

            # 6. Close session
            resp = await client.post(
                f"/api/v1/assistant/sessions/{session_id}/close",
            )
            assert resp.status_code == 200
            assert resp.json()["data"]["status"] == "archived"
