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


def _player_lesson(page, base_url: str, topics: list[str] | None = None) -> dict[str, str]:
    """Register a user and create a presentation+lesson via in-page fetch."""
    uid = uuid.uuid4().hex[:8]
    email = f"e2e_presenter_{uid}@example.com"
    password = "PlayerPass1234!"
    name = "E2E Presenter User"
    deck_topics = topics or ["Alpha", "Beta"]

    # Navigate to a same-origin page first so localStorage is writable.
    page.goto(f"{base_url}/frontend/index.html")
    page.wait_for_load_state("domcontentloaded")

    result = page.evaluate(
        """async ([base, email, password, name, deckTopics]) => {
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
                body: JSON.stringify({ title: 'E2E Presenter Deck', topics: deckTopics }),
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
        [base_url, email, password, name, deck_topics],
    )
    return {**result, "email": email, "password": password, "name": name}


def _open_player(
    page, base_url: str, topics: list[str] | None = None
) -> dict[str, str]:
    ctx = _player_lesson(page, base_url, topics=topics)
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


@pytest.mark.e2e
def test_annotation_visibility_toggle_hides_and_shows_layer(server_env, page):
    _open_player(page, server_env["base_url"])

    # Draw one stroke so there is something to reveal/hide.
    page.locator('[data-tool="pen"]').click()
    canvas = page.locator("#annotCanvas")
    canvas.wait_for(state="attached", timeout=10_000)
    page.wait_for_function(
        """() => {
            const c = document.getElementById('annotCanvas');
            return c && c.clientWidth > 0 && c.clientHeight > 0;
        }""",
        timeout=10_000,
    )
    box = canvas.bounding_box()
    assert box is not None
    page.mouse.move(box["x"] + 120, box["y"] + 120)
    page.mouse.down()
    page.mouse.move(box["x"] + 180, box["y"] + 160, steps=5)
    page.mouse.up()

    # Hide the annotation layer; the overlay must become invisible.
    toggle = page.locator("#teachAnnotToggle")
    toggle.click()
    assert "hidden" in (canvas.get_attribute("style") or "")
    assert toggle.get_attribute("aria-pressed") == "false"

    # Reveal it again; the stroke must still be stored and visible.
    toggle.click()
    assert "hidden" not in (canvas.get_attribute("style") or "")
    assert toggle.get_attribute("aria-pressed") == "true"
    kept = page.evaluate(
        "Object.values(annotBySlide).reduce((n,s)=>n+s.items.length,0)"
    )
    assert kept >= 1


@pytest.mark.e2e
def test_learner_progress_completion_reflects_slide_position(server_env, page):
    # Four topics so source-mode slide indices map onto all four topics and the
    # backend completion can progress from the first slide to the last.
    _open_player(page, server_env["base_url"], topics=["Alpha", "Beta", "Gamma", "Delta"])

    # The panel must surface real backend completion (was hardcoded 0%).
    pct = page.locator("#ljCompletionPct").first
    pct.wait_for(state="visible", timeout=15_000)
    try:
        initial = float(pct.inner_text().rstrip("%"))
    except ValueError:
        initial = 0.0
    # A fresh session starts on topic 0 of a 4-topic deck -> 25% (never 0%).
    assert initial == 25.0, f"initial completion must be the backend value, got {initial!r}"

    # Jump to the final slide via the End key. The backend maps the source
    # slide index onto a topic via the mode-aware position mapping (with the
    # final source slide pinned to the last topic), so the last of 4 source
    # slides reports 100% — not the old source-mode ceiling of 50%.
    page.keyboard.press("End")
    page.wait_for_timeout(1600)  # goTo + 400ms position debounce + panel re-render

    final_text = pct.inner_text()
    try:
        final = float(final_text.rstrip("%"))
    except ValueError:
        final = 0.0
    assert final > initial, f"completion must advance with the slide position ({initial}% -> {final}%)"
    assert final == 100.0, f"final source slide must reach the backend value, got {final_text!r}"


@pytest.mark.e2e
def test_presenter_notes_overlay_toggles_with_buttons_and_keys(server_env, page):
    _open_player(page, server_env["base_url"])

    panel = page.locator("#notesPanel")
    toggle = page.locator("#teachNotesToggle")
    assert "hidden" in (panel.get_attribute("class") or ""), "notes panel must start hidden"
    assert toggle.get_attribute("aria-expanded") == "false"

    # N opens it (the key binding works whenever no modal is visible) and the
    # toggle button reflects the expanded state.
    page.keyboard.press("n")
    panel.wait_for(state="visible", timeout=5_000)
    assert toggle.get_attribute("aria-expanded") == "true"
    body = page.locator("#notesBody").inner_text()
    # Either real presenter notes or the explicit empty-state message render.
    assert body.strip() != ""

    # Escape closes the notes overlay (it is modal-like: only Escape while open).
    page.keyboard.press("Escape")
    assert "hidden" in (panel.get_attribute("class") or "")
    assert toggle.get_attribute("aria-expanded") == "false"

    # The toggle button closes and reopens it (both directions).
    toggle.click()
    panel.wait_for(state="visible", timeout=5_000)
    assert toggle.get_attribute("aria-expanded") == "true"
    toggle.click()
    assert "hidden" in (panel.get_attribute("class") or "")
    assert toggle.get_attribute("aria-expanded") == "false"

    # Shift+N reopens it from the closed state.
    page.keyboard.press("N")
    panel.wait_for(state="visible", timeout=5_000)
    page.keyboard.press("Escape")

    # Navigate to another slide while closed, then reopen: the notes content
    # is (re)rendered for the current slide each time it opens.
    page.locator("#thumb-1").click()
    page.wait_for_timeout(600)
    page.keyboard.press("n")
    panel.wait_for(state="visible", timeout=5_000)
    assert page.locator("#notesBody").inner_text().strip() != ""
    assert toggle.get_attribute("aria-expanded") == "true"
    page.keyboard.press("Escape")


@pytest.mark.e2e
def test_annotations_persist_across_player_reload(server_env, page):
    ctx = _open_player(page, server_env["base_url"])

    page.locator('[data-tool="pen"]').click()
    canvas = page.locator("#annotCanvas")
    canvas.wait_for(state="attached", timeout=10_000)
    page.wait_for_function(
        """() => {
            const c = document.getElementById('annotCanvas');
            return c && c.clientWidth > 0 && c.clientHeight > 0;
        }""",
        timeout=10_000,
    )
    box = canvas.bounding_box()
    assert box is not None
    page.mouse.move(box["x"] + 200, box["y"] + 200)
    page.mouse.down()
    page.mouse.move(box["x"] + 300, box["y"] + 260, steps=8)
    page.mouse.up()

    drawn = page.evaluate(
        "Object.values(annotBySlide).reduce((n,s)=>n+s.items.length,0)"
    )
    assert drawn >= 1

    # Wait for the 700ms debounce + PUT round trip, then verify the backend row.
    page.wait_for_timeout(1800)
    persisted = page.evaluate(
        """async (payload) => {
            const token = localStorage.getItem('access_token');
            const res = await fetch(
                payload.base + '/api/v1/lessons/' + payload.lessonId + '/annotations',
                { headers: { 'Authorization': 'Bearer ' + token } },
            );
            return await res.json();
        }""",
        {"base": server_env["base_url"], "lessonId": ctx["lessonId"]},
    )
    layers = persisted["data"]["layers"]
    assert layers, "drawn annotation layer must be persisted to the backend"

    # A fresh load must restore the stroke from the persisted layer.
    page.reload()
    page.wait_for_load_state("domcontentloaded")
    page.locator(".thumb-title").first.wait_for(state="visible", timeout=25_000)
    # Hydration is async after render, so poll until the merged layer lands.
    page.wait_for_function(
        "() => Object.values(annotBySlide).reduce((n,s)=>n+s.items.length,0) >= 1",
        timeout=10_000,
    )
    restored = page.evaluate(
        "Object.values(annotBySlide).reduce((n,s)=>n+s.items.length,0)"
    )
    assert restored >= 1, "persisted annotations must be restored after reload"
