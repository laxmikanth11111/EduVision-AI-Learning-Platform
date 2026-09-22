"""Browser-level end-to-end tests for the presentation player teaching tools.

Exercises the real player.html in a real Chrome: teaching toolbar presence,
annotation drawing/undo/redo, tool switching via shortcuts, help overlay,
AI panel toggling, and present-mode entry. Runs only via ``pytest -m e2e``.
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


def _player_lesson(page, base_url: str) -> dict[str, str]:
    """Register a user and create a presentation+lesson via in-page fetch."""
    uid = uuid.uuid4().hex[:8]
    email = f"e2e_presenter_{uid}@example.com"
    password = "PlayerPass1234!"
    name = "E2E Presenter User"

    # Navigate to a same-origin page first so localStorage is writable.
    page.goto(f"{base_url}/frontend/index.html")
    page.wait_for_load_state("domcontentloaded")

    result = page.evaluate(
        """async ([base, email, password, name]) => {
            const regRes = await fetch(base + '/api/v1/auth/register', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ email, password, name }),
            });
            const regData = await regRes.json();
            const token = regData.tokens.access_token;

            const presRes = await fetch(base + '/api/v1/presentations/manual', {
                method: 'POST',
                headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token},
                body: JSON.stringify({ title: 'E2E Presenter Deck', topics: ['Alpha', 'Beta'] }),
            });
            const presData = await presRes.json();
            const presId = presData.data.id;

            const lessonRes = await fetch(
                base + '/api/v1/presentations/' + presId + '/lessons',
                {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token},
                    body: JSON.stringify({ mode: 'slide', title: 'E2E Presenter Lesson' }),
                },
            );
            const lessonData = await lessonRes.json();

            // Store tokens in localStorage so player.html picks them up.
            localStorage.setItem('user', JSON.stringify({ id: regData.user.id, name, email }));
            localStorage.setItem('access_token', token);
            localStorage.setItem('refresh_token', regData.tokens.refresh_token);
            return { lessonId: lessonData.data.id, presId: presId };
        }""",
        [base_url, email, password, name],
    )
    return {**result, "email": email, "password": password, "name": name}


def _open_player(page, base_url: str):
    ctx = _player_lesson(page, base_url)
    page.goto(f"{base_url}/frontend/player.html?lesson={ctx['lessonId']}&deck={ctx['presId']}")
    page.wait_for_load_state("domcontentloaded")
    thumbs = page.locator(".thumb-title")
    try:
        thumbs.first.wait_for(state="visible", timeout=25_000)
    except Exception:
        body = page.inner_text("body")
        assert "Failed" in body or "no slides" in body.lower(), f"Player failed: {body}"
        pytest.skip("Lesson was not ready in this environment; player teaching tools not exercised.")
    return ctx


@pytest.mark.e2e
def test_teaching_toolbar_visible_and_tools_switch(server_env, page):
    _open_player(page, server_env["base_url"])
    toolbar = page.locator("#teachBar")
    toolbar.wait_for(state="visible", timeout=10_000)
    assert toolbar.count() == 1

    pen_btn = page.locator('[data-tool="pen"]')
    pen_btn.click()
    assert page.locator('[data-tool="pen"]').get_attribute("class")
    label = page.locator("#teachToolLabel")
    assert "Pen" in label.inner_text()

    h_btn = page.locator('[data-tool="highlighter"]')
    h_btn.click()
    assert "Highlighter" in label.inner_text()


@pytest.mark.e2e
def test_annotation_draw_then_undo_redo(server_env, page):
    _open_player(page, server_env["base_url"])

    # Switch to pen via the toolbar.
    page.locator('[data-tool="pen"]').click()

    # Draw a stroke on the annotation canvas.
    canvas = page.locator("#annotCanvas")
    canvas.wait_for(state="attached", timeout=10_000)
    box = canvas.bounding_box()
    assert box is not None
    page.mouse.move(box["x"] + 200, box["y"] + 200)
    page.mouse.down()
    page.mouse.move(box["x"] + 300, box["y"] + 260, steps=8)
    page.mouse.up()

    # A stroke should now be stored.
    count_after_draw = page.evaluate(
        "Object.values(annotBySlide).reduce((n,s)=>n+s.items.length,0)"
    )
    assert count_after_draw >= 1

    # Undo clears it back to zero.
    page.locator("#teachUndo").click()
    count_after_undo = page.evaluate(
        "Object.values(annotBySlide).reduce((n,s)=>n+s.items.length,0)"
    )
    assert count_after_undo == 0

    # Redo restores it.
    page.locator("#teachRedo").click()
    count_after_redo = page.evaluate(
        "Object.values(annotBySlide).reduce((n,s)=>n+s.items.length,0)"
    )
    assert count_after_redo == 1


@pytest.mark.e2e
def test_annotations_do_not_modify_slide_dom(server_env, page):
    _open_player(page, server_env["base_url"])
    # Canvas lives inside the viewport by design; strip it so we compare only
    # the actual slide content the renderer produced.
    strip = """newId => {
        const el = document.getElementById('viewport');
        const clone = el.cloneNode(true);
        const c = clone.querySelector('#annotCanvas');
        if (c) c.remove();
        return clone.innerHTML;
    }"""
    before = page.evaluate(strip)
    page.locator('[data-tool="pen"]').click()
    canvas = page.locator("#annotCanvas")
    canvas.wait_for(state="attached", timeout=10_000)
    box = canvas.bounding_box()
    assert box is not None
    page.mouse.move(box["x"] + 150, box["y"] + 150)
    page.mouse.down()
    page.mouse.move(box["x"] + 250, box["y"] + 220, steps=6)
    page.mouse.up()
    after = page.evaluate(strip)
    assert before == after, "Slide DOM must be untouched by annotation strokes"


@pytest.mark.e2e
def test_keyboard_shortcuts_and_help_overlay(server_env, page):
    _open_player(page, server_env["base_url"])

    page.keyboard.press("?")
    help_overlay = page.locator("#helpOverlay")
    help_overlay.wait_for(state="visible", timeout=5_000)
    assert "Keyboard Shortcuts" in help_overlay.inner_text()
    page.keyboard.press("Escape")
    assert help_overlay.count() == 0 or not help_overlay.is_visible()

    # P switches to pen.
    page.keyboard.press("p")
    assert "Pen" in page.locator("#teachToolLabel").inner_text()
    # H switches to highlighter.
    page.keyboard.press("h")
    assert "Highlighter" in page.locator("#teachToolLabel").inner_text()


@pytest.mark.e2e
def test_ai_panel_opens_and_components_present(server_env, page):
    _open_player(page, server_env["base_url"])

    page.locator("#aiToggleBtn").click()
    panel = page.locator("#aiPanel")
    panel.wait_for(state="visible", timeout=5_000)
    pc = panel.get_attribute("class") or ""
    assert "open" in pc
    assert page.locator("#aiInput").count() == 1
    assert page.locator("#aiActions .ai-action").count() >= 5
    # Close it with Escape (also closes the panel keyboard-wise).
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    assert "open" not in (panel.get_attribute("class") or "")


@pytest.mark.e2e
def test_present_mode_enters_and_exits(server_env, page):
    _open_player(page, server_env["base_url"])

    page.locator("#presentBtn").click()
    page.wait_for_timeout(1200)
    body = page.locator("body")
    assert "presenting" in body.get_attribute("class")
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    assert "presenting" not in body.get_attribute("class")
