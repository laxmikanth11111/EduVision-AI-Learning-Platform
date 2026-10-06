"""Read-after-write consistency across HTTP request boundaries.

FastAPI runs the exit code of a ``yield`` dependency *after* the response has
been handed to the ASGI server (``fastapi.routing.request_response`` calls
``await response(scope, receive, send)`` before it closes the request-level
``AsyncExitStack``). When ``get_unit_of_work`` committed in that teardown, a
successful ``201`` could reach the client while its transaction was still open.
A client that immediately followed up on another connection saw ``404`` until the
commit happened to land.

These tests assert the invariant directly: **when the response head is emitted,
the write must already be visible to an independent connection.** No sleeps and
no polling are used; either the write is committed before the response is
observed, or the test fails.

The endpoints exercised here (``POST /api/v1/folders``,
``POST /api/v1/me/goals``) deliberately have no incidental in-service commit, so
they observe the raw request-scoped transaction lifecycle.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

import app.database.session as db_session_module
from app.main import app
from app.models.learning_goal import LearningGoal
from app.models.presentation_folder import PresentationFolder

pytestmark = pytest.mark.integration

# Shared ordering log. "commit" is appended by the UnitOfWork.commit hook and
# "response_start" by the raw-ASGI probe, so the two can be compared directly.
EVENTS: list[str] = []


@pytest.fixture(autouse=True)
def _record_commits(monkeypatch: pytest.MonkeyPatch):
    """Append "commit" to the shared log whenever a request UoW commits."""
    from app.database.unit_of_work import UnitOfWork

    original_commit = UnitOfWork.commit

    async def _commit(self) -> None:
        await original_commit(self)
        EVENTS.append("commit")

    monkeypatch.setattr(UnitOfWork, "commit", _commit)
    EVENTS.clear()
    yield
    EVENTS.clear()


async def _visible(model: Any, name: str) -> bool:
    """Read through a brand-new session, i.e. an independent connection."""
    async with db_session_module.async_session_factory() as session:
        result = await session.execute(select(model.id).where(model.name == name))
        return result.scalar_one_or_none() is not None


async def _post_and_probe(
    path: str,
    payload: dict[str, Any],
    model: Any,
    name: str,
) -> dict[str, Any]:
    """POST and observe the DB at the instant the response head is emitted.

    The ASGI protocol is driven by hand so the observation happens exactly when
    the server emits the response head -- the moment a real client learns the
    create succeeded.
    """
    body = json.dumps(payload).encode()
    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"host", b"test"),
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
        ],
        "client": ("127.0.0.1", 12345),
        "server": ("test", 80),
    }

    request_sent = False
    status_code: int | None = None
    chunks: list[bytes] = []
    visible_at_head: bool | None = None

    async def receive() -> dict[str, Any]:
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        nonlocal status_code, visible_at_head
        if message["type"] == "http.response.start":
            status_code = int(message["status"])
            EVENTS.append("response_start")
            if status_code == 201:
                visible_at_head = await _visible(model, name)
        elif message["type"] == "http.response.body":
            chunks.append(message.get("body", b""))

    await app(scope, receive, send)

    assert status_code is not None, "the app produced no response at all"
    return {
        "status_code": status_code,
        "body": b"".join(chunks),
        "visible_at_head": visible_at_head,
    }


async def test_created_row_is_visible_to_an_independent_connection_at_response_time() -> None:
    """create/upload -> immediate follow-up request -> resource already visible."""
    result = await _post_and_probe(
        "/api/v1/folders",
        {"name": "Race Visibility Folder"},
        PresentationFolder,
        "Race Visibility Folder",
    )
    assert result["status_code"] == 201, result["body"]
    assert result["visible_at_head"] is True, (
        "201 Created was emitted before the row was committed: an immediate "
        "read from another connection would have seen nothing"
    )


async def test_commit_precedes_response_head() -> None:
    """Ordering proof that does not depend on database isolation semantics.

    ``get_unit_of_work`` must not leave its COMMIT to dependency teardown,
    because teardown runs only after the response has been sent.
    """
    result = await _post_and_probe(
        "/api/v1/folders",
        {"name": "Race Ordering Folder"},
        PresentationFolder,
        "Race Ordering Folder",
    )
    assert result["status_code"] == 201, result["body"]
    assert "commit" in EVENTS, "no commit was recorded for the create request"
    assert EVENTS.index("commit") < EVENTS.index("response_start"), (
        f"COMMIT must happen before the response head is emitted; got {EVENTS}"
    )


async def test_immediate_follow_up_get_returns_the_created_presentation() -> None:
    """End-to-end read-after-write over the public API: no sleeps, no retries."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        created = await c.post(
            "/api/v1/folders", json={"name": "Follow Up Folder"}
        )
        assert created.status_code == 201, created.text
        folder_id = created.json()["data"]["id"]

        fetched = await c.get(f"/api/v1/folders/{folder_id}/breadcrumbs")

    assert fetched.status_code == 200, (
        f"immediate GET returned {fetched.status_code} after a 201 create"
    )
    assert fetched.json()["data"][0]["id"] == folder_id


async def test_goal_create_is_visible_immediately() -> None:
    """Second independent write path, exercising the same lifecycle."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        created = await c.post(
            "/api/v1/me/goals",
            json={
                "goal_type": "mastery_target",
                "title": "Immediate Goal",
                "target_value": 10,
            },
        )
        assert created.status_code == 200, created.text
        goal_id = created.json()["data"]["goal"]["id"]

        fetched = await c.get(f"/api/v1/me/goals/{goal_id}")

    assert fetched.status_code == 200, (
        f"immediate GET returned {fetched.status_code} after a successful create"
    )
    assert fetched.json()["data"]["goal"]["id"] == goal_id


async def test_failed_request_is_not_committed() -> None:
    """The commit barrier must not turn an error path into a commit."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        rejected = await c.post("/api/v1/folders", json={})
    assert rejected.status_code in (400, 422), rejected.text
    assert "commit" not in EVENTS, f"an error response committed: {EVENTS}"


async def test_read_only_request_is_unaffected() -> None:
    """A pure read still works, with or without a UoW dependency."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        listed = await c.get("/api/v1/folders")
        live = await c.get("/api/v1/health/live")
    assert listed.status_code == 200, listed.text
    assert live.status_code == 200, live.text


async def test_uncommitted_rows_do_not_leak_between_connections() -> None:
    """Sanity check for the probe itself: an uncommitted row is invisible."""
    from app.database.unit_of_work import UnitOfWork
    from app.repositories.presentation_folder_repository import (
        PresentationFolderRepository,
    )
    from tests.conftest import TEST_USER_ID

    uow = UnitOfWork()
    await uow.__aenter__()
    try:
        await PresentationFolderRepository(uow.session).create(
            name="Uncommitted Folder", owner_id=TEST_USER_ID
        )
        assert await _visible(PresentationFolder, "Uncommitted Folder") is False
    finally:
        await uow.__aexit__(None, None, None)
    assert await _visible(PresentationFolder, "Uncommitted Folder") is True