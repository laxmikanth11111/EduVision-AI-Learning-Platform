"""Unit tests for EduVision 2.0 Checkpoint C3 — Visual Need Analysis."""

import pytest

from app.schemas.c3_visual_intelligence import (
    C3VisualType,
    VisualNeedDecision,
    compute_visual_fingerprint,
)
from app.services.c3_visual_need_analyzer import analyze_visual_need


class TestC3VisualNeedAnalyzer:
    def test_c3_need_01_process_content_needs_visual(self):
        decision = analyze_visual_need(
            topic_title="Understanding the TCP Handshake",
            topic_content=(
                "The TCP three-way handshake is a process with sequential steps: "
                "the client sends a SYN packet, the server replies with SYN-ACK, "
                "and finally the client acknowledges with an ACK. This connection "
                "establishment procedure is important for reliable data transfer."
            ),
        )
        assert decision.visual_needed is True
        assert decision.confidence >= 0.3
        assert decision.suggested_type in (
            C3VisualType.SEQUENCE_DIAGRAM,
            C3VisualType.PROCESS_DIAGRAM,
            C3VisualType.FLOWCHART,
        )

    def test_c3_need_02_comparison_content_detected(self):
        decision = analyze_visual_need(
            topic_title="LAN vs WAN",
            topic_content=(
                "Compare LAN and WAN: local area networks cover small geographic areas "
                "while wide area networks span cities and countries. The differences "
                "between these network types matter for planning infrastructure."
            ),
        )
        assert decision.visual_needed is True
        assert decision.suggested_type == C3VisualType.COMPARISON

    def test_c3_need_03_short_content_skipped(self):
        decision = analyze_visual_need(
            topic_title="Introduction",
            topic_content="Brief.",
        )
        assert decision.visual_needed is False
        assert decision.skip_reason is not None

    def test_c3_need_04_text_preferred_content_skipped(self):
        decision = analyze_visual_need(
            topic_title="Appendix: References",
            topic_content=(
                "This appendix lists the bibliographic references and citations used "
                "throughout the course material for further reading and study."
            ),
        )
        assert decision.visual_needed is False

    def test_c3_need_05_hierarchy_detection(self):
        decision = analyze_visual_need(
            topic_title="Network Topology",
            topic_content=(
                "Network typologies form a hierarchical classification tree: "
                "there are parent and child categories, and the levels group "
                "shared properties across the taxonomy."
            ),
        )
        assert decision.visual_needed is True
        assert decision.suggested_type == C3VisualType.HIERARCHY

    def test_c3_need_06_concepts_influence_relationship_choice(self):
        concepts = [
            {"name": "Client", "description": "initiates connection"},
            {"name": "Server", "description": "listens for connections"},
            {"name": "Protocol", "description": "communication rules"},
            {"name": "Port", "description": "logical endpoint"},
            {"name": "Socket", "description": "network endpoint abstraction"},
        ]
        decision = analyze_visual_need(
            topic_title="Networking Components",
            topic_content=(
                "Networking involves several interconnected components that relate "
                "to one another. Multiple elements depend on and work with each other "
                "to enable communication across the system."
            ),
            concepts=concepts,
        )
        assert decision.visual_needed is True

    def test_c3_need_07_fallback_concept_map(self):
        decision = analyze_visual_need(
            topic_title="Distributed Systems Concepts",
            topic_content=(
                "Distributed systems involve multiple components that work together "
                "across a network. Several related elements coordinate and cooperate "
                "to provide a unified service for end users and applications."
            ),
            concepts=[
                {"name": "Node", "description": "a processing unit"},
                {"name": "Network", "description": "connects nodes"},
                {"name": "Protocol", "description": "governs exchange"},
            ],
        )
        assert decision.visual_needed is True
        assert isinstance(decision, VisualNeedDecision)
        assert 0.0 <= decision.confidence <= 1.0

    def test_c3_need_08_section_heading_fragment_skipped(self):
        decision = analyze_visual_need(
            topic_title="Network Types & Classifications",
            topic_content=(
                "Networks are categorized based on geographic scale and infrastructure: "
                "local, metropolitan, and wide area networks span different physical "
                "regions and rely on distinct infrastructure for connectivity."
            ),
            subtopic_title="Networks are categorized based on geographic scale and infrastructure:",
            subtopic_content=(
                "Networks are categorized based on geographic scale and infrastructure: "
                "local, metropolitan, and wide area networks span different physical "
                "regions and rely on distinct infrastructure for connectivity."
            ),
            concepts=[{"name": "Principles", "description": "categorization basis"}],
            source_references=[{"slide_number": 2, "preview": "types"}],
        )
        assert decision.visual_needed is False
        assert "heading" in decision.skip_reason.lower()


class TestC3Fingerprint:
    def test_c3_fingerprint_01_deterministic(self):
        fp1 = compute_visual_fingerprint("pres_1", "topic_a", "sub_1", ["c1", "c2"])
        fp2 = compute_visual_fingerprint("pres_1", "topic_a", "sub_1", ["c1", "c2"])
        assert fp1 == fp2
        assert len(fp1) == 32

    def test_c3_fingerprint_02_changes_with_inputs(self):
        fp1 = compute_visual_fingerprint("pres_1", "topic_a", "sub_1", ["c1", "c2"])
        fp2 = compute_visual_fingerprint("pres_1", "topic_a", "sub_1", ["c1", "c3"])
        assert fp1 != fp2
