"""Unit tests for EduVision 2.0 Checkpoint C4 — Animation Specification
Generator (deterministic derivation from C3 base specifications)."""

import pytest

from app.schemas.c3_visual_intelligence import C3VisualType
from app.schemas.c4_animation_intelligence import (
    AnimationSpecification,
    AnimationStepKind,
    C4AnimationType,
)
from app.services.c4_animation_spec_generator import (
    build_animation_explanation,
    generate_animation_specification,
)


def _base_flowchart() -> dict:
    return {
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
    }


def _base_comparison() -> dict:
    return {
        "visual_type": "comparison",
        "title": "OSI vs TCP/IP",
        "columns": [
            {
                "header": "OSI",
                "items": ["7 layers", "Layer separation", "Separate session"],
            },
            {
                "header": "TCP/IP",
                "items": ["4 layers", "Merged processing", "No session layer"],
            },
        ],
    }


def _base_state() -> dict:
    return {
        "visual_type": "state_diagram",
        "title": "Connection states",
        "nodes": [
            {"id": "state_0", "label": "LISTEN", "node_type": "state"},
            {"id": "state_1", "label": "ESTABLISHED", "node_type": "state"},
            {"id": "state_2", "label": "CLOSED", "node_type": "state"},
        ],
        "edges": [
            {"id": "e_1", "source_id": "state_0", "target_id": "state_1", "label": "transition"},
            {"id": "e_2", "source_id": "state_1", "target_id": "state_2", "label": "transition"},
        ],
    }


def _base_timeline_steps() -> dict:
    return {
        "visual_type": "timeline",
        "title": "Ethernet evolution",
        "steps": [
            {"step_number": 1, "title": "10 Mbps", "description": "coaxial"},
            {"step_number": 2, "title": "100 Mbps", "description": "twisted pair"},
            {"step_number": 3, "title": "1 Gbps", "description": "structured cabling"},
        ],
    }


class TestC4SpecGenerator:
    def test_c4_gen_01_process_sequence_deterministic_and_valid(self):
        spec = generate_animation_specification(
            _base_flowchart(),
            C4AnimationType.PROCESS_SEQUENCE,
            "The TCP Handshake",
            base_visual_type=C3VisualType.FLOWCHART,
        )
        assert isinstance(spec, AnimationSpecification)
        assert spec.animation_type == C4AnimationType.PROCESS_SEQUENCE
        assert spec.scenes[0].steps[0].kind == AnimationStepKind.REVEAL
        assert spec.scenes[0].steps[0].node_ids == ["start"]
        assert spec.total_duration_ms >= 1500
        # Deterministic: same inputs -> identical spec
        again = generate_animation_specification(
            _base_flowchart(),
            C4AnimationType.PROCESS_SEQUENCE,
            "The TCP Handshake",
            base_visual_type=C3VisualType.FLOWCHART,
        )
        assert again.model_dump() == spec.model_dump()

    def test_c4_gen_02_only_allowed_kinds_emitted(self):
        spec = generate_animation_specification(
            _base_flowchart(),
            C4AnimationType.PROCESS_SEQUENCE,
            "The TCP Handshake",
        )
        allowed = {
            AnimationStepKind.REVEAL,
            AnimationStepKind.HIGHLIGHT,
            AnimationStepKind.ANNOTATE,
            AnimationStepKind.FADE_OUT,
            AnimationStepKind.PAUSE,
        }
        for scene in spec.scenes:
            for step in scene.steps:
                assert step.kind in allowed

    def test_c4_gen_03_comparison_derives_column_nodes(self):
        spec = generate_animation_specification(
            _base_comparison(),
            C4AnimationType.COMPARISON_REVEAL,
            "OSI vs TCP/IP",
            base_visual_type=C3VisualType.COMPARISON,
        )
        node_ids = {n.id for n in spec.nodes}
        assert node_ids == {"col_a", "col_b"}
        assert len(spec.scenes) == 2
        assert spec.scenes[1].steps[0].kind == AnimationStepKind.HIGHLIGHT

    def test_c4_gen_04_state_transition_builds_transforms(self):
        spec = generate_animation_specification(
            _base_state(),
            C4AnimationType.STATE_TRANSITION,
            "Connection States",
            base_visual_type=C3VisualType.STATE_DIAGRAM,
        )
        kinds = {step.kind for scene in spec.scenes for step in scene.steps}
        assert AnimationStepKind.TRANSFORM in kinds

    def test_c4_gen_05_timeline_derives_milestones_from_steps(self):
        spec = generate_animation_specification(
            _base_timeline_steps(),
            C4AnimationType.TIMELINE_PROGRESS,
            "Ethernet Evolution",
            base_visual_type=C3VisualType.TIMELINE,
        )
        assert [n.id for n in spec.nodes] == ["milestone_0", "milestone_1", "milestone_2"]
        assert spec.total_duration_ms >= 1500

    def test_c4_gen_06_node_overflow_is_bounded(self):
        big = _base_flowchart()
        big["nodes"] = [{"id": f"n_{i}", "label": f"Nodo {i}"} for i in range(40)]
        big["edges"] = [
            {"id": f"e_{i}", "source_id": f"n_{i}", "target_id": f"n_{i + 1}"} for i in range(30)
        ]
        spec = generate_animation_specification(big, C4AnimationType.NETWORK_FLOW, "Big Network")
        assert len(spec.nodes) <= 14
        # Not empty and fully valid despite capped content
        assert spec.total_duration_ms >= 1500

    def test_c4_gen_07_empty_base_rejected(self):
        with pytest.raises(ValueError, match="empty base"):
            generate_animation_specification({}, C4AnimationType.PROCESS_SEQUENCE, "Empty")

    def test_c4_gen_08_single_column_comparison_rejected(self):
        with pytest.raises(ValueError, match="at least two columns"):
            generate_animation_specification(
                {
                    "visual_type": "comparison",
                    "title": "Mono",
                    "columns": [{"header": "Only", "items": ["x"]}],
                },
                C4AnimationType.COMPARISON_REVEAL,
                "Mono",
            )

    def test_c4_gen_09_spec_validates_fully(self):
        spec = generate_animation_specification(
            _base_state(),
            C4AnimationType.STATE_TRANSITION,
            "Connection States",
            source_references=[{"slide_number": 4}],
            concept_ids=["tcp", "state"],
        )
        roundtrip = AnimationSpecification.model_validate(spec.model_dump())
        assert roundtrip == spec
        assert len(roundtrip.interactions) >= 1

    def test_c4_gen_10_walk_highlights_follow_first_reveal(self):
        spec = generate_animation_specification(
            _base_flowchart(),
            C4AnimationType.PROCESS_SEQUENCE,
            "The TCP Handshake",
        )
        reveal_scenes = [s for s in spec.scenes if "step by step" in s.title.lower()]
        walk_scenes = [s for s in spec.scenes if "walk through" in s.title.lower()]
        assert reveal_scenes
        assert walk_scenes

    def test_c4_gen_11_explanation_panel_content(self):
        spec = generate_animation_specification(
            _base_comparison(),
            C4AnimationType.COMPARISON_REVEAL,
            "OSI vs TCP/IP",
        )
        expl = build_animation_explanation(C4AnimationType.COMPARISON_REVEAL, spec, "OSI vs TCP/IP")
        assert set(expl) == {
            "what_you_see",
            "how_to_read",
            "key_takeaway",
            "motion_justification",
        }
        assert "OSI vs TCP/IP" in expl["what_you_see"]
