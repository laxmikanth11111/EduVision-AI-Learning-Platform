from __future__ import annotations

import pytest

from app.services.chunking_service import (
    ChunkingService,
    ChunkSourceUnit,
    detect_language,
)
from shared.constants import ChunkingStrategy


def _units(*items: tuple[str, str, int]) -> list[ChunkSourceUnit]:
    return [
        ChunkSourceUnit(block_type=block_type, content=content, position=position)
        for block_type, content, position in items
    ]


def _long_text(paragraphs: int = 12, words_per_paragraph: int = 60) -> str:
    return "\n\n".join(
        " ".join(f"word{paragraph}_{word}" for word in range(words_per_paragraph))
        for paragraph in range(paragraphs)
    )


class TestDetectLanguage:
    def test_english_default(self) -> None:
        assert detect_language("The quick brown fox jumps over the lazy dog.") == "en"

    def test_cjk_detection(self) -> None:
        assert detect_language("你好世界 这是一个测试") == "zh"

    def test_cyrillic_detection(self) -> None:
        assert detect_language("Привет мир это тест") == "ru"

    def test_arabic_detection(self) -> None:
        assert detect_language("مرحبا بالعالم هذا اختبار") == "ar"

    def test_hangul_detection(self) -> None:
        assert detect_language("안녕하세요 이것은 테스트입니다") == "ko"

    def test_empty_text(self) -> None:
        assert detect_language("") == "en"


class TestParagraphStrategy:
    def test_one_chunk_per_paragraph(self) -> None:
        service = ChunkingService(strategy=ChunkingStrategy.PARAGRAPH.value)
        candidates = service.chunk(
            _units(
                ("paragraph", "First paragraph.", 0),
                ("paragraph", "Second paragraph.", 1),
                ("heading", "Ignored Heading", 2),
                ("paragraph", "Third paragraph.", 3),
            )
        )
        assert [c.content for c in candidates] == [
            "First paragraph.",
            "Second paragraph.",
            "Third paragraph.",
        ]

    def test_skip_empty_paragraphs(self) -> None:
        service = ChunkingService(strategy=ChunkingStrategy.PARAGRAPH.value)
        candidates = service.chunk(
            _units(
                ("paragraph", "   ", 0),
                ("paragraph", "Real content.", 1),
            )
        )
        assert [c.content for c in candidates] == ["Real content."]

    def test_long_paragraph_split(self) -> None:
        service = ChunkingService(
            strategy=ChunkingStrategy.PARAGRAPH.value, max_chunk_characters=100
        )
        candidates = service.chunk(_units(("paragraph", "x" * 250, 0)))
        assert len(candidates) == 3
        assert all(len(c.content) <= 100 for c in candidates)

    def test_hashes_and_counts_populated(self) -> None:
        service = ChunkingService(strategy=ChunkingStrategy.PARAGRAPH.value)
        candidate = service.chunk(
            _units(("paragraph", "Alpha content here.", 0))
        )[0]
        assert candidate.chunk_hash
        assert candidate.checksum
        assert len(candidate.chunk_hash) == 64
        assert candidate.character_count == len("Alpha content here.")
        assert candidate.token_count >= 1
        assert candidate.language == "en"

    def test_position_renumbered(self) -> None:
        service = ChunkingService(strategy=ChunkingStrategy.PARAGRAPH.value)
        candidates = service.chunk(
            _units(
                ("paragraph", "A", 5),
                ("paragraph", "B", 3),
            )
        )
        assert [c.position for c in candidates] == [0, 1]


class TestHeadingStrategy:
    def test_group_under_heading(self) -> None:
        service = ChunkingService(strategy=ChunkingStrategy.HEADING.value)
        candidates = service.chunk(
            _units(
                ("heading", "Introduction", 0),
                ("paragraph", "Body one.", 1),
                ("paragraph", "Body two.", 2),
                ("heading", "Conclusion", 3),
                ("paragraph", "Wrap up.", 4),
            )
        )
        assert len(candidates) == 2
        assert candidates[0].title == "Introduction"
        assert candidates[0].heading_path == ["Introduction"]
        assert "Body one." in candidates[0].content
        assert "Body two." in candidates[0].content
        assert candidates[1].title == "Conclusion"

    def test_content_before_first_heading(self) -> None:
        service = ChunkingService(strategy=ChunkingStrategy.HEADING.value)
        candidates = service.chunk(
            _units(
                ("paragraph", "Preamble.", 0),
                ("heading", "Main", 1),
                ("paragraph", "Detail.", 2),
            )
        )
        assert len(candidates) == 2
        assert candidates[0].title is None
        assert candidates[0].content == "Preamble."

    def test_heading_without_body_skipped(self) -> None:
        service = ChunkingService(strategy=ChunkingStrategy.HEADING.value)
        candidates = service.chunk(_units(("heading", "Lonely", 0)))
        assert candidates == []


class TestSemanticStrategy:
    def test_merges_paragraphs_up_to_chunk_size(self) -> None:
        service = ChunkingService(
            strategy=ChunkingStrategy.SEMANTIC.value, chunk_size=120
        )
        candidates = service.chunk(
            _units(
                ("heading", "Section", 0),
                ("paragraph", "a" * 80, 1),
                ("paragraph", "b" * 80, 2),
            )
        )
        assert len(candidates) == 2
        assert candidates[0].content == "a" * 80
        assert candidates[0].title == "Section"
        assert candidates[1].content == "b" * 80

    def test_headings_anchor_heading_path(self) -> None:
        service = ChunkingService(strategy=ChunkingStrategy.SEMANTIC.value)
        candidates = service.chunk(
            _units(
                ("h1", "Chapter 1", 0),
                ("paragraph", "Intro text.", 1),
                ("h2", "Section 1.1", 2),
                ("paragraph", "Detail text.", 3),
            )
        )
        second = candidates[-1]
        assert second.heading_path == ["Chapter 1", "Section 1.1"]

    def test_sibling_headings_replace_path(self) -> None:
        service = ChunkingService(strategy=ChunkingStrategy.SEMANTIC.value)
        candidates = service.chunk(
            _units(
                ("h1", "Chapter 1", 0),
                ("paragraph", "Intro text.", 1),
                ("h1", "Chapter 2", 2),
                ("paragraph", "More text.", 3),
            )
        )
        assert candidates[-1].heading_path == ["Chapter 2"]

    def test_deterministic_output(self) -> None:
        service = ChunkingService(strategy=ChunkingStrategy.SEMANTIC.value)
        text = _long_text()
        units = _units(
            ("heading", "Overview", 0),
            *[("paragraph", text, index + 1) for index in range(5)],
        )
        first = service.chunk(units)
        second = service.chunk(units)
        assert [c.chunk_hash for c in first] == [c.chunk_hash for c in second]


class TestSlidingStrategy:
    def test_single_window_when_short(self) -> None:
        service = ChunkingService(strategy=ChunkingStrategy.SLIDING.value)
        candidates = service.chunk(_units(("paragraph", "Short content.", 0)))
        assert len(candidates) == 1
        assert candidates[0].chunk_type == "sliding"

    def test_multiple_windows_with_overlap(self) -> None:
        service = ChunkingService(
            strategy=ChunkingStrategy.SLIDING.value,
            chunk_size=200,
            chunk_overlap=40,
        )
        text = "Sentence one is here. " * 30
        candidates = service.chunk(_units(("paragraph", text, 0)))
        assert len(candidates) > 1
        assert all(len(c.content) <= 200 for c in candidates)

    def test_no_overlap_when_disabled(self) -> None:
        service = ChunkingService(
            strategy=ChunkingStrategy.SLIDING.value,
            chunk_size=200,
            chunk_overlap=0,
        )
        text = "Sentence one is here. " * 30
        candidates = service.chunk(_units(("paragraph", text, 0)))
        assert len(candidates) > 1


class TestChunkSourceUnit:
    def test_heading_variants(self) -> None:
        assert ChunkSourceUnit("h1", "Title", 0).is_heading
        assert ChunkSourceUnit("heading", "Title", 0).is_heading
        assert not ChunkSourceUnit("paragraph", "Body", 0).is_heading
        assert not ChunkSourceUnit("code", "x = 1", 0).is_heading

    def test_effective_heading(self) -> None:
        assert ChunkSourceUnit("heading", "  ", 0, heading="Real Title").effective_heading == "Real Title"
        assert ChunkSourceUnit("heading", "Inline", 0).effective_heading == "Inline"
