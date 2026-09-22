"""Unit tests for EduVision 2.0 Checkpoint C4 — deterministic animation package
renderer."""

import json
import re

from app.schemas.c3_visual_intelligence import C3VisualType
from app.schemas.c4_animation_intelligence import C4AnimationType
from app.services.c4_animation_renderer import render_animation_package
from app.services.c4_animation_spec_generator import generate_animation_specification


def _process_spec():
    return generate_animation_specification(
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


def _comparison_spec():
    return generate_animation_specification(
        {
            "visual_type": "comparison",
            "title": "OSI vs TCP/IP",
            "columns": [
                {"header": "OSI", "items": ["7 layers", "Session layer", "Presentation layer"]},
                {"header": "TCP/IP", "items": ["4 layers", "No session layer", "Merged transport"]},
            ],
        },
        C4AnimationType.COMPARISON_REVEAL,
        "OSI vs TCP/IP",
        base_visual_type=C3VisualType.COMPARISON,
    )


class TestC4PackageRenderer:
    def test_c4_pkg_01_deterministic_bytes(self):
        a = render_animation_package(_process_spec(), title="T", topic_title="The TCP Handshake")
        b = render_animation_package(_process_spec(), title="T", topic_title="The TCP Handshake")
        assert a == b
        assert len(a) > 2000

    def test_c4_pkg_02_markers_present(self):
        html = render_animation_package(_process_spec(), topic_title="The TCP Handshake")
        for marker in (
            'id="c4-svg"',
            'id="c4-hud"',
            'id="c4-play"',
            'id="c4-next"',
            'id="c4-prev"',
            'id="c4-restart"',
            'id="c4-step"',
            'id="c4-speed"',
            "c4-explanation",
            "The TCP Handshake",
        ):
            assert marker in html

    def test_c4_pkg_03_single_closing_script_tag(self):
        html = render_animation_package(_process_spec())
        assert html.count("</script>") == 1

    def test_c4_pkg_04_payload_json_embedded(self):
        html = render_animation_package(_process_spec())
        match = re.search(r"var RAW = (\{.*?\});\n", html[html.index("<script>") :], re.DOTALL)
        assert match is not None
        payload = json.loads(match.group(1))
        total = sum(len(s["steps"]) for s in payload["scenes"])
        spec = _process_spec()
        assert total == sum(len(s.steps) for s in spec.scenes)
        assert payload["animationType"] == "process_sequence"

    def test_c4_pkg_05_html_escapes_user_content(self):
        spec = _process_spec()
        spec.nodes[1].label = "<script>alert(1)</script>"
        html = render_animation_package(spec)
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html

    def test_c4_pkg_06_comparison_boxes_rendered(self):
        html = render_animation_package(_comparison_spec(), topic_title="OSI vs TCP/IP")
        assert 'id="c4-compare"' in html
        assert 'data-id="col_a"' in html
        assert 'data-id="col_b"' in html
        assert "OSI" in html
        assert "TCP/IP" in html

    def test_c4_pkg_07_explanation_embedded(self):
        html = render_animation_package(_comparison_spec(), topic_title="OSI vs TCP/IP")
        for label in ("Learning guide", "What you see", "Why motion helps"):
            assert label in html

    def test_c4_pkg_08_interaction_overlay_for_generated_spec(self):
        html = render_animation_package(_process_spec())
        assert 'id="c4-interaction"' in html
        assert 'id="c4-interaction-next"' in html

    def test_c4_pkg_09_steps_capped_per_scene_in_payload(self):
        from app.schemas.c4_animation_intelligence import MAX_STEPS_PER_SCENE

        spec = _process_spec()
        html = render_animation_package(spec)
        match = re.search(r"var RAW = (\{.*?\});\n", html[html.index("<script>") :], re.DOTALL)
        payload = json.loads(match.group(1))
        assert max(len(s["steps"]) for s in payload["scenes"]) <= MAX_STEPS_PER_SCENE

    def test_c4_pkg_10_edges_and_nodes_ids_present(self):
        spec = _process_spec()
        html = render_animation_package(spec)
        for nid in ("start", "step_0", "end"):
            assert f'data-id="{nid}"' in html
        assert 'class="c4-edge" data-id="e_1"' in html


def test_self_check_uses_represented_content_not_invented_dependencies():
    spec = _process_spec()
    interaction = spec.interactions[0]
    assert "each element depends" not in interaction.answer
    assert interaction.anchor_scene_index == len(spec.scenes)
    assert interaction.answer
