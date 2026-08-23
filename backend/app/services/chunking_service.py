"""Deterministic chunking engine (Phase 4E.1).

Converts normalized content units into ``ChunkCandidate`` records that the
worker layer persists as ``DocumentChunk`` rows. Every strategy is
deterministic — no AI calls, no randomness — so identical source content
always produces identical hashes, making change detection and incremental
re-indexing possible.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from app.ai.tokens import estimate_tokens
from shared.constants import ChunkingStrategy, ContentBlockType

_HEADING_RE = re.compile(r"^(h[1-6]|heading)$", re.IGNORECASE)
_HEADING_LEVEL_RE = re.compile(r"^h([1-6])$", re.IGNORECASE)
_SENTENCE_END_RE = re.compile(r"(?<=[.!?。！？…])\s+")
_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")
_HANGUL_RE = re.compile(r"[\uac00-\ud7af\u1100-\u11ff]")
_KANA_RE = re.compile(r"[\u3040-\u30ff]")
_CYRILLIC_RE = re.compile(r"[\u0400-\u04ff]")
_ARABIC_RE = re.compile(r"[\u0600-\u06ff]")
_DEVANAGARI_RE = re.compile(r"[\u0900-\u097f]")
_BENGALI_RE = re.compile(r"[\u0980-\u09ff]")
_GURMUKHI_RE = re.compile(r"[\u0a00-\u0a7f]")
_TAMIL_RE = re.compile(r"[\u0b80-\u0bff]")
_TELUGU_RE = re.compile(r"[\u0c00-\u0c7f]")
_THAI_RE = re.compile(r"[\u0e00-\u0e7f]")
_VIETNAMESE_RE = re.compile(r"[àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵ]")


def detect_language(text: str) -> str:
    """Detect a primary written language from character ranges.

    Returns an ISO-639-1 code from the supported dialect list; defaults to
    ``"en"`` when no dominant non-Latin script is present.
    """
    if not text:
        return "en"

    detectors = (
        ("ko", _HANGUL_RE),
        ("ja", _KANA_RE),
        ("zh", _CJK_RE),
        ("ru", _CYRILLIC_RE),
        ("ar", _ARABIC_RE),
        ("hi", _DEVANAGARI_RE),
        ("bn", _BENGALI_RE),
        ("pa", _GURMUKHI_RE),
        ("ta", _TAMIL_RE),
        ("te", _TELUGU_RE),
        ("th", _THAI_RE),
        ("vi", _VIETNAMESE_RE),
    )
    scores: dict[str, int] = {}
    for lang, pattern in detectors:
        count = len(pattern.findall(text))
        if count:
            scores[lang] = count
    if not scores:
        return "en"
    return max(scores, key=lambda lang: scores[lang])


def _normalize_text(content: str) -> str:
    return re.sub(r"\s+", " ", content).strip()


def _content_hash(content: str) -> str:
    return hashlib.sha256(_normalize_text(content).encode("utf-8")).hexdigest()


def _checksum(
    content: str,
    *,
    title: str | None,
    heading_path: list[str],
    source_page: int | None,
    source_slide: int | None,
    source_unit_position: int | None,
) -> str:
    anchor = "|".join(
        [
            _normalize_text(content),
            title or "",
            ">".join(heading_path),
            str(source_page or ""),
            str(source_slide or ""),
            str(source_unit_position or ""),
        ]
    )
    return hashlib.sha256(anchor.encode("utf-8")).hexdigest()


def _split_on_sentences(content: str, max_length: int) -> list[str]:
    parts = _SENTENCE_END_RE.split(content)
    chunks: list[str] = []
    buffer = ""
    for part in parts:
        if len(buffer) + len(part) + 1 <= max_length:
            buffer = f"{buffer} {part}".strip()
            continue
        if buffer:
            chunks.append(buffer)
        if len(part) > max_length:
            chunks.extend(_hard_split(part, max_length))
            buffer = ""
        else:
            buffer = part
    if buffer:
        chunks.append(buffer)
    return [c for c in chunks if c]


def _hard_split(content: str, max_length: int) -> list[str]:
    return [
        content[index : index + max_length]
        for index in range(0, len(content), max_length)
    ]


@dataclass
class ChunkSourceUnit:
    """A normalized content item the chunker consumes.

    Mirrors the ordering/content fields of ``ContentBlock`` and
    ``GeneratedBlock`` so either source can be adapted cheaply.
    """

    block_type: str
    content: str
    position: int
    heading: str | None = None
    level: int = 0
    source_page: int | None = None
    source_slide: int | None = None
    source_unit_position: int | None = None

    @property
    def is_heading(self) -> bool:
        return _HEADING_RE.match(self.block_type) is not None

    @property
    def effective_heading(self) -> str | None:
        return self.heading or (self.content.strip() if self.is_heading else None)


@dataclass
class ChunkCandidate:
    """A ready-to-persist chunk produced by the chunking engine."""

    chunk_type: str
    content: str
    position: int
    level: int
    heading_path: list[str] = field(default_factory=list)
    title: str | None = None
    source_page: int | None = None
    source_slide: int | None = None
    source_unit_position: int | None = None
    token_count: int = 0
    character_count: int = 0
    chunk_hash: str = ""
    checksum: str = ""
    language: str = "en"
    meta: dict[str, object] = field(default_factory=dict)

    @classmethod
    def build(
        cls,
        *,
        chunk_type: str,
        content: str,
        position: int,
        level: int,
        heading_path: list[str] | None = None,
        title: str | None = None,
        source_page: int | None = None,
        source_slide: int | None = None,
        source_unit_position: int | None = None,
        language: str | None = None,
        meta: dict[str, object] | None = None,
    ) -> ChunkCandidate:
        path = list(heading_path or [])
        return cls(
            chunk_type=chunk_type,
            content=content,
            position=position,
            level=level,
            heading_path=path,
            title=title,
            source_page=source_page,
            source_slide=source_slide,
            source_unit_position=source_unit_position,
            token_count=estimate_tokens(content),
            character_count=len(content),
            chunk_hash=_content_hash(content),
            checksum=_checksum(
                content,
                title=title,
                heading_path=path,
                source_page=source_page,
                source_slide=source_slide,
                source_unit_position=source_unit_position,
            ),
            language=language or detect_language(content),
            meta=dict(meta or {}),
        )


def _heading_path_through(units: list[ChunkSourceUnit], index: int) -> list[str]:
    stack: list[tuple[int, str]] = []
    for unit in units[: index + 1]:
        if unit.is_heading:
            level = _heading_level(unit)
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, unit.effective_heading or ""))
    return [heading for _, heading in stack if heading]


def _heading_level(unit: ChunkSourceUnit) -> int:
    match = _HEADING_LEVEL_RE.match(unit.block_type)
    if match:
        return int(match.group(1))
    return max(1, unit.level)


def _assign_heading_levels(units: list[ChunkSourceUnit]) -> None:
    level_stack: list[int] = []
    for unit in units:
        if unit.is_heading:
            level = _heading_level(unit) or (
                level_stack[-1] + 1 if level_stack else 1
            )
            while level_stack and level_stack[-1] >= level:
                level_stack.pop()
            level_stack.append(level)
            unit.level = level
        else:
            unit.level = level_stack[-1] if level_stack else 0


class ChunkingService:
    """Builds ``ChunkCandidate`` records from normalized source units.

    Parameters mirror the RAG configuration block so the service can be
    constructed directly from ``settings`` or overridden per-index.
    """

    def __init__(
        self,
        *,
        strategy: str = ChunkingStrategy.SEMANTIC.value,
        chunk_size: int = 1500,
        chunk_overlap: int = 150,
        max_chunk_tokens: int = 1000,
        max_chunk_characters: int = 12000,
    ) -> None:
        self.strategy = strategy
        self.chunk_size = max(1, chunk_size)
        self.chunk_overlap = max(0, min(chunk_overlap, self.chunk_size - 1))
        self.max_chunk_tokens = max(1, max_chunk_tokens)
        self.max_chunk_characters = max(1, max_chunk_characters)

    def chunk(self, units: list[ChunkSourceUnit]) -> list[ChunkCandidate]:
        ordered = sorted(units, key=lambda unit: unit.position)
        _assign_heading_levels(ordered)

        if self.strategy == ChunkingStrategy.HEADING.value:
            candidates = self._chunk_heading(ordered)
        elif self.strategy == ChunkingStrategy.PARAGRAPH.value:
            candidates = self._chunk_paragraph(ordered)
        elif self.strategy == ChunkingStrategy.SLIDING.value:
            candidates = self._chunk_sliding(ordered)
        else:
            candidates = self._chunk_semantic(ordered)

        for index, candidate in enumerate(candidates):
            candidate.position = index
        return [self._finalize(candidate) for candidate in candidates]

    def _finalize(self, candidate: ChunkCandidate) -> ChunkCandidate:
        if candidate.token_count > self.max_chunk_tokens:
            candidate.meta["truncated"] = True
        return candidate

    # ── Paragraph strategy ────────────────────────────────────────────────────

    def _chunk_paragraph(self, units: list[ChunkSourceUnit]) -> list[ChunkCandidate]:
        candidates: list[ChunkCandidate] = []
        for unit in units:
            if unit.is_heading:
                continue
            content = unit.content.strip()
            if not content:
                continue
            if len(content) > self.max_chunk_characters:
                for part in _hard_split(content, self.max_chunk_characters):
                    candidates.append(
                        self._candidate(unit, part, chunk_type=unit.block_type)
                    )
                continue
            candidates.append(
                self._candidate(unit, content, chunk_type=unit.block_type)
            )
        return candidates

    # ── Semantic (paragraph-merge) strategy ───────────────────────────────────

    def _chunk_semantic(self, units: list[ChunkSourceUnit]) -> list[ChunkCandidate]:
        candidates: list[ChunkCandidate] = []
        buffer: list[ChunkSourceUnit] = []
        buffer_chars = 0
        pending_path: list[str] = []

        def _flush() -> None:
            nonlocal buffer, buffer_chars, pending_path
            if not buffer:
                return
            content = "\n\n".join(
                unit.content.strip() for unit in buffer if unit.content.strip()
            )
            if not content:
                buffer = []
                buffer_chars = 0
                return
            title = pending_path[-1] if pending_path else None
            candidates.append(
                self._candidate(
                    buffer[0],
                    content,
                    chunk_type="paragraph",
                    heading_path=list(pending_path),
                    title=title,
                )
            )
            pending_path = []
            buffer = []
            buffer_chars = 0

        for unit in units:
            if unit.is_heading:
                _flush()
                pending_path = _heading_path_through(units, unit.position)
                continue

            content = unit.content.strip()
            if not content:
                continue
            if len(content) > self.max_chunk_characters:
                _flush()
                for part in _hard_split(content, self.max_chunk_characters):
                    candidates.append(
                        self._candidate(
                            unit,
                            part,
                            chunk_type=unit.block_type,
                            heading_path=list(pending_path),
                        )
                    )
                continue

            if buffer_chars + len(content) + 2 > self.chunk_size:
                _flush()
            buffer.append(unit)
            buffer_chars += len(content) + 2

        _flush()
        return candidates

    # ── Heading strategy ──────────────────────────────────────────────────────

    def _chunk_heading(self, units: list[ChunkSourceUnit]) -> list[ChunkCandidate]:
        sections: list[tuple[str | None, list[ChunkSourceUnit]]] = []
        current_heading: str | None = None
        current_body: list[ChunkSourceUnit] = []

        for unit in units:
            if unit.is_heading:
                sections.append((current_heading, current_body))
                current_heading = unit.effective_heading or unit.content.strip()
                current_body = []
            else:
                current_body.append(unit)
        sections.append((current_heading, current_body))

        candidates: list[ChunkCandidate] = []
        for heading, body in sections:
            content = "\n\n".join(
                unit.content.strip() for unit in body if unit.content.strip()
            )
            if not content:
                continue
            heading_path = [heading] if heading else []
            for part in self._split_long(content):
                candidates.append(
                    self._candidate(
                        _placeholder_unit(part),
                        part,
                        chunk_type="paragraph",
                        heading_path=list(heading_path),
                        title=heading,
                    )
                )
        return candidates

    # ── Sliding window strategy ───────────────────────────────────────────────

    def _chunk_sliding(self, units: list[ChunkSourceUnit]) -> list[ChunkCandidate]:
        body = "\n\n".join(
            unit.content.strip() for unit in units if unit.content.strip()
        )
        if not body:
            return []

        if len(body) <= self.chunk_size:
            return [
                self._candidate(
                    _placeholder_unit(body), body, chunk_type="sliding"
                )
            ]

        step = max(1, self.chunk_size - self.chunk_overlap)
        windows: list[str] = []
        start = 0
        while start < len(body):
            windows.append(body[start : start + self.chunk_size])
            start += step

        return [
            self._candidate(
                _placeholder_unit(window), window, chunk_type="sliding"
            )
            for window in windows
        ]

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _split_long(self, content: str) -> list[str]:
        if len(content) <= self.chunk_size:
            return [content]
        return _split_on_sentences(content, self.chunk_size)

    def _candidate(
        self,
        unit: ChunkSourceUnit,
        content: str,
        *,
        chunk_type: str,
        heading_path: list[str] | None = None,
        title: str | None = None,
    ) -> ChunkCandidate:
        return ChunkCandidate.build(
            chunk_type=chunk_type,
            content=content,
            position=0,
            level=unit.level,
            heading_path=heading_path or [],
            title=title or unit.effective_heading,
            source_page=unit.source_page,
            source_slide=unit.source_slide,
            source_unit_position=unit.source_unit_position,
            meta={"strategy": self.strategy, "block_type": unit.block_type},
        )


def _placeholder_unit(content: str) -> ChunkSourceUnit:
    return ChunkSourceUnit(
        block_type=ContentBlockType.PARAGRAPH.value,
        content=content,
        position=0,
    )


def _stringify_block_type(value: object) -> str:
    """Normalize a block type value to a plain string.

    ``ContentBlock.block_type`` is stored as a string but typed with an enum
    whose members are ``str`` subclasses; ``GeneratedBlock.block_type`` is a
    plain string. This handles both.
    """
    if isinstance(value, str):
        return value
    return getattr(value, "value", str(value))


def units_from_content_unit(
    unit: Any,
    *,
    position_offset: int = 0,
) -> list[ChunkSourceUnit]:
    """Adapt a persisted ``ContentUnit`` into chunker input units.

    Duck-typed against the ``ContentUnit`` shape (``blocks`` ordered by
    position, each block exposing ``block_type``/``content``/``position``) so
    the chunker does not hard-depend on the model module.
    """
    blocks = list(unit.blocks or [])
    units: list[ChunkSourceUnit] = []
    for block in blocks:
        block_type = _stringify_block_type(getattr(block, "block_type", ""))
        content = block.content or ""
        position = int(getattr(block, "position", 0)) + position_offset
        is_heading = block_type in {ContentBlockType.HEADING.value, "heading"}
        units.append(
            ChunkSourceUnit(
                block_type=block_type,
                content=content,
                position=position,
                heading=content if is_heading else None,
                source_page=getattr(unit, "source_page", None),
                source_slide=int(getattr(unit, "position", 0) or 0) + 1,
                source_unit_position=getattr(unit, "position", None),
            )
        )
    return units


def units_from_generated_lesson_version(
    version: Any,
    *,
    position_offset: int = 0,
) -> list[ChunkSourceUnit]:
    """Adapt a persisted ``GeneratedLessonVersion`` into chunker input units.

    Duck-typed against the version shape (``blocks`` exposing ``block_type``,
    ``heading`` and ``content``) so generated lessons reuse the same chunking
    engine as source presentations.
    """
    blocks = list(version.blocks or [])
    units: list[ChunkSourceUnit] = []
    for block in blocks:
        block_type = _stringify_block_type(getattr(block, "block_type", ""))
        heading = getattr(block, "heading", None) or ""
        content = block.content or ""
        position = int(getattr(block, "position", 0)) + position_offset
        is_heading = _HEADING_RE.match(block_type) is not None
        units.append(
            ChunkSourceUnit(
                block_type=block_type,
                content=content,
                position=position,
                heading=heading if is_heading else None,
                source_page=None,
                source_slide=int(getattr(block, "slide_position", 0) or 0) + 1,
                source_unit_position=getattr(block, "slide_position", None),
            )
        )
    return units
