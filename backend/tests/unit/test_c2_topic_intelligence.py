"""Unit and integration tests for EduVision 2.0 Checkpoint C2:
Topic / Subtopic Learning Intelligence & Deep Content Structuring.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.exceptions import NotFoundError
from app.models.content_block import ContentBlock
from app.models.content_unit import ContentUnit
from app.models.presentation import Presentation
from app.models.topic_outline import TopicOutline
from app.schemas.topic_outline import (
    Concept,
    OutlineSection,
    OutlineTopic,
    Subtopic,
    TopicOutlinePayload,
)
from app.services.presentation_service import PresentationService
from app.services.topic_outline_service import TopicOutlineService


def _create_mock_presentation(pres_id=None, owner_id=None, total_slides=4):
    pres = MagicMock(spec=Presentation)
    pres.id = pres_id or uuid4()
    pres.public_id = f"pres_{uuid4().hex[:12]}"
    pres.owner_id = owner_id or uuid4()
    pres.title = "Computer Networks: Foundations & Architectures"
    pres.file_name = "computer_networks.pptx"
    pres.total_slides = total_slides
    return pres


def _create_sample_content_units(presentation_id):
    u1 = ContentUnit(
        id=uuid4(),
        public_id=f"unit_{uuid4().hex[:12]}",
        presentation_id=presentation_id,
        position=1,
        unit_type="slide",
        title="Introduction to Computer Networks",
        raw_text="A computer network connects autonomous computing devices to exchange data and share resources.",
        meta={},
    )
    u1.blocks = [
        ContentBlock(
            id=uuid4(),
            public_id=f"block_{uuid4().hex[:12]}",
            content_unit_id=u1.id,
            block_type="paragraph",
            content="A computer network connects autonomous computing devices to exchange data and share resources.",
            position=0,
            meta={},
        ),
        ContentBlock(
            id=uuid4(),
            public_id=f"block_{uuid4().hex[:12]}",
            content_unit_id=u1.id,
            block_type="bullet",
            content="Primary goal: Resource sharing (printers, storage, compute)",
            position=1,
            meta={"level": 0},
        ),
    ]

    u2 = ContentUnit(
        id=uuid4(),
        public_id=f"unit_{uuid4().hex[:12]}",
        presentation_id=presentation_id,
        position=2,
        unit_type="slide",
        title="Network Types by Scale",
        raw_text="Networks are categorized by geographic scale: LAN, MAN, and WAN.",
        meta={},
    )
    u2.blocks = [
        ContentBlock(
            id=uuid4(),
            public_id=f"block_{uuid4().hex[:12]}",
            content_unit_id=u2.id,
            block_type="bullet",
            content="Local Area Network (LAN): Confined to a single room, building, or campus with high data rates and low latency.",
            position=0,
            meta={"level": 0},
        ),
        ContentBlock(
            id=uuid4(),
            public_id=f"block_{uuid4().hex[:12]}",
            content_unit_id=u2.id,
            block_type="bullet",
            content="Metropolitan Area Network (MAN): Spans an entire city or metropolitan region.",
            position=1,
            meta={"level": 0},
        ),
        ContentBlock(
            id=uuid4(),
            public_id=f"block_{uuid4().hex[:12]}",
            content_unit_id=u2.id,
            block_type="bullet",
            content="Wide Area Network (WAN): Spans countries or continents (e.g., the global Internet).",
            position=2,
            meta={"level": 0},
        ),
        ContentBlock(
            id=uuid4(),
            public_id=f"block_{uuid4().hex[:12]}",
            content_unit_id=u2.id,
            block_type="table",
            content="Network Scale Comparison Table",
            position=3,
            meta={
                "table_data": [
                    ["Type", "Coverage", "Speed"],
                    ["LAN", "Building", "1-10 Gbps"],
                    ["WAN", "Global", "100-1000 Mbps"],
                ]
            },
        ),
        ContentBlock(
            id=uuid4(),
            public_id=f"block_{uuid4().hex[:12]}",
            content_unit_id=u2.id,
            block_type="note",
            content="Common mistake: Students often confuse LAN with Wi-Fi. Wi-Fi is a wireless transmission medium (IEEE 802.11), not a network scale category.",
            position=4,
            meta={},
        ),
    ]

    u3 = ContentUnit(
        id=uuid4(),
        public_id=f"unit_{uuid4().hex[:12]}",
        presentation_id=presentation_id,
        position=3,
        unit_type="slide",
        title="Protocol Architecture & OSI Model",
        raw_text="Layered protocol architectures separate networking concerns into modular abstractions.",
        meta={},
    )
    u3.blocks = [
        ContentBlock(
            id=uuid4(),
            public_id=f"block_{uuid4().hex[:12]}",
            content_unit_id=u3.id,
            block_type="bullet",
            content="OSI 7-Layer Reference Model: Physical, Data Link, Network, Transport, Session, Presentation, Application.",
            position=0,
            meta={"level": 0},
        ),
        ContentBlock(
            id=uuid4(),
            public_id=f"block_{uuid4().hex[:12]}",
            content_unit_id=u3.id,
            block_type="bullet",
            content="Encapsulation: Headers are appended at each descending layer during transmission.",
            position=1,
            meta={"level": 1},
        ),
    ]

    u4 = ContentUnit(
        id=uuid4(),
        public_id=f"unit_{uuid4().hex[:12]}",
        presentation_id=presentation_id,
        position=4,
        unit_type="slide",
        title="TCP/IP Model & Internet Architecture",
        raw_text="The pragmatic 4-layer model governing the modern Internet.",
        meta={},
    )
    u4.blocks = [
        ContentBlock(
            id=uuid4(),
            public_id=f"block_{uuid4().hex[:12]}",
            content_unit_id=u4.id,
            block_type="bullet",
            content="Four Layers: Link, Internet (IP), Transport (TCP/UDP), Application (HTTP, DNS).",
            position=0,
            meta={"level": 0},
        ),
    ]

    return [u1, u2, u3, u4]


class TestC2TopicIntelligence:
    """Test suite for Checkpoint C2 educational intelligence requirements."""

    def test_c2_01_deterministic_fallback_full_hierarchy(self):
        """Test C2-01 through C2-05: deterministic fallback builds a deep, grounded learning hierarchy."""
        pres = _create_mock_presentation()
        units = _create_sample_content_units(pres.id)

        mock_uow = MagicMock()
        service = TopicOutlineService(uow=mock_uow)
        fallback_payload = service._deterministic_fallback(units, pres)

        assert isinstance(fallback_payload, TopicOutlinePayload)
        assert fallback_payload.structure_version == 2
        assert len(fallback_payload.sections) > 0

        # Verify sections -> topics -> subtopics -> concepts
        assert len(fallback_payload.sections) > 0
        assert len(fallback_payload.topics) >= 3
        all_topics = fallback_payload.topics

        assert len(all_topics) >= 3
        # Topic 2: Network Types by Scale
        net_types_topic = next((t for t in all_topics if "Scale" in t.title or "Types" in t.title), None)
        assert net_types_topic is not None
        assert len(net_types_topic.subtopics) >= 2

        # Subtopics must have concepts
        lan_subtopic = next((st for st in net_types_topic.subtopics if "LAN" in st.title or "Local" in st.title), None)
        assert lan_subtopic is not None
        assert len(lan_subtopic.concepts) > 0
        assert any("scope" in (c.description or "").lower() or "speed" in (c.description or "").lower() or "latency" in (c.description or "").lower() for c in lan_subtopic.concepts)

        # Source grounding check
        assert len(net_types_topic.source_references) > 0
        assert any(ref.slide_number == 2 for ref in net_types_topic.source_references)

    def test_c2_02_source_provenance_and_references(self):
        """Test C2-10: every node in the hierarchy is traceable to uploaded slides."""
        pres = _create_mock_presentation()
        units = _create_sample_content_units(pres.id)

        mock_uow = MagicMock()
        service = TopicOutlineService(uow=mock_uow)
        payload = service._deterministic_fallback(units, pres)

        for topic in payload.topics:
            assert len(topic.source_references) > 0
            for ref in topic.source_references:
                assert ref.slide_number in [1, 2, 3, 4]
                assert ref.unit_id is not None

    def test_c2_03_source_ai_separation_and_misconceptions(self):
        """Test C2-07 & C2-12: speaker notes and educational guidance are separated with AI provenance tags."""
        pres = _create_mock_presentation()
        units = _create_sample_content_units(pres.id)

        mock_uow = MagicMock()
        service = TopicOutlineService(uow=mock_uow)
        payload = service._deterministic_fallback(units, pres)

        # Look for the speaker note extracted misconception on slide 2
        net_types_topic = next(t for t in payload.topics if "Scale" in t.title or "Types" in t.title)
        has_misconception = False
        for st in net_types_topic.subtopics:
            if st.misconceptions:
                for m in st.misconceptions:
                    has_misconception = True
                    assert m.is_ai_inferred is False  # Source-derived from speaker notes
                    assert "wi-fi" in m.statement.lower() or "wi-fi" in m.correction.lower()
        assert has_misconception, "Misconception from speaker notes should be parsed and preserved with source fidelity"

    def test_c2_04_deduplication_of_repeated_topics(self):
        """Test C2-17: normalization merges duplicate or repeated headings."""
        pres = _create_mock_presentation()
        u1 = ContentUnit(id=uuid4(), presentation_id=pres.id, position=1, unit_type="slide", title="Network Types", raw_text="Overview of types.", meta={})
        u1.blocks = []
        u2 = ContentUnit(id=uuid4(), presentation_id=pres.id, position=2, unit_type="slide", title="Network Types", raw_text="Deep dive into types.", meta={})
        u2.blocks = []
        u3 = ContentUnit(id=uuid4(), presentation_id=pres.id, position=3, unit_type="slide", title="Types of Networks", raw_text="Summary of types.", meta={})
        u3.blocks = []

        mock_uow = MagicMock()
        service = TopicOutlineService(uow=mock_uow)
        # Simulate unnormalized AI payload with 3 near-duplicate topics
        raw_payload = TopicOutlinePayload(
            title="Computer Networks",
            structure_version=2,
            sections=[
                OutlineSection(
                    title="Fundamentals",
                    topic_titles=["Network Types", "Types of Networks"],
                    slide_ranges=[1, 3],
                )
            ],
            topics=[
                OutlineTopic(title="Network Types", description="Part 1", slide_ranges=[1, 1]),
                OutlineTopic(title="Network Types", description="Part 2", slide_ranges=[2, 2]),
                OutlineTopic(title="Types of Networks", description="Part 3", slide_ranges=[3, 3]),
            ],
        )

        normalized = service._normalize_and_deduplicate(raw_payload, units=[u1, u2, u3])
        assert len(normalized) == 1
        assert normalized[0]["slide_ranges"] == [1, 3]

    def test_c2_05_small_document_handling(self):
        """Test C2-15: 1-slide and 2-slide documents are handled gracefully without failing."""
        pres = _create_mock_presentation(total_slides=1)
        u1 = ContentUnit(
            id=uuid4(),
            public_id=f"unit_{uuid4().hex[:12]}",
            presentation_id=pres.id,
            position=1,
            unit_type="slide",
            title="Single Slide Presentation",
            raw_text="Quantum Computing uses qubits.",
            meta={},
        )
        u1.blocks = [
            ContentBlock(
                id=uuid4(),
                public_id=f"block_{uuid4().hex[:12]}",
                content_unit_id=u1.id,
                block_type="bullet",
                content="Qubits exhibit superposition and entanglement.",
                position=0,
                meta={},
            )
        ]

        mock_uow = MagicMock()
        service = TopicOutlineService(uow=mock_uow)
        payload = service._deterministic_fallback([u1], pres)
        assert len(payload.topics) == 1
        assert payload.topics[0].title == "Single Slide Presentation"
        assert payload.topics[0].slide_ranges == [1, 1]

    def test_c2_06_backward_compatibility_with_legacy_schema(self):
        """Test C2-18 & C2-26: legacy callers expecting title and slide_ranges work seamlessly."""
        topic = OutlineTopic(
            title="Protocol Architecture",
            slide_ranges=[3, 4],
            description="OSI and TCP/IP protocol stacks.",
            subtopics=[
                Subtopic(title="OSI Model", concepts=[Concept(name="7-Layers")])
            ],
        )

        # Standard legacy attributes
        assert topic.title == "Protocol Architecture"
        assert topic.slide_ranges == [3, 4]
        assert hasattr(topic, "subtopics")
        assert topic.subtopics[0].title == "OSI Model"

    @pytest.mark.asyncio
    async def test_c2_07_persistence_and_regeneration_safety(self):
        """Test C2-18 & C2-22: learning structure is safely persisted and regenerated."""
        mock_uow = MagicMock()
        mock_uow.session = AsyncMock()
        mock_uow.commit = AsyncMock()
        mock_uow.flush = AsyncMock()

        mock_outline_repo = MagicMock()
        mock_content_repo = MagicMock()

        pres = _create_mock_presentation()
        units = _create_sample_content_units(pres.id)

        mock_content_repo.list_for_presentation = AsyncMock(return_value=units)
        mock_outline_repo.get_by_presentation_id = AsyncMock(return_value=None)
        mock_outline_repo.create_for_presentation = AsyncMock(side_effect=lambda pres_id, **kwargs: TopicOutline(
            id=uuid4(),
            presentation_id=pres.id,
            topics=kwargs["topics"],
            title=kwargs["title"],
            status="succeeded",
        ))

        service = TopicOutlineService(uow=mock_uow)
        service._repo = mock_outline_repo
        service._content_repo = mock_content_repo
        # Mock AI failure to trigger deterministic fallback
        service._ai.generate = AsyncMock(side_effect=Exception("AI Quota Exceeded"))

        res = await service.regenerate(presentation=pres)
        assert res is not None
        assert res.get("status") == "succeeded"
        assert res.get("structure_version") == 2
        assert len(res.get("topics", [])) >= 3
        mock_outline_repo.create_for_presentation.assert_called_once()

    @pytest.mark.asyncio
    async def test_c2_08_cross_user_isolation(self):
        """Test C2-19 & C2-32: User B cannot access User A's presentation outline."""
        mock_uow = MagicMock()
        service = PresentationService(uow=mock_uow)
        service._repo = MagicMock()

        owner_a = uuid4()
        user_b = uuid4()
        pres_a = _create_mock_presentation(owner_id=owner_a)

        service._repo.get_by_public_id_or_raise = AsyncMock(return_value=pres_a)

        # Owner A accessing their own presentation succeeds
        owned = await service.assert_ownership(pres_a.public_id, owner_a)
        assert owned.id == pres_a.id

        # User B attempting to access User A's presentation raises NotFoundError
        with pytest.raises(NotFoundError):
            await service.assert_ownership(pres_a.public_id, user_b)
