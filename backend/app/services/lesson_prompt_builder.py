"""Versioned prompt construction for lesson generation.

Owns the system prompt, the JSON payload contract and the deterministic
``prompt_hash``. Bumping ``PROMPT_VERSION`` or ``PAYLOAD_SCHEMA_VERSION``
records provenance on every generated version without requiring a migration.
"""

from __future__ import annotations

import hashlib
from typing import Any

from pydantic import BaseModel, Field

from app.ai.models import AIRequest, AIResponseFormat
from shared.constants import LearningMode

PROMPT_VERSION = "3"
PAYLOAD_SCHEMA_VERSION = "1"

# Output budget guidance. Cap total output to stay inside the model's
# effective output window.
OUTPUT_BUDGET_LARGE_SOURCE_CHARS = 8000
OUTPUT_BUDGET_SMALL_SOURCE_CHARS = 12000

BLOCK_BUDGET_THRESHOLD_CHARS = 20_000

MODE_INSTRUCTIONS: dict[LearningMode, str] = {
    LearningMode.SLIDE: (
        "For each topic, write a clear, well-structured description. "
        "Start with a simple explanation, then provide more detail. "
        "Use natural paragraphs. Do not use block types or bullet lists."
    ),
    LearningMode.READING: (
        "For each topic, write a clear, well-structured description. "
        "Start with a simple explanation, then provide more detail. "
        "Use natural paragraphs. Do not use block types or bullet lists."
    ),
}

JSON_CONTRACT = (
    "Respond with a single JSON object (no markdown fences, no extra text) "
    "matching exactly this schema:\n"
    "{'title': string, 'summary': string|null, "
    "'language': string|null, 'difficulty': 'beginner'|'intermediate'|'advanced'|null, "
    "'topics': [{'topic': string, 'description': string}]}\n"
    "Each item in 'topics' should be a coherent description of one topic. "
    "The 'topic' field should be the topic title. "
    "The 'description' field should be a well-structured explanation. "
    "Return at least one topic per source topic."
)


class SourceUnit(BaseModel):
    position: int
    title: str | None = None
    raw_text: str | None = None
    blocks: list[dict[str, Any]] = Field(default_factory=list)

    def serialized(self) -> str:
        lines: list[str] = [f"[{self.position}] {self.title or 'Untitled'}"]
        if self.raw_text:
            lines.append(self.raw_text)
        for block in self.blocks:
            content = block.get("content")
            if content:
                lines.append(f"- {content}")
        return "\n".join(lines)


class SourceTopic(BaseModel):
    """A topic grouping derived from the stored topic outline."""

    title: str
    slide_ranges: list[int]

    @property
    def start(self) -> int:
        return self.slide_ranges[0] if self.slide_ranges else 1

    @property
    def end(self) -> int:
        return self.slide_ranges[-1] if self.slide_ranges else self.start


class SourceContext(BaseModel):
    title: str | None = None
    units: list[SourceUnit] = Field(default_factory=list)
    total_chars: int = 0
    truncated_units: int = 0
    truncated_chars: int = 0
    topics: list[SourceTopic] = Field(default_factory=list)

    def to_text(self) -> str:
        if not self.topics:
            return "\n\n".join(unit.serialized() for unit in self.units)
        sections: list[str] = []
        grouped_positions: set[int] = set()
        for topic in self.topics:
            group = [
                unit
                for unit in self.units
                if topic.start <= unit.position <= topic.end
            ]
            if not group:
                continue
            grouped_positions.update(unit.position for unit in group)
            header = f"TOPIC: {topic.title} (slides {topic.start}-{topic.end})"
            body = "\n".join(unit.serialized() for unit in group)
            sections.append(f"{header}\n{body}")
        remainder = [
            unit for unit in self.units if unit.position not in grouped_positions
        ]
        if remainder:
            sections.append(
                "TOPIC: (ungrouped)\n"
                + "\n".join(unit.serialized() for unit in remainder)
            )
        return "\n\n".join(sections)


class LessonPromptBuilder:
    @staticmethod
    def _block_parts(block: Any) -> tuple[str | None, str | None]:
        if isinstance(block, dict):
            return block.get("block_type"), block.get("content")
        return getattr(block, "block_type", None), getattr(block, "content", None)

    def build_source_context(
        self,
        units: list[Any],
        *,
        max_units: int,
        max_chars: int,
        topics: list[SourceTopic] | None = None,
    ) -> SourceContext:
        selected = units[:max_units]
        skipped = len(units) - len(selected)
        source_units: list[SourceUnit] = []
        remaining = max_chars
        truncated_chars = 0
        for unit in selected:
            block_parts: list[dict[str, str | None]] = []
            for block in (unit.blocks or []):
                block_type, content = self._block_parts(block)
                if content:
                    block_parts.append({"block_type": block_type, "content": content})
            source_unit = SourceUnit(
                position=unit.position,
                title=unit.title,
                raw_text=unit.raw_text,
                blocks=block_parts,
            )
            size = len(source_unit.serialized())
            if remaining <= 0:
                truncated_chars += size
                continue
            if size > remaining:
                raw = source_unit.raw_text or ""
                keep = remaining - len(f"[{unit.position}] {unit.title or 'Untitled'}\n")
                if keep > 0:
                    source_unit.raw_text = raw[:keep]
                truncated_chars += max(0, size - keep)
                remaining = 0
            else:
                remaining -= size
            source_units.append(source_unit)
        return SourceContext(
            title=units[0].title if units else None,
            units=source_units,
            total_chars=max_chars - remaining,
            truncated_units=skipped + (len(selected) - len(source_units)),
            truncated_chars=truncated_chars,
            topics=list(topics or []),
        )

    def build_ai_request(
        self,
        *,
        mode: LearningMode,
        difficulty: str | None,
        language: str | None,
        title_override: str | None,
        source_context: SourceContext,
        metadata: dict[str, Any],
        model_override: str | None = None,
        attempt: int = 1,
    ) -> AIRequest:
        mode_instruction = MODE_INSTRUCTIONS.get(mode, "")
        title_instruction = ""
        if title_override:
            title_instruction = f'The lesson title must be exactly "{title_override}".'
        difficulty_instruction = (
            f"Target difficulty: {difficulty}." if difficulty else ""
        )
        language_instruction = f"Write the lesson in language code: {language}." if language else ""

        system_prompt = "\n".join(
            [
                "You are an expert educator creating clear topic descriptions for EduVision AI.",
                "For each topic in the source content, write ONE well-structured description.",
                (
                    "Start each description with a simple, accessible explanation. "
                    "Then provide more detail for learners who want to go deeper."
                ),
                JSON_CONTRACT,
                mode_instruction,
                self._budget_instruction(source_context, attempt),
                difficulty_instruction,
                language_instruction,
                title_instruction,
                "Never include information absent from the source content.",
            ]
        )

        user_prompt = "\n".join(
            [
                "Generate topic descriptions from the source content below.",
                (
                    "For each topic, write a clear explanation: start with a simple, "
                    "accessible explanation, then provide more detail."
                ),
                "--- SOURCE CONTENT ---",
                source_context.to_text() or "(empty source)",
                "--- END SOURCE CONTENT ---",
            ]
        )

        return AIRequest(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            response_format=AIResponseFormat.JSON,
            language=language,
            difficulty=difficulty,
            metadata=metadata,
            model_override=model_override,
        )

    @staticmethod
    def _resolve_budget(total_chars: int, attempt: int) -> int:
        return OUTPUT_BUDGET_LARGE_SOURCE_CHARS if total_chars >= BLOCK_BUDGET_THRESHOLD_CHARS else OUTPUT_BUDGET_SMALL_SOURCE_CHARS

    @classmethod
    def _budget_instruction(cls, source_context: SourceContext, attempt: int) -> str:
        max_chars = cls._resolve_budget(source_context.total_chars, attempt)
        return f"Keep the total output under {max_chars} characters."

    def prompt_hash(
        self,
        *,
        mode: LearningMode,
        difficulty: str | None,
        language: str | None,
        source_context: SourceContext,
        attempt: int = 1,
    ) -> str:
        max_chars = self._resolve_budget(source_context.total_chars, attempt)
        payload = "\n".join(
            [
                PROMPT_VERSION,
                PAYLOAD_SCHEMA_VERSION,
                mode.value,
                difficulty or "",
                language or "",
                str(max_chars),
                source_context.to_text(),
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
