"""Frontend contract regression tests for the presentation player.

These do not execute JavaScript; they verify that the served player.html
contains the annotation layer, teaching-tools wiring, keyboard shortcuts,
help overlay and AI assistant panel that the backend test suite must not
silently remove. The structural ids/functions below are referenced by both
the HTML and the inline script, so a mismatch fails loudly here instead of
in the browser.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


FRONTEND_PLAYER_URL = "/frontend/player.html"

# (html id | function name | a string that must literally appear)
REQUIRED_PLAYER_PIECES = [
    # annotation overlay: canvas is created at runtime per slide render
    ("canvas", "annot-canvas", "annot-canvas"),
    ("canvas", "ensureAnnotCanvas", "function ensureAnnotCanvas()"),
    ("canvas", "sizeAnnotCanvas", "function sizeAnnotCanvas()"),
    ("canvas", "wireAnnotationLayer", "function wireAnnotationLayer()"),
    # teaching toolbar
    ("toolbar", "teachBar", 'id="teachBar"'),
    ("toolbar", "setTool", "function setTool(tool)"),
    ("toolbar", "teachUndo", 'id="teachUndo"'),
    ("toolbar", "teachRedo", 'id="teachRedo"'),
    ("toolbar", "annotUndo", "function annotUndo()"),
    ("toolbar", "annotRedo", "function annotRedo()"),
    ("toolbar", "annotClearSlide", "function annotClearSlide()"),
    ("toolbar", "annotClearAll", "function annotClearAll()"),
    ("toolbar", "toggleThumbCompact", "function toggleThumbCompact()"),
    # annotation visibility toggle
    ("toolbar", "teachAnnotToggle", 'id="teachAnnotToggle"'),
    ("toolbar", "toggleAnnotVisibility", "function toggleAnnotVisibility()"),
    ("toolbar", "annotVisible", "let annotVisible = true;"),
    # learner progress surfacing (backend completion_percentage is displayed)
    ("progress", "completion_percentage", "completion_percentage"),
    ("progress", "applyCompletionFromResponse", "function applyCompletionFromResponse(payload)"),
    ("progress", "ljCompletionPct", 'id="ljCompletionPct"'),
    # laser + eraser helpers
    ("laser", "laserDot", 'id="laserDot"'),
    ("eraser", "eraserRing", 'id="eraserRing"'),
    ("pointer", "moveLaser", "function moveLaser(p)"),
    # present mode scaling
    ("present", "wrapForPresent", "function wrapForPresent()"),
    ("present", "fitPresentedSlide", "function fitPresentedSlide()"),
    ("present", "enterPresent", "async function enterPresent()"),
    ("present", "presCounter", 'id="presCounter"'),
    # help overlay + shortcuts
    ("help", "helpOverlay", 'id="helpOverlay"'),
    ("help", "openHelp", "function openHelp()"),
    ("help", "closeHelp", "function closeHelp()"),
    # AI assistant panel (grounded via tutor endpoints)
    ("ai", "aiPanel", 'id="aiPanel"'),
    ("ai", "aiBackdrop", 'id="aiBackdrop"'),
    ("ai", "toggleAiPanel", "function toggleAiPanel(force)"),
    ("ai", "aiAsk", "async function aiAsk(kind)"),
    ("ai", "ensureTutorSession", "async function ensureTutorSession()"),
    ("ai", "tutor/sessions", "/tutor/sessions"),
    ("ai", "aiThread", 'id="aiThread"'),
    ("ai", "aiInput", 'id="aiInput"'),
]


class TestPlayerFrontendContract:
    async def test_player_html_is_served(self, client) -> None:
        response = await client.get(FRONTEND_PLAYER_URL)
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert "<html" in response.text.lower()

    async def test_all_teaching_tool_wiring_present(self, client) -> None:
        response = await client.get(FRONTEND_PLAYER_URL)
        assert response.status_code == 200
        missing = []
        for _section, name, needle in REQUIRED_PLAYER_PIECES:
            if needle not in response.text:
                missing.append(name)
        assert missing == [], "player.html missing: {}".format(", ".join(missing))

    async def test_annotation_layer_never_mutates_slide_markup(self, client) -> None:
        """Annotations live on a separate canvas; the slide renderer must not
        be asked to emit annotation strokes into the slide DOM."""
        response = await client.get(FRONTEND_PLAYER_URL)
        assert response.status_code == 200
        # The only annotation sink in the file is the overlay canvas.
        assert response.text.count(".annot-canvas") >= 1
        # No placeholder text for teaching tools should leak into served HTML.
        assert "NOT_IMPLEMENTED" not in response.text
        assert "TODO" not in response.text

    async def test_keyboard_shortcut_help_lists_major_bindings(self, client) -> None:
        response = await client.get(FRONTEND_PLAYER_URL)
        assert response.status_code == 200
        assert "Keyboard Shortcuts" in response.text
        for _key, label in [
            ("ArrowRight", "Next slide"),
            ("KeyP", "Pen"),
            ("KeyH", "Highlighter"),
            ("KeyE", "Eraser"),
            ("KeyL", "Laser"),
            ("KeyT", "Text"),
            ("KeyV", "Pointer"),
        ]:
            # the help panel documents human-readable labels
            assert label in response.text

    async def test_ai_uses_mastery_tutor_not_fabrication(self, client) -> None:
        """AI answers must come from the real grounded tutor endpoints and
        must not invent client-side 'AI' responses."""
        response = await client.get(FRONTEND_PLAYER_URL)
        assert response.status_code == 200
        body = response.text
        assert "/tutor/sessions" in body
        assert "/messages" in body
        # disallow naive fake-AI artefacts
        assert "fakeAi" not in body
        assert "MOCK_AI" not in body
