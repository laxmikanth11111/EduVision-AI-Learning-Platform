"""E2E test configuration.

Starts a real uvicorn server against a fresh SQLite database, seeds minimal
test data via the API, and exposes the server URL for browser tests.
"""
from __future__ import annotations

import os
import socket
import threading
import time
from collections.abc import Generator
from typing import Any

import httpx
import pytest
import uvicorn


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_server(base_url: str, timeout: float = 45.0) -> None:
    deadline = time.monotonic() + timeout
    last_err = None
    while time.monotonic() < deadline:
        try:
            with httpx.Client() as client:
                r = client.get(f"{base_url}/api/v1/health/live", timeout=5.0)
                if r.status_code < 500:
                    return
                last_err = f"status {r.status_code}: {r.text}"
        except Exception as e:
            last_err = str(e)
        time.sleep(0.3)
    raise RuntimeError(f"Server did not become ready within {timeout}s (last_err: {last_err})")


def _seed_test_data(base_url: str) -> dict[str, str]:
    """Register a user and create a presentation+lesson via the REST API."""
    creds: dict[str, str] = {
        "email": "e2e_smoke_user@example.com",
        "password": "testpassword123",
        "name": "E2E Test User",
    }

    with httpx.Client(base_url=base_url, timeout=15.0) as client:
        # Register the user; ignore 409 if already exists from a prior run.
        r = client.post(
            "/api/v1/auth/register",
            json={
                "email": creds["email"],
                "password": creds["password"],
                "name": creds["name"],
            },
        )
        if r.status_code == 201:
            data = r.json()
            user_id = data["user"]["id"]
            access_token = data["tokens"]["access_token"]
        elif r.status_code == 409:
            r2 = client.post(
                "/api/v1/auth/login",
                json={"email": creds["email"], "password": creds["password"]},
            )
            r2.raise_for_status()
            logindata = r2.json()
            user_id = logindata["user"]["id"]
            access_token = logindata["tokens"]["access_token"]
        else:
            raise RuntimeError(f"Register failed: {r.status_code} {r.text}")

        auth_headers = {"Authorization": f"Bearer {access_token}"}

        # Create a presentation owned by the seed user.
        r = client.post(
            "/api/v1/presentations/manual",
            headers=auth_headers,
            json={
                "title": "E2E Smoke Deck",
                "topics": ["Photosynthesis", "Cellular Respiration"],
            },
        )
        r.raise_for_status()
        pres_id: str = r.json()["data"]["id"]

        # Create a lesson for this presentation.
        r = client.post(
            f"/api/v1/presentations/{pres_id}/lessons",
            headers=auth_headers,
            json={"mode": "slide", "title": "E2E Smoke Lesson"},
        )
        r.raise_for_status()
        lesson_id: str = r.json()["data"]["id"]

    return {**creds, "user_id": user_id, "presentation_id": pres_id, "lesson_id": lesson_id}


class _ServerRunner:
    """Runs uvicorn in a background thread."""

    def __init__(self, app: Any, port: int) -> None:
        config = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_level="error",
            access_log=False,
        )
        self._server = uvicorn.Server(config)

        def _run():
            try:
                self._server.run()
            except Exception:
                import traceback
                traceback.print_exc()

        self._thread = threading.Thread(target=_run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=10)


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------

def pytest_configure(config):  # noqa: D103
    config.addinivalue_line(
        "markers",
        "e2e: browser-level end-to-end smoke tests against a running server",
    )


def pytest_collection_modifyitems(config, items):  # noqa: D103
    import pathlib

    e2e_dir = pathlib.Path(__file__).parent

    # Only the `e2e` marker (pytest -m e2e) or an explicit env flag enables the
    # browser smoke tests. They start a uvicorn server and launch a real
    # browser, so they must never run implicitly as part of the default suite.
    explicitly_requested = bool(
        config.getoption("-m")
        and "e2e" in config.getoption("-m")
        or os.environ.get("PYTEST_RUN_E2E") == "1"
    )

    for item in items:
        if pathlib.Path(item.fspath).is_relative_to(e2e_dir):
            item.add_marker("e2e")
            if not explicitly_requested:
                item.add_marker(
                    pytest.mark.skip(
                        reason="E2E smoke disabled; run with `pytest -m e2e` "
                        "or PYTEST_RUN_E2E=1"
                    )
                )


@pytest.fixture(scope="session")
def server_env() -> Generator[dict[str, str]]:
    """Start a real FastAPI server and seed minimal test data.

    The root ``tests/conftest.py`` already builds ``app.main.app`` against a
    fresh SQLite test database (``setup_database`` autouse fixture creates the
    tables and patches the session factories). This fixture reuses that same
    app/engine so the uvicorn server and the browser both observe the same,
    already-initialized test DB — no separate database scaffolding here.

    Yields a dict with ``base_url``, ``lesson_id``, ``user_id``, ``email`` and
    ``password`` so tests can drive the browser.
    """
    from app.main import app  # loaded via root tests/conftest

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"

    runner = _ServerRunner(app, port)
    runner.start()

    try:
        _wait_for_server(base_url, timeout=45)

        # Seed test data via the REST API.
        seed = _seed_test_data(base_url)
        seed["base_url"] = base_url
        yield seed
    finally:
        runner.stop()
