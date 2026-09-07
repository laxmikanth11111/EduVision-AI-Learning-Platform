"""Unit tests for EduVision 2.0 Checkpoint C3 — Deterministic SVG Rendering."""

import pytest

from app.schemas.c3_visual_intelligence import (
    C3VisualType,
    VisualColumn,
    VisualEdge,
    VisualNode,
    VisualSpecification,
    VisualStep,
)
from app.services.c3_svg_renderer import render_visual


def _base_spec(vtype=C3VisualType.CONCEPT_MAP):
    return VisualSpecification(
        visual_type=vtype,
        title="Sample Visual",
        purpose="Illustrate the structure",
        learning_objective="Understand the structure",
        nodes=[
            VisualNode(id="n1", label="Concept A", description="first"),
            VisualNode(id="n2", label="Concept B", description="second"),
        ],
        edges=[VisualEdge(id="e1", source_id="n1", target_id="n2", label="flows to")],
    )


class TestC3SVGRenderer:
    def test_c3_render_01_output_is_valid_svg(self):
        svg = render_visual(_base_spec())
        assert svg.startswith("<svg")
        assert "xmlns" in svg
        assert "</svg>" in svg
        assert "font-family" in svg

    def test_c3_render_02_deterministic_output(self):
        s1 = render_visual(_base_spec())
        s2 = render_visual(_base_spec())
        assert s1 == s2

    def test_c3_render_03_contains_expected_nodes(self):
        spec = _base_spec()
        svg = render_visual(spec)
        for node in spec.nodes:
            assert node.label in svg

    def test_c3_render_04_comparison_renders_columns(self):
        spec = VisualSpecification(
            visual_type=C3VisualType.COMPARISON,
            title="TCP vs UDP",
            purpose="Side-by-side comparison",
            columns=[
                VisualColumn(header="Feature", items=["Reliability", "Ordering"]),
                VisualColumn(header="TCP", items=["Guaranteed", "Ordered"]),
                VisualColumn(header="UDP", items=["Best effort", "Not ordered"]),
            ],
        )
        svg = render_visual(spec)
        assert "TCP" in svg
        assert "UDP" in svg
        assert "Reliability" in svg

    def test_c3_render_05_steps_rendered(self):
        spec = VisualSpecification(
            visual_type=C3VisualType.STEP_BY_STEP,
            title="TLS Handshake",
            purpose="Show ordered steps",
            steps=[
                VisualStep(step_number=1, title="ClientHello", description="Greeting"),
                VisualStep(step_number=2, title="ServerHello", description="Response"),
                VisualStep(step_number=3, title="Finished", description="Done"),
            ],
        )
        svg = render_visual(spec)
        assert "ClientHello" in svg
        assert "Finished" in svg

    def test_c3_render_06_empty_spec_still_renders(self):
        spec = VisualSpecification(
            visual_type=C3VisualType.CONCEPT_MAP,
            title="Empty",
            purpose="Edge case",
            nodes=[],
            edges=[],
        )
        svg = render_visual(spec)
        assert svg.startswith("<svg")
        assert "Empty" in svg

    def test_c3_render_07_type_dispatcher_covers_all_types(self):
        types_to_check = [
            C3VisualType.FLOWCHART,
            C3VisualType.PROCESS_DIAGRAM,
            C3VisualType.HIERARCHY,
            C3VisualType.TIMELINE,
            C3VisualType.CYCLE,
            C3VisualType.NETWORK_DIAGRAM,
            C3VisualType.ARCHITECTURE_DIAGRAM,
            C3VisualType.STATE_DIAGRAM,
        ]
        for t in types_to_check:
            svg = render_visual(_base_spec(vtype=t))
            assert svg.startswith("<svg"), f"type {t} failed to render"
            assert "</svg>" in svg
