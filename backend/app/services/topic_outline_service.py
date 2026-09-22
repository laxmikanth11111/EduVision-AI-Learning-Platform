"""Topic outline & learning intelligence generation service (EduVision 2.0 Checkpoint C2).

Transforms flat presentations into deep hierarchical educational learning structures:
    Document -> Sections -> Topics -> Subtopics -> Concepts -> Objectives -> Examples -> Misconceptions -> Prerequisites -> Learning Sequence

Preserves source grounding, exact source references, backward compatibility, and provides
a high-fidelity deterministic fallback when AI providers are unavailable or exceed quotas.
"""

from __future__ import annotations

import json
import re
import time
import uuid
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
    Concept,
    EducationalExample,
    Misconception,
    OutlineSection,
    OutlineTopic,
    Prerequisite,
    SourceReference,
    Subtopic,
    TopicOutlinePayload,
    build_outline_response,
)

logger = get_logger(__name__)

OUTLINE_PROMPT_VERSION = "2"
OUTLINE_MAX_SOURCE_CHARS = 28_000
OUTLINE_UNIT_PREVIEW_CHARS = 350
OUTLINE_MAX_TOKENS = 8192

OUTLINE_SYSTEM_PROMPT = (
    "You are a principal educational architect and learning science expert for EduVision AI.\n"
    "Your objective is to analyze the source material and produce a deep, structured educational hierarchy.\n"
    "Respond with a single valid JSON object matching exactly this schema:\n"
    "{\n"
    "  \"title\": string,\n"
    "  \"sections\": [\n"
    "    {\"title\": string, \"order\": int, \"topic_titles\": [string], \"slide_ranges\": [start, end]}\n"
    "  ],\n"
    "  \"topics\": [\n"
    "    {\n"
    "      \"title\": string,\n"
    "      \"slide_ranges\": [start, end],\n"
    "      \"section\": string,\n"
    "      \"learning_order\": int,\n"
    "      \"confidence\": float (0.0 to 1.0),\n"
    "      \"source_references\": [{\"unit_id\": string or null, \"slide_number\": int, \"preview\": string or null}],\n"
    "      \"subtopics\": [\n"
    "        {\n"
    "          \"title\": string,\n"
    "          \"learning_order\": int,\n"
    "          \"confidence\": float (0.0 to 1.0),\n"
    "          \"source_references\": [{\"unit_id\": string or null, \"slide_number\": int, \"preview\": string or null}],\n"
    "          \"concepts\": [\n"
    "            {\"name\": string, \"description\": string, \"is_source_grounded\": boolean, \"confidence\": float}\n"
    "          ],\n"
    "          \"learning_objectives\": [string],\n"
    "          \"examples\": [\n"
    "            {\"content\": string, \"type\": \"source_example\" or \"ai_generated_example\"}\n"
    "          ],\n"
    "          \"misconceptions\": [\n"
    "            {\"statement\": string, \"correction\": string, \"is_ai_inferred\": true}\n"
    "          ],\n"
    "          \"prerequisites\": [\n"
    "            {\"prerequisite_topic\": string, \"confidence\": \"high\" or \"medium\" or \"low\"}\n"
    "          ]\n"
    "        }\n"
    "      ]\n"
    "    }\n"
    "  ]\n"
    "}\n\n"
    "Rules for Educational Quality & Integrity:\n"
    "1. Strict Grounding: Concepts and subtopics must be directly derived from the source material. Never invent facts.\n"
    "2. Clear Separation: If an example exists in the source text, type MUST be 'source_example'. If you provide an extra real-world pedagogical illustration, type MUST be 'ai_generated_example'.\n"
    "3. Misconceptions: Identify common mistakes students make for each topic/subtopic; set is_ai_inferred to true.\n"
    "4. Concise Concepts: Keep concept names specific and descriptive (e.g. 'Geographic Scope', 'Transmission Latency'). Avoid generic filler like 'Overview of LAN'.\n"
    "5. Slide Ranges: 1-based, inclusive [start, end] slide indices covering the whole presentation sequentially.\n"
    "6. Valid JSON: Return strictly valid JSON without markdown wrapping or commentary."
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

    async def get_outline_data(
        self,
        presentation: Presentation,
        *,
        auto_generate: bool = False,
    ) -> dict[str, Any]:
        """Retrieve the persisted outline, or return status='none' if missing."""
        outline = await self._repo.get_by_presentation_id(presentation.id)
        if outline is None and auto_generate:
            units = await self._content_repo.list_for_presentation(
                presentation.id, include_blocks=True
            )
            if units:
                return await self.regenerate(presentation, fallback_on_error=True)
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
        return [
            {"title": topic["title"], "slide_ranges": topic["slide_ranges"]}
            for topic in (outline.topics or [])
            if isinstance(topic, dict) and "title" in topic and "slide_ranges" in topic
        ]

    async def regenerate(
        self,
        presentation: Presentation,
        *,
        fallback_on_error: bool = False,
        force_fallback: bool = False,
    ) -> dict[str, Any]:
        """Generate or re-generate the deep C2 learning structure."""
        start_time = time.monotonic()
        units = await self._content_repo.list_for_presentation(
            presentation.id, include_blocks=True
        )
        if not units:
            raise ConflictError(
                message="Presentation has no extracted content to outline",
                details={"presentation_id": presentation.public_id},
            )

        payload: TopicOutlinePayload
        provider: str = "gemini"
        model: str = "gemini-3.5-flash"
        request_id: str | None = None
        correlation_id: str | None = None

        if force_fallback:
            payload = self._deterministic_fallback(units, presentation)
            provider = "deterministic_source_fallback"
            model = "source_structural_engine"
            request_id = f"fallback_{uuid.uuid4().hex[:12]}"
        else:
            try:
                payload, response = await self._generate_payload(units, presentation)
                provider = getattr(response, "provider", "gemini")
                model = getattr(response, "model", "gemini-3.5-flash")
                request_id = getattr(response, "request_id", None)
                correlation_id = getattr(response, "correlation_id", None)
            except AppValidationError:
                if not fallback_on_error:
                    raise
                logger.warning(
                    "topic_outline_ai_parse_failed_using_fallback",
                    presentation_id=presentation.public_id,
                )
                payload = self._deterministic_fallback(units, presentation)
                provider = "deterministic_source_fallback"
                model = "source_structural_engine"
                request_id = f"fallback_{uuid.uuid4().hex[:12]}"
            except Exception as exc:
                logger.warning(
                    "topic_outline_ai_generation_failed_using_fallback",
                    presentation_id=presentation.public_id,
                    error=str(exc)[:300],
                )
                payload = self._deterministic_fallback(units, presentation)
                provider = "deterministic_source_fallback"
                model = "source_structural_engine"
                request_id = f"fallback_{uuid.uuid4().hex[:12]}"

        # Normalize, deduplicate, and enforce source references
        normalized_topics = self._normalize_and_deduplicate(payload, units=units)

        # Build outline model dicts
        duration_ms = int((time.monotonic() - start_time) * 1000)
        total_subtopics = 0
        total_concepts = 0
        for t in normalized_topics:
            subtopics = t.get("subtopics")
            if isinstance(subtopics, list):
                total_subtopics += len(subtopics)
                for st in subtopics:
                    if isinstance(st, dict):
                        concepts = st.get("concepts")
                        if isinstance(concepts, list):
                            total_concepts += len(concepts)

        outline = await self._repo.create_for_presentation(
            presentation.id,
            title=payload.title,
            topics=normalized_topics,
            status="succeeded",
            provider=provider,
            model=model,
            request_id=request_id,
            correlation_id=correlation_id,
        )
        await self._uow.flush()

        logger.info(
            "topic_outline_generated_c2",
            presentation_id=presentation.public_id,
            title=outline.title,
            topics_count=len(normalized_topics),
            subtopics_count=total_subtopics,
            concepts_count=total_concepts,
            duration_ms=duration_ms,
            provider=provider,
            model=model,
        )

        resp = build_outline_response(
            presentation_public_id=presentation.public_id,
            outline=outline,
        )
        resp["generation_metadata"] = {
            "source_units_processed": len(units),
            "topics_created": len(normalized_topics),
            "subtopics_created": total_subtopics,
            "concepts_created": total_concepts,
            "duration_ms": duration_ms,
            "engine": provider,
        }
        return resp

    # ── AI Pipeline Internals ──────────────────────────────────────────────────

    async def _generate_payload(
        self, units: list[Any], presentation: Presentation
    ) -> tuple[TopicOutlinePayload, Any]:
        """Run the AI prompt pass, retrying once with compact source on failure."""
        last_error: Exception | None = None
        for attempt in (1, 2):
            try:
                source_text = self._build_source_text(
                    units, titles_only=(attempt == 2)
                )
                self._assert_no_injection(source_text, presentation)
                request = self._build_request(source_text, presentation, attempt=attempt)
                response = await self._ai.generate(request)
                payload = self._parse_payload(response.text)
                return payload, response
            except (AIError, ValidationError, ValueError) as exc:
                last_error = exc
                continue

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

    def _build_source_text(self, units: list[Any], *, titles_only: bool = False) -> str:
        lines: list[str] = []
        remaining = OUTLINE_MAX_SOURCE_CHARS
        for unit in units:
            pos = getattr(unit, "position", 1)
            title = getattr(unit, "title", None) or f"Slide {pos}"
            if titles_only:
                block = f"[{pos}] {title}"
            else:
                preview = self._unit_preview(unit)
                header = f"[{pos}] {title}"
                block = header if not preview else f"{header}\n{preview}"
            if remaining <= 0:
                break
            if len(block) > remaining:
                block = block[:remaining]
            lines.append(block)
            remaining -= len(block)
        return "\n".join(lines)

    @classmethod
    def _assert_no_injection(
        cls, source_text: str, presentation: Presentation
    ) -> None:
        """Block user-supplied source from manipulating the outline model.

        Uploaded content is DATA. When it contains a reliable instruction-override
        attempt we abort the LLM path so ``regenerate`` (which catches generic
        exceptions) can fall back to the deterministic, model-free outline.
        """
        from app.ai.prompt_injection import (
            is_reliably_flagged,
            scan_for_prompt_injection,
        )
        from app.core.config import settings

        if not settings.AI_PROMPT_INJECTION_ENABLED or not source_text.strip():
            return
        scan = scan_for_prompt_injection(
            source_text, threshold=settings.AI_PROMPT_INJECTION_THRESHOLD
        )
        if is_reliably_flagged(scan):
            logger.warning(
                "topic_outline_prompt_injection_refused",
                presentation_id=presentation.public_id,
                matched_rules=scan.matched_rules,
            )
            raise AppValidationError(
                message=(
                    "The uploaded source content contains embedded "
                    "instructions that could manipulate the learning model. "
                    "Outline generation was blocked for safety."
                ),
                details={
                    "presentation_id": presentation.public_id,
                    "matched_rules": list(scan.matched_rules),
                },
            )

    @classmethod
    def _unit_preview(cls, unit: Any) -> str:
        parts: list[str] = []
        for block in getattr(unit, "blocks", []) or []:
            b_type = getattr(block, "block_type", "")
            content = getattr(block, "content", None)
            meta = getattr(block, "meta", None) or getattr(block, "metadata", None) or {}
            if b_type == "list_item" and content:
                lvl = meta.get("level", 0)
                indent = "  " * lvl
                parts.append(f"{indent}• {content}")
            elif b_type == "table" and content:
                parts.append(f"[Table]: {content[:150]}")
            elif b_type == "note" and content:
                parts.append(f"[Instructor Note]: {content[:120]}")
            elif content:
                parts.append(str(content).strip())
        if parts:
            text = "\n".join(parts)
        elif getattr(unit, "raw_text", None):
            text = str(unit.raw_text).strip()
        else:
            text = ""
        return text[: OUTLINE_UNIT_PREVIEW_CHARS]

    @staticmethod
    def _build_request(
        source_text: str,
        presentation: Presentation,
        *,
        attempt: int = 1,
    ) -> AIRequest:
        user_prompt = "\n".join(
            [
                "Analyze the uploaded presentation source content and build a complete hierarchical learning outline.",
                f"Deck Title: {presentation.title or 'Untitled Presentation'}",
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
        cleaned = cls._extract_json(text)
        try:
            return TopicOutlinePayload.model_validate_json(cleaned)
        except ValidationError:
            try:
                data = json.loads(cleaned)
                if "outline" in data and isinstance(data["outline"], dict):
                    return TopicOutlinePayload.model_validate(data["outline"])
                if "topics" in data and isinstance(data["topics"], list):
                    return TopicOutlinePayload.model_validate(data)
            except Exception:
                pass
            fixed = cls._repair_json(cleaned)
            return TopicOutlinePayload.model_validate_json(fixed)

    @staticmethod
    def _extract_json(text: str) -> str:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
        if match:
            text = match.group(1)
        text = text.strip()
        start = text.find("{")
        if start == -1:
            return text
        end = text.rfind("}")
        return text[start:] if end == -1 else text[start : end + 1]

    @staticmethod
    def _repair_json(candidate: str) -> str:
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
        closers = []
        while stack:
            closers.append("}" if stack.pop() == "{" else "]")
        return candidate + "".join(closers)

    # ── High-Fidelity Deterministic Fallback ────────────────────────────────────

    def _deterministic_fallback(
        self, units: list[Any], presentation: Presentation
    ) -> TopicOutlinePayload:
        """Derive an educational hierarchy directly from source units and blocks.

        Guarantees:
        - Works for 1-slide, 2-slide, small, or large documents without failing.
        - Preserves exact slide numbers and unit public IDs in source_references.
        - Maps Level 0 bullets to Subtopics, Level 1 bullets to Concepts.
        - Maps Tables to Subtopics and matrix rows to Concepts.
        - Maps Speaker Notes to instructional clarifications.
        - Generates measurable Bloom-taxonomy learning objectives.
        - Partitions examples: text from slides is marked 'source_example'.
        """
        deck_title = (
            presentation.title
            or (units[0].title if units and getattr(units[0], "title", None) else None)
            or "Educational Presentation"
        )
        total_units = len(units)

        # 1. Section Identification
        sections: list[OutlineSection] = []
        topics: list[OutlineTopic] = []


        section_titles: list[str] = []
        if total_units <= 2:
            section_titles = ["Core Fundamentals"]
        elif total_units <= 4:
            section_titles = ["Foundations & Classifications", "Protocols & Systems"]
        else:
            section_titles = [
                "Introduction & Principles",
                "Architectural Frameworks",
                "Advanced Implementations & Analysis",
            ]

        # 2. Process Units into Topics
        for idx, unit in enumerate(units):
            pos = getattr(unit, "position", idx + 1)
            raw_title = (getattr(unit, "title", None) or "").strip()
            title = raw_title if raw_title else f"Topic {pos}"

            # Assign section
            sec_idx = min(int(idx / max(1, total_units / len(section_titles))), len(section_titles) - 1)
            sec_name = section_titles[sec_idx]

            unit_id = getattr(unit, "public_id", None)
            src_ref = SourceReference(
                unit_id=unit_id,
                slide_number=pos,
                preview=title,
            )

            # Analyze blocks for Subtopics, Concepts, Tables, Notes
            subtopics: list[Subtopic] = []
            current_subtopic: Subtopic | None = None
            current_order = 1

            blocks = getattr(unit, "blocks", []) or []
            for b in blocks:
                b_type = (getattr(b, "block_type", "") or "").lower()
                content = (getattr(b, "content", "") or "").strip()
                b_meta = getattr(b, "meta", None)
                meta = b_meta if isinstance(b_meta, dict) else {}
                if not content and b_type != "table":
                    continue

                if b_type in ("bullet", "list_item"):
                    level = int(meta.get("level", 0))
                    if level == 0:
                        # Major bullet point -> Subtopic
                        colon_split = content.split(":", 1)
                        sub_title = colon_split[0].strip()
                        sub_desc = colon_split[1].strip() if len(colon_split) > 1 else None

                        init_concepts = []
                        if sub_desc:
                            init_concepts.append(
                                Concept(
                                    name=f"{sub_title} Characteristics",
                                    description=sub_desc,
                                    is_source_grounded=True,
                                    confidence=0.92,
                                    source_references=[src_ref],
                                )
                            )
                        else:
                            init_concepts.append(
                                Concept(
                                    name=f"{sub_title} Principles",
                                    description=f"Core conceptual definition and properties of {sub_title}.",
                                    is_source_grounded=True,
                                    confidence=0.9,
                                    source_references=[src_ref],
                                )
                            )

                        current_subtopic = Subtopic(
                            title=content,
                            learning_order=current_order,
                            confidence=0.95,
                            source_references=[src_ref],
                            concepts=init_concepts,
                            learning_objectives=[
                                f"Explain the core characteristics and operation of {sub_title}."
                            ],
                            examples=[],
                            misconceptions=[],
                            prerequisites=[],
                        )
                        # Check for source examples in content
                        if any(kw in content.lower() for kw in ("such as", "for example", "e.g.", "campus", "home")):
                            current_subtopic.examples.append(
                                EducationalExample(
                                    content=content,
                                    type="source_example",
                                )
                            )
                        subtopics.append(current_subtopic)
                        current_order += 1
                    else:
                        # Sub-bullet -> Concept under current subtopic
                        concept_obj = Concept(
                            name=content[:80] + ("..." if len(content) > 80 else ""),
                            description=content,
                            is_source_grounded=True,
                            confidence=0.92,
                            source_references=[src_ref],
                        )
                        if current_subtopic is not None:
                            current_subtopic.concepts.append(concept_obj)
                        else:
                            # Fallback if level 1 appears without level 0
                            if not subtopics:
                                current_subtopic = Subtopic(
                                    title=f"{title} Details",
                                    learning_order=1,
                                    confidence=0.9,
                                    source_references=[src_ref],
                                )
                                subtopics.append(current_subtopic)
                            subtopics[-1].concepts.append(concept_obj)

                elif b_type == "table":
                    tbl_rows = meta.get("table_data") or []
                    tbl_title = f"{title} Specification Matrix"
                    tbl_subtopic = Subtopic(
                        title=tbl_title,
                        learning_order=current_order,
                        confidence=0.95,
                        source_references=[src_ref],
                        concepts=[],
                        learning_objectives=[
                            f"Analyze and compare elements presented in the {title} reference matrix."
                        ],
                        examples=[],
                        misconceptions=[],
                        prerequisites=[],
                    )
                    current_order += 1
                    if isinstance(tbl_rows, list) and len(tbl_rows) > 1:
                        for row in tbl_rows[1:]:
                            if isinstance(row, list) and len(row) >= 2:
                                concept_name = str(row[0]).strip()
                                concept_desc = " | ".join(str(c).strip() for c in row[1:])
                                tbl_subtopic.concepts.append(
                                    Concept(
                                        name=concept_name,
                                        description=concept_desc,
                                        is_source_grounded=True,
                                        confidence=0.95,
                                        source_references=[src_ref],
                                    )
                                )
                    subtopics.append(tbl_subtopic)

                elif b_type in ("note", "notes"):
                    # Speaker note -> Misconception / Instructional insight
                    note_clean = content.replace("Instructor Note:", "").replace("Note:", "").strip()
                    if subtopics:
                        subtopics[-1].misconceptions.append(
                            Misconception(
                                statement=f"Oversimplifying the scope or theoretical nature of {subtopics[-1].title}.",
                                correction=note_clean,
                                is_ai_inferred=False,
                            )
                        )

            # If no subtopics were derived from bullets/tables, create one from the slide title
            if not subtopics:
                subtopics.append(
                    Subtopic(
                        title=title,
                        learning_order=1,
                        confidence=0.9,
                        source_references=[src_ref],
                        concepts=[
                            Concept(
                                name=f"{title} Overview",
                                description=f"Foundational concepts and principles of {title}.",
                                is_source_grounded=True,
                                confidence=0.88,
                                source_references=[src_ref],
                            )
                        ],
                        learning_objectives=[
                            f"Demonstrate a clear conceptual understanding of {title}."
                        ],
                        examples=[],
                        misconceptions=[],
                        prerequisites=[],
                    )
                )

            # Assign prerequisites between sequential topics
            prerequisites: list[Prerequisite] = []
            if idx > 0:
                prev_title = topics[-1].title
                prerequisites.append(
                    Prerequisite(prerequisite_topic=prev_title, confidence="high")
                )

            topic_obj = OutlineTopic(
                title=title,
                slide_ranges=[pos, pos],
                section=sec_name,
                source_order=pos,
                learning_order=pos,
                confidence=0.95,
                source_references=[src_ref],
                subtopics=subtopics,
                concepts=[c for st in subtopics for c in st.concepts],
                learning_objectives=[obj for st in subtopics for obj in st.learning_objectives],
                examples=[ex for st in subtopics for ex in st.examples],
                misconceptions=[m for st in subtopics for m in st.misconceptions],
                prerequisites=prerequisites,
            )
            topics.append(topic_obj)

        sec_grouped: dict[str, list[str]] = {}
        for t in topics:
            sec_grouped.setdefault(t.section or "General", []).append(t.title)

        for s_idx, (s_name, s_top_titles) in enumerate(sec_grouped.items()):
            sections.append(
                OutlineSection(
                    title=s_name,
                    order=s_idx + 1,
                    topic_titles=s_top_titles,
                    slide_ranges=[1, total_units],
                )
            )

        return TopicOutlinePayload(
            title=deck_title,
            sections=sections,
            topics=topics,
        )

    # ── Deduplication & Normalization ──────────────────────────────────────────

    def _normalize_and_deduplicate(
        self,
        payload: TopicOutlinePayload,
        *,
        units: list[Any],
    ) -> list[dict[str, object]]:
        unit_count = len(units)
        unit_map = {getattr(u, "position", i + 1): getattr(u, "public_id", None) for i, u in enumerate(units)}

        raw_topics = payload.topics
        merged_topics: list[dict[str, Any]] = []
        seen_titles: dict[str, int] = {}

        def _normalize_title(t: str) -> str:
            cleaned = re.sub(r"[^a-zA-Z0-9\s]", "", t).lower().strip()
            cleaned = re.sub(r"^(overview\s+of|introduction\s+to|summary\s+of)\s+", "", cleaned)
            words = sorted(
                re.sub(r"s\b", "", w)
                for w in cleaned.split()
                if w not in ("of", "the", "in", "to", "for", "and", "by", "a", "an")
            )
            return " ".join(words)

        for topic in raw_topics:
            title = topic.title.strip()
            if not title:
                continue

            start = max(1, min(int(topic.slide_ranges[0]), unit_count))
            end = max(start, min(int(topic.slide_ranges[1]), unit_count))

            norm_key = _normalize_title(title)
            if norm_key in seen_titles:
                # Merge duplicate into existing topic
                existing_idx = seen_titles[norm_key]
                target = merged_topics[existing_idx]
                target["slide_ranges"][0] = min(target["slide_ranges"][0], start)
                target["slide_ranges"][1] = max(target["slide_ranges"][1], end)

                # Merge subtopics
                existing_st_titles = {st["title"].lower() for st in target["subtopics"]}
                for st in topic.subtopics:
                    if st.title.lower() not in existing_st_titles:
                        target["subtopics"].append(st.model_dump(mode="json"))
                        existing_st_titles.add(st.title.lower())
                continue

            # Ensure valid source references with real public IDs
            src_refs = []
            for slide_num in range(start, end + 1):
                u_id = unit_map.get(slide_num)
                src_refs.append(
                    {
                        "unit_id": u_id,
                        "slide_number": slide_num,
                        "preview": title,
                    }
                )

            topic_dict = topic.model_dump(mode="json")
            topic_dict["title"] = title
            topic_dict["slide_ranges"] = [start, end]
            topic_dict["source_references"] = src_refs
            topic_dict["learning_order"] = len(merged_topics) + 1
            topic_dict["source_order"] = start

            # Propagate source references to subtopics if empty
            for st in topic_dict.get("subtopics") or []:
                if not st.get("source_references"):
                    st["source_references"] = src_refs

            seen_titles[norm_key] = len(merged_topics)
            merged_topics.append(topic_dict)

        merged_topics.sort(key=lambda t: int(t["slide_ranges"][0]))
        for idx, t in enumerate(merged_topics, start=1):
            t["learning_order"] = idx

        return merged_topics
