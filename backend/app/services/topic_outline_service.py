"""Topic outline generation service.

Runs a single LLM pass over a presentation's extracted content units to
produce a structured outline::

    {"title": str, "topics": [{"title": str, "slide_ranges": [start, end]}]}

The outline is persisted per presentation (``topic_outlines``), surfaced via
the topics API and consumed by lesson generation so ``build_source_context``
can group source content by real topic structure instead of raw serialized
text.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from app.ai.errors import AIError
from app.ai.models import AIRequest, AIResponseFormat
from app.ai.service import AIContentService
from app.core.exceptions import ConflictError
from app.core.exceptions import ValidationError as AppValidationError
from app.core.logging import get_logger
from app.database.unit_of_work import UnitOfWork
from app.models.presentation import Presentation
from app.repositories.content_repository import ContentUnitRepository
from app.repositories.topic_outline_repository import TopicOutlineRepository
from app.schemas.topic_outline import (
    TopicOutlinePayload,
    build_outline_response,
)

logger = get_logger(__name__)

OUTLINE_PROMPT_VERSION = "1"
OUTLINE_MAX_SOURCE_CHARS = 24_000
OUTLINE_UNIT_PREVIEW_CHARS = 240
OUTLINE_MAX_TOKENS = 8192

OUTLINE_SYSTEM_PROMPT = (
    "You are an expert educator organizing a slide deck into a logical topic "
    "outline for EduVision AI.\n"
    "Analyze the source content below and respond with a single JSON object "
    "(no markdown fences, no extra text) matching exactly this schema:\n"
    "{'title': string, 'topics': [{'title': string, 'slide_ranges': [start, end]}]}\n"
    "Rules:\n"
    "- 'title' is a concise title for the whole deck.\n"
    "- Each topic has a short, specific 'title' and 'slide_ranges' = [start, end] "
    "listing the 1-based, inclusive slide numbers it covers in the source deck.\n"
    "- Topics must be non-overlapping, ordered by start, and together cover the "
    "entire deck (start of the first topic must be 1, end of the last topic must "
    "equal the total slide count).\n"
    "- Use at most 12 topics. Merge near-identical adjacent sections instead of "
    "splitting them.\n"
    "- The response must be complete and valid JSON: every object and array "
    "closed, ending with '}'.\n"
    "Never invent content absent from the source."
)


class TopicOutlineService:
    def __init__(
        self,
        uow: UnitOfWork,
        *,
        ai_service: Any | None = None,
    ) -> None:
        self._uow = uow
        self._repo = TopicOutlineRepository(uow.session)
        self._content_repo = ContentUnitRepository(uow.session)
        self._ai = ai_service if ai_service is not None else AIContentService(uow=uow)

    # ── Public API ────────────────────────────────────────────────────────────

    async def get_outline_data(self, presentation: Presentation) -> dict[str, Any]:
        outline = await self._repo.get_by_presentation_id(presentation.id)
        return build_outline_response(
            presentation_public_id=presentation.public_id,
            outline=outline,
        )

    async def get_stored_topics(
        self, presentation_id: Any
    ) -> list[dict[str, object]] | None:
        """Return the persisted outline topics (``{title, slide_ranges}``).

        ``None`` when no outline has been generated. Used by lesson generation
        to feed real topic structure into ``build_source_context``.
        """
        outline = await self._repo.get_by_presentation_id(presentation_id)
        if outline is None or outline.status != "succeeded":
            return None
        return [dict(topic) for topic in (outline.topics or [])]

    async def regenerate(self, presentation: Presentation) -> dict[str, Any]:
        units = await self._content_repo.list_for_presentation(
            presentation.id, include_blocks=True
        )
        if not units:
            raise ConflictError(
                message="Presentation has no extracted content to outline",
                details={"presentation_id": presentation.public_id},
            )

        payload, response = await self._generate_payload(units, presentation)
        normalized = self._normalize(payload, unit_count=len(units))
        outline = await self._repo.create_for_presentation(
            presentation.id,
            title=payload.title,
            topics=normalized,
            status="succeeded",
            provider=response.provider,
            model=response.model,
            request_id=response.request_id,
            correlation_id=response.correlation_id,
        )
        await self._uow.flush()

        logger.info(
            "topic_outline_generated",
            presentation_id=presentation.public_id,
            title=outline.title,
            topics=len(normalized),
            provider=response.provider,
            model=response.model,
        )
        return build_outline_response(
            presentation_public_id=presentation.public_id,
            outline=outline,
        )

    async def _generate_payload(
        self, units: list[Any], presentation: Presentation
    ) -> tuple[TopicOutlinePayload, Any]:
        """Run the LLM pass, retrying once with a compact source on failure.

        Returns ``(payload, response)`` or raises an ``AppValidationError``
        with a friendly message when the model repeatedly fails to produce a
        parseable outline.
        """
        last_error: Exception | None = None
        for attempt in (1, 2):
            if attempt == 2:
                logger.warning(
                    "topic_outline_retry_compact",
                    presentation_id=presentation.public_id,
                    error=str(last_error)[:300],
                )
            try:
                source_text = self._build_source_text(
                    units, titles_only=(attempt == 2)
                )
                request = self._build_request(source_text, presentation, attempt=attempt)
                response = await self._ai.generate(request)
                payload = self._parse_payload(response.text)
            except AIError as exc:
                last_error = exc
                continue
            except (ValidationError, ValueError) as exc:
                last_error = exc
                continue
            return payload, response

        logger.error(
            "topic_outline_parse_failed",
            presentation_id=presentation.public_id,
            error=str(last_error)[:300],
        )
        raise AppValidationError(
            message=(
                "Topic outline generation failed: the AI output could not be "
                "parsed. Please retry."
            ),
            details={"presentation_id": presentation.public_id},
        ) from last_error

    # ── Internals ─────────────────────────────────────────────────────────────

    def _build_source_text(self, units: list[Any], *, titles_only: bool = False) -> str:
        lines: list[str] = []
        remaining = OUTLINE_MAX_SOURCE_CHARS
        for unit in units:
            title = unit.title or f"Slide {unit.position}"
            if titles_only:
                block = f"[{unit.position}] {title}"
            else:
                preview = self._unit_preview(unit)
                header = f"[{unit.position}] {title}"
                block = header if not preview else f"{header}\n{preview}"
            if remaining <= 0:
                break
            if len(block) > remaining:
                block = block[:remaining]
            lines.append(block)
            remaining -= len(block)
        return "\n".join(lines)

    @classmethod
    def _unit_preview(cls, unit: Any) -> str:
        if unit.raw_text:
            text = unit.raw_text.strip()
        else:
            parts: list[str] = []
            for block in unit.blocks or []:
                content = getattr(block, "content", None)
                if content:
                    parts.append(str(content).strip())
            text = "\n".join(parts)
        return text[: OUTLINE_UNIT_PREVIEW_CHARS].replace("\n", " ")

    @staticmethod
    def _build_request(
        source_text: str,
        presentation: Presentation,
        *,
        attempt: int = 1,
    ) -> AIRequest:
        user_prompt = "\n".join(
            [
                (
                    "Create a topic outline for the deck below. Total slide count "
                    "is the number of listed entries."
                ),
                "--- SOURCE CONTENT ---",
                source_text or "(empty source)",
                "--- END SOURCE CONTENT ---",
            ]
        )
        return AIRequest(
            user_prompt=user_prompt,
            system_prompt=OUTLINE_SYSTEM_PROMPT,
            response_format=AIResponseFormat.JSON,
            max_tokens=OUTLINE_MAX_TOKENS,
            metadata={
                "resource_type": "presentation",
                "resource_id": presentation.public_id,
                "prompt_version": OUTLINE_PROMPT_VERSION,
                "attempt": attempt,
            },
        )

    @classmethod
    def _parse_payload(cls, text: str) -> TopicOutlinePayload:
        """Parse the model output, tolerating fences, wrappers and truncated
        trailing braces."""
        cleaned = cls._extract_json(text)
        try:
            return TopicOutlinePayload.model_validate_json(cleaned)
        except (ValidationError, ValueError):
            data = json.loads(cleaned)
            if isinstance(data, dict) and "outline" in data and isinstance(
                data["outline"], dict
            ):
                return TopicOutlinePayload.model_validate(data["outline"])
            raise

    @staticmethod
    def _extract_json(text: str) -> str:
        """Return the JSON object from a model response, repairing the common
        truncated-trailing-brace failure mode."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        start = cleaned.find("{")
        if start < 0:
            return cleaned
        candidate = cleaned[start:].rstrip()
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass
        return candidate + TopicOutlineService._close_json(candidate)

    @staticmethod
    def _close_json(candidate: str) -> str:
        """Append missing closers (LIFO) to a truncated JSON value."""
        stack: list[str] = []
        in_string = False
        escaped = False
        for ch in candidate:
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch in "{[":
                stack.append(ch)
            elif ch in "}]" and stack:
                stack.pop()
        closers: list[str] = []
        while stack:
            closers.append("}" if stack.pop() == "{" else "]")
        return "".join(closers)

    @staticmethod
    def _normalize(
        payload: TopicOutlinePayload,
        *,
        unit_count: int,
    ) -> list[dict[str, object]]:
        topics: list[dict[str, object]] = []
        for topic in payload.topics:
            title = topic.title.strip()
            if not title:
                continue
            start = max(1, min(int(topic.slide_ranges[0]), unit_count))
            end = max(start, min(int(topic.slide_ranges[1]), unit_count))
            topics.append({"title": title, "slide_ranges": [start, end]})
        topics.sort(key=lambda t: int(t["slide_ranges"][0]))
        return topics
