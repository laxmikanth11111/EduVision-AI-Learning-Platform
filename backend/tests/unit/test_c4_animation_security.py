"""C4.13 security audit — animation package must resist script/attribute injection.

The C4 package is rendered from user-derived structured content (titles, node
labels, captions, interaction prompts) into a self-contained HTML string that is
later embedded in a sandboxed iframe. These tests attack every sink with the
classic payloads (``<script>``, ``</script>`` closers, event-handler attributes,
``javascript:`` URLs, HTML comments) and assert that:

* user content can never close the package's single ``<script>`` block,
* user content can never break out of an HTML attribute,
* the embedded ``RAW`` JSON payload round-trips exactly (no truncation/corruption)
  after escaping,
* runtime text sinks (caption, prompt, annotation) are written with ``textContent``
  and never ``innerHTML`` from payload data.

Complements the existing cross-user API isolation tests in ``test_c4_animation_api.py``.
"""

from __future__ import annotations

import json
import re

from app.schemas.c3_visual_intelligence import C3VisualType
from app.schemas.c4_animation_intelligence import C4AnimationType
from app.services.c4_animation_renderer import render_animation_package
from app.services.c4_animation_spec_generator import generate_animation_specification

SINGLE_SCRIPT = "<script>alert('xss')</script>"
CLOSER = "</script><script>alert(document.domain)</script>"
EVENT_ATTR = 'onload="evil()" onerror="evil()"'
INJECT_ID = 'n1" onload="evil()'
COMMENT = "<!-- broken -->"
JAVASCRIPT_URL = "javascript:alert(document.domain)"


def _process_spec():
    spec = generate_animation_specification(
        {
            "visual_type": "flowchart",
            "title": "TCP handshake",
            "nodes": [
                {"id": "start", "label": "Start", "node_type": "start"},
                {"id": "step_0", "label": "SYN sent", "node_type": "process"},
                {"id": "step_1", "label": "SYN-ACK", "node_type": "process"},
                {"id": "step_2", "label": "ACK", "node_type": "process"},
                {"id": "end", "label": "Connected", "node_type": "end"},
            ],
            "edges": [
                {"id": "e_0", "source_id": "start", "target_id": "step_0"},
                {"id": "e_1", "source_id": "step_0", "target_id": "step_1"},
                {"id": "e_2", "source_id": "step_1", "target_id": "step_2"},
                {"id": "e_end", "source_id": "step_2", "target_id": "end"},
            ],
        },
        C4AnimationType.PROCESS_SEQUENCE,
        "The TCP Handshake",
        base_visual_type=C3VisualType.FLOWCHART,
    )
    return spec


def _payload(html: str) -> dict:
    match = re.search(r"var RAW = (\{.*?\});\n", html[html.index("<script>") :], re.DOTALL)
    assert match is not None, "RAW payload not found"
    return json.loads(match.group(1))


class TestC4SecurityInjection:
    def test_c4_sec_01_single_script_invariant_with_closer_injection(self):
        spec = _process_spec()
        spec.scenes[0].steps[0].caption = CLOSER
        spec.scenes[0].title = CLOSER
        html = render_animation_package(spec, title=CLOSER)
        assert html.count("<script>") == 1
        assert html.count("</script>") == 1

    def test_c4_sec_02_payload_roundtrips_after_escaping(self):
        spec = _process_spec()
        injected = CLOSER + COMMENT
        spec.scenes[0].steps[0].caption = injected
        spec.scenes[0].steps[1].caption = SINGLE_SCRIPT
        html = render_animation_package(spec)
        payload = _payload(html)
        assert payload["scenes"][0]["steps"][0]["caption"] == injected
        assert payload["scenes"][0]["steps"][1]["caption"] == SINGLE_SCRIPT
        assert "\\u003c/script" in html
        assert "\\u003c!--" in html

    def test_c4_sec_03_attribute_breakout_impossible(self):
        spec = _process_spec()
        spec.nodes[1].id = INJECT_ID
        spec.nodes[1].label = EVENT_ATTR
        html = render_animation_package(spec)
        assert 'onload="' not in html
        assert "&quot; onload=&quot;" in html
        assert html.count("<script>") == 1
        assert "onload=&quot;evil()&quot;" in html

    def test_c4_sec_04_title_and_topic_title_escaped(self):
        spec = _process_spec()
        html = render_animation_package(spec, title=SINGLE_SCRIPT, topic_title=EVENT_ATTR)
        assert "<title>" in html
        assert html.count("<title>") == 1
        assert html.count("<script>") == 1
        assert "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;" in html

    def test_c4_sec_05_interaction_text_cannot_execute(self):
        spec = _process_spec()
        spec.interactions[0].prompt = f'Which box? <img src=x onerror="evil()"> {JAVASCRIPT_URL}'
        spec.interactions[0].answer = SINGLE_SCRIPT
        spec.interactions[0].guide_hint = CLOSER
        html = render_animation_package(spec)
        payload = _payload(html)
        assert payload["interactions"][0]["prompt"] == (
            'Which box? <img src=x onerror="evil()"> javascript:alert(document.domain)'
        )
        assert payload["interactions"][0]["answer"] == SINGLE_SCRIPT
        assert html.count("<script>") == 1
        assert html.count("<img") == 0

    def test_c4_sec_06_text_sinks_use_textcontent_not_innerhtml(self):
        html = render_animation_package(_process_spec())
        for sink in ("c4-caption-text", "c4-caption-title", "c4-interaction-prompt"):
            assert sink in html
        inner_assignments = re.findall(r"innerHTML\s*=", html)
        assert len(inner_assignments) == 2, "only the fixed play/pause glyphs may use innerHTML"
        assert html.count("textContent") >= 3

    def test_c4_sec_07_comment_and_script_urls_do_not_alter_structure(self):
        spec = _process_spec()
        spec.nodes[1].description = f"{SINGLE_SCRIPT} {COMMENT} {JAVASCRIPT_URL}"
        html = render_animation_package(spec)
        assert html.count("<script>") == 1
        assert "&lt;!--" in html
        assert "<script>alert" not in html
