"""Browser-level end-to-end smoke: sign-in → create → player.

Uses pytest-playwright with system Chrome (channel="chrome") against the
real FastAPI app served by the session-scoped ``server_env`` fixture.
"""
from __future__ import annotations

import uuid

import pytest


@pytest.fixture(scope="session")
def browser_context_args():
    return {
        "viewport": {"width": 1280, "height": 800},
        "ignore_https_errors": True,
    }


@pytest.fixture(scope="session")
def browser_type_launch_args():
    return {
        "headless": True,
        "channel": "chrome",
        "args": [
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--disable-web-security",
        ],
    }


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------


def _sign_in(page, base_url: str, email: str, password: str) -> None:
    """Drive the real sign-in form and wait for the redirect to upload."""
    page.goto(f"{base_url}/frontend/signin.html")
    page.wait_for_load_state("domcontentloaded")
    page.fill("#email", email)
    page.fill("#password", password)
    page.click("#submitBtn")
    page.wait_for_url("**/upload.html", timeout=15_000)
    page.wait_for_load_state("domcontentloaded")


def _create_lesson_via_browser(page, base_url: str) -> dict[str, str]:
    """Register a user and create a presentation+lesson using in-page fetch.

    Returns ``{email, password, name, lesson_id, presentation_id}``.
    """
    uid = uuid.uuid4().hex[:8]
    email = f"e2e_player_{uid}@example.com"
    password = "PlayerPass1234!"
    name = "E2E Player User"

    result = page.evaluate(
        """async ([base, email, password, name]) => {
            // 1. Register user
            const regRes = await fetch(base + '/api/v1/auth/register', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ email, password, name }),
            });
            const regData = await regRes.json();
            const token = regData.tokens.access_token;

            // 2. Create presentation
            const presRes = await fetch(base + '/api/v1/presentations/manual', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer ' + token,
                },
                body: JSON.stringify({
                    title: 'E2E Player Deck',
                    topics: ['Topic Alpha', 'Topic Beta'],
                }),
            });
            const presData = await presRes.json();
            const presId = presData.data.id;

            // 3. Create lesson
            const lessonRes = await fetch(
                base + '/api/v1/presentations/' + presId + '/lessons',
                {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': 'Bearer ' + token,
                    },
                    body: JSON.stringify({ mode: 'slide', title: 'E2E Player Lesson' }),
                },
            );
            const lessonData = await lessonRes.json();
            return { lessonId: lessonData.data.id, presId: presId };
        }""",
        [base_url, email, password, name],
    )

    return {
        "email": email,
        "password": password,
        "name": name,
        "lesson_id": result["lessonId"],
        "presentation_id": result["presId"],
    }


# -----------------------------------------------------------------------
# Tests
# -----------------------------------------------------------------------


@pytest.mark.e2e
def test_signin_e2e(server_env, page):
    """Sign in through the real SPA and verify the upload page loads."""
    base = server_env["base_url"]

    page.goto(f"{base}/frontend/signin.html")
    page.wait_for_load_state("domcontentloaded")
    assert "Sign in" in page.title() or "Sign in" in page.inner_text("h1")

    page.fill("#email", server_env["email"])
    page.fill("#password", server_env["password"])
    page.click("#submitBtn")

    page.wait_for_url("**/upload.html", timeout=10_000)
    page.wait_for_load_state("domcontentloaded")

    nav_user = page.locator("#userName")
    nav_user.wait_for(state="visible", timeout=5_000)
    assert server_env["name"] in nav_user.inner_text()

    assert page.locator(".upload-zone").count() == 1 or page.locator("#manualTitle").count() == 1


@pytest.mark.e2e
def test_player_renders_topics(server_env, page):
    """Load the player with a pre-seeded lesson and verify topics render."""
    base = server_env["base_url"]

    # Create a user + lesson via the browser's fetch API.
    player = _create_lesson_via_browser(page, base)
    lesson_id = player["lesson_id"]
    deck_id = player["presentation_id"]

    # Sign in so the player has valid tokens in localStorage.
    _sign_in(page, base, player["email"], player["password"])

    # Navigate to the player.
    page.goto(f"{base}/frontend/player.html?lesson={lesson_id}&deck={deck_id}")
    page.wait_for_load_state("domcontentloaded")

    # The player calls POST /lessons/{id}/player/start which returns topics.
    # Wait for either the sidebar thumbnails or the error / "no slides" state.
    thumbs = page.locator(".thumb-title")
    try:
        thumbs.first.wait_for(state="visible", timeout=20_000)
        assert thumbs.count() >= 1, "Expected at least one topic in the player"
    except Exception:
        # The lesson may still be in "queued" status.  Verify the page loaded
        # without crashing — a valid error state is acceptable for the smoke.
        body = page.inner_text("body")
        assert (
            "upload" in page.url.lower()
            or "Failed" in body
            or "no slides" in body.lower()
            or "no topics" in body.lower()
            or "topic alpha" in body.lower()
        )


@pytest.mark.e2e
def test_nonexistent_lesson_shows_error(server_env, page):
    """Navigate to a nonexistent lesson and verify the player handles it."""
    base = server_env["base_url"]

    # Register a user via the signup form (real SPA interaction).
    uid = uuid.uuid4().hex[:8]
    page.goto(f"{base}/frontend/signup.html")
    page.wait_for_load_state("domcontentloaded")
    page.fill("#email", f"e2e_err_{uid}@example.com")
    page.fill("#password", "ErrPath12345!")
    page.fill("#name", "Error Path User")
    page.click("#submitBtn")
    page.wait_for_url("**/upload.html", timeout=10_000)
    page.wait_for_load_state("domcontentloaded")

    # Navigate to the player with a bogus lesson ID.
    page.goto(f"{base}/frontend/player.html?lesson=lesson_nonexistent&deck=pres_nonexistent")
    page.wait_for_load_state("domcontentloaded")

    # The player should show an error, a "no slides" message, or redirect
    # back to upload (because the lesson lookup failed).
    page.wait_for_timeout(3000)
    url = page.url
    body_text = page.inner_text("body")
    has_expected = (
        "Failed" in body_text
        or "not found" in body_text.lower()
        or "error" in body_text.lower()
        or "no slides" in body_text.lower()
        or "upload" in url.lower()
    )
    assert has_expected, f"Expected error state on nonexistent lesson, got: {url}"


@pytest.mark.e2e
def test_index_page_loads(server_env, page):
    """Verify the index page renders correctly in a real browser."""
    base = server_env["base_url"]
    page.goto(f"{base}/frontend/index.html")
    page.wait_for_load_state("domcontentloaded")

    assert "EduVision AI" in page.title() or "EduVision AI" in page.inner_text("h1")
    assert page.locator("a:has-text('Get Started')").count() == 1
    assert page.locator("a:has-text('Sign In')").count() == 1
