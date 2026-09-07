"""Unit tests for EduVision 2.0 Checkpoint C3 — Visual Specification Generation."""

import pytest

from app.schemas.c3_visual_intelligence import C3VisualType
from app.schemas.topic_outline import Concept, OutlineTopic, SourceReference, Subtopic
from app.services.c3_visual_spec_generator import generate_visual_specification


def _make_topic(title="OAuth 2.0 Authorization Flow"):
    return OutlineTopic(
        title=title,
        slide_ranges=[1, 4],
        section="Security",
        source_order=1,
        learning_order=1,
        source_references=[
            SourceReference(slide_number=1, preview="Authorization code flow overview"),
            SourceReference(slide_number=3, preview="Token refresh mechanics"),
        ],
        subtopics=[
            Subtopic(
                title="Authorization Code Flow",
                learning_order=1,
                source_references=[SourceReference(slide_number=2, preview="Flow steps")],
                concepts=[
                    Concept(name="Resource Owner", description="The user who grants access"),
                    Concept(name="Client", description="The application requesting access"),
                    Concept(name="Authorization Server", description="Issues tokens"),
                    Concept(name="Redirect URI", description="Callback destination"),
                ],
                learning_objectives=["Explain the authorization code exchange"],
                examples=[],
                misconceptions=[],
            )
        ],
        concepts=[
            Concept(name="Access Token", description="Short-lived credential"),
            Concept(name="Refresh Token", description="Long-lived renewal credential"),
        ],
    )


class TestC3SpecGenerator:
    def test_c3_spec_01_process_spec_generation(self):
        topic = _make_topic()
        spec = generate_visual_specification(topic, visual_type=C3VisualType.SEQUENCE_DIAGRAM)
        assert spec.visual_type == C3VisualType.SEQUENCE_DIAGRAM
        assert spec.title
        assert spec.purpose
        assert len(spec.steps) >= 2
        assert spec.steps[0].step_number == 1

    def test_c3_spec_02_comparison_spec_has_columns(self):
        topic = _make_topic(title="TCP vs UDP")
        spec = generate_visual_specification(topic, visual_type=C3VisualType.COMPARISON)
        assert spec.visual_type == C3VisualType.COMPARISON
        assert len(spec.columns) >= 2
        for col in spec.columns:
            assert col.header
            assert isinstance(col.items, list)

    def test_c3_spec_03_hierarchy_spec_uses_concepts(self):
        topic = _make_topic(title="ISO/OSI Model")
        spec = generate_visual_specification(topic, visual_type=C3VisualType.HIERARCHY)
        assert spec.visual_type == C3VisualType.HIERARCHY
        # Root node + one child per topic concept
        assert len(spec.nodes) == 1 + len(topic.concepts)
        assert len(spec.edges) == len(topic.concepts)

    def test_c3_spec_04_step_by_step_has_numbered_steps(self):
        topic = _make_topic(title="TLS Handshake")
        spec = generate_visual_specification(topic, visual_type=C3VisualType.STEP_BY_STEP)
        assert len(spec.steps) >= 2
        nums = [s.step_number for s in spec.steps]
        assert nums == sorted(nums)
        assert all(s.title for s in spec.steps)

    def test_c3_spec_05_learning_objective_extracted(self):
        topic = _make_topic()
        subtopic = topic.subtopics[0]
        spec = generate_visual_specification(
            topic, subtopic=subtopic, visual_type=C3VisualType.CONCEPT_MAP
        )
        assert spec.learning_objective == "Explain the authorization code exchange"

    def test_c3_spec_06_fallback_type_defaults_to_concept_map(self):
        topic = _make_topic()
        spec = generate_visual_specification(topic)
        assert spec.visual_type == C3VisualType.CONCEPT_MAP
        assert spec.nodes

    def test_c3_spec_07_table_spec_labels(self):
        topic = _make_topic(title="HTTP Status Codes")
        spec = generate_visual_specification(topic, visual_type=C3VisualType.TABLE_VISUALIZATION)
        assert spec.visual_type == C3VisualType.TABLE_VISUALIZATION
        assert len(spec.columns) >= 1
