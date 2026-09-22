"""Unit tests for EduVision 2.0 Checkpoint C4 — Animation Need Analysis."""

from app.schemas.c3_visual_intelligence import C3VisualType
from app.schemas.c4_animation_intelligence import (
    AnimationNeedDecision,
    C4AnimationType,
)
from app.services.c4_animation_need_analyzer import analyze_animation_need


class TestC4AnimationNeedAnalyzer:
    def test_c4_need_01_sequence_content_animates_process(self):
        decision = analyze_animation_need(
            topic_title="The TCP Handshake",
            topic_content=(
                "The TCP three-way handshake is a sequence of three ordered messages: "
                "the client sends a SYN, the server replies with a SYN-ACK, and finally "
                "the client acknowledges with an ACK. The order and pacing of these "
                "messages matters for reliable data transfer."
            ),
            base_visual_type=C3VisualType.SEQUENCE_DIAGRAM,
        )
        assert decision.animation_needed is True
        assert decision.suggested_type == C4AnimationType.PROCESS_SEQUENCE
        assert decision.base_visual_type == C3VisualType.SEQUENCE_DIAGRAM
        assert 0.0 <= decision.confidence <= 1.0

    def test_c4_need_02_comparison_animates_reveal(self):
        decision = analyze_animation_need(
            topic_title="OSI vs TCP/IP",
            topic_content=(
                "Compare the OSI seven-layer model and the TCP/IP four-layer model: "
                "their stacks are similar but differ in layer count, naming, and how "
                "functions such as routing and session control are distributed."
            ),
            base_visual_type=C3VisualType.COMPARISON,
        )
        assert decision.animation_needed is True
        assert decision.suggested_type == C4AnimationType.COMPARISON_REVEAL

    def test_c4_need_03_hierarchy_animates_zoom(self):
        decision = analyze_animation_need(
            topic_title="Network Classifications",
            topic_content=(
                "Networks are classified into a hierarchy of parent and child groups: "
                "personal area networks, local, metropolitan, and wide area networks, "
                "each level grouping shared properties of the level below."
            ),
            base_visual_type=C3VisualType.HIERARCHY,
        )
        assert decision.animation_needed is True
        assert decision.suggested_type == C4AnimationType.HIERARCHY_ZOOM

    def test_c4_need_04_state_machine_animates_transition(self):
        decision = analyze_animation_need(
            topic_title="Connection State Machine",
            topic_content=(
                "A TCP connection passes through several states: it is established, "
                "then changes to data transfer, and finally transitions through "
                "FIN-WAIT to CLOSED as the connection terminates."
            ),
            base_visual_type=C3VisualType.STATE_DIAGRAM,
        )
        assert decision.animation_needed is True
        assert decision.suggested_type == C4AnimationType.STATE_TRANSITION

    def test_c4_need_05_causal_language_prefers_cause_effect(self):
        decision = analyze_animation_need(
            topic_title="Packet Loss in Congestion",
            topic_content=(
                "When the network is congested, the router drops packets. This loss "
                "triggers the sender to retransmit, which propagates even more "
                "traffic and results in increased latency for every flow."
            ),
            base_visual_type=C3VisualType.NETWORK_DIAGRAM,
        )
        assert decision.animation_needed is True
        assert decision.suggested_type == C4AnimationType.CAUSE_EFFECT_CHAIN

    def test_c4_need_06_static_table_rejected(self):
        decision = analyze_animation_need(
            topic_title="IP Address Ranges",
            topic_content=(
                "Private IP address ranges are a table of reserved values: 10.0.0.0 "
                "to 10.255.255.255 for class A, 172.16.0.0 to 172.31.255.255 for "
                "class B, and 192.168.0.0 to 192.168.255.255 for class C. These "
                "ranges are used for local addressing."
            ),
            base_visual_type=C3VisualType.TABLE_VISUALIZATION,
        )
        assert decision.animation_needed is False
        assert decision.skip_reason is not None

    def test_c4_need_07_no_base_visual_rejected(self):
        decision = analyze_animation_need(
            topic_title="DNS Resolution",
            topic_content=(
                "DNS resolution looks up a domain name, following each step of the "
                "lookup chain from the root to the authoritative server."
            ),
            base_visual_type=None,
        )
        assert decision.animation_needed is False
        assert "foundation" in decision.skip_reason.lower()

    def test_c4_need_08_heading_fragment_rejected(self):
        decision = analyze_animation_need(
            topic_title="Physical infrastructure:",
            topic_content=(
                "Physical infrastructure: cables, switches, routers, and the actual "
                "hardware that connects machines together across buildings and cities."
            ),
            base_visual_type=C3VisualType.ARCHITECTURE_DIAGRAM,
        )
        assert decision.animation_needed is False
        assert "heading" in decision.skip_reason.lower()

    def test_c4_need_09_short_content_rejected(self):
        decision = analyze_animation_need(
            topic_title="Intro",
            topic_content="Brief.",
            base_visual_type=C3VisualType.SEQUENCE_DIAGRAM,
        )
        assert decision.animation_needed is False

    def test_c4_need_10_formula_rejected_as_static(self):
        decision = analyze_animation_need(
            topic_title="Subnet Mask Formula",
            topic_content=(
                "The subnet mask formula derives the number of hosts from the number "
                "of host bits: hosts equal two raised to the host bits minus two, "
                "illustrating how addressing scales with the prefix length."
            ),
            base_visual_type=C3VisualType.FORMULA_VISUALIZATION,
        )
        assert decision.animation_needed is False
        assert "static" in decision.skip_reason.lower()

    def test_c4_need_11_decision_is_instance_with_bounds(self):
        decision = analyze_animation_need(
            topic_title="Protocol Flow",
            topic_content=(
                "Protocols exchange messages in a fixed order: the client sends a "
                "request, the server processes it, and then the response traverses "
                "the same path back through the network to the client."
            ),
            base_visual_type=C3VisualType.NETWORK_DIAGRAM,
        )
        assert isinstance(decision, AnimationNeedDecision)
        assert 0.0 <= decision.confidence <= 1.0

    def test_c4_need_12_timeline_animates_progress(self):
        decision = analyze_animation_need(
            topic_title="Evolution of Ethernet",
            topic_content=(
                "Ethernet evolved chronologically: from 10 Mbps coaxial networks, "
                "through 100 Mbps and 1 Gbps twisted pair, to 10 Gbps and beyond; "
                "each generation reduced collision domains and raised throughput."
            ),
            base_visual_type=C3VisualType.TIMELINE,
        )
        assert decision.animation_needed is True
        assert decision.suggested_type == C4AnimationType.TIMELINE_PROGRESS


def test_causal_keywords_do_not_match_inside_unrelated_words():
    decision = analyze_animation_need(
        topic_title="Different network components",
        topic_content=(
            "Different network components include routers, switches and computers. "
            "Their classifications identify the equipment present in the network "
            "and describe its physical arrangement across the building."
        ),
        base_visual_type=C3VisualType.NETWORK_DIAGRAM,
    )
    assert decision.suggested_type == C4AnimationType.NETWORK_FLOW
