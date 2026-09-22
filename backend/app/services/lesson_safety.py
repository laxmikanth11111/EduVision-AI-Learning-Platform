"""Pluggable AI safety validation hooks for lesson generation.

The default implementation is a no-op. Production deployments can provide a
concrete validator (e.g. wired via ``AI_LESSON_SAFETY_VALIDATOR``) that checks
source content before generation and model output after generation. Results of
the applied checks are recorded in the version ``generation_metadata``.

Names supported by :func:`build_safety_validator`:

* ``noop`` — accepts everything (extension point / explicit opt-out).
* ``grounded`` — the default. Scans untrusted source content for prompt
  injection and refuses generation when a reliable injection attempt is
  detected; rejects structurally empty generated payloads; records a
  deterministic source-coverage estimate on every accepted output.
"""

from __future__ import annotations

from typing import Any, Protocol

from app.core.error_codes import ErrorCode
from app.core.exceptions import EduVisionError
from app.core.logging import get_logger
from app.observability.metrics import metrics

logger = get_logger(__name__)


class LessonSafetyError(EduVisionError):
    def __init__(
        self,
        message: str = "Content did not pass safety validation",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=ErrorCode.SAFETY_ERROR,
            status_code=422,
            details=details,
        )


class LessonSafetyValidator(Protocol):
    """Validates input source content and generated output.

    Implementations should be stateless or inject dependencies via __init__.
    Raising ``LessonSafetyError`` blocks the generation (input) or fails the
    version with ``error_code="safety_rejected"`` (output).
    """

    name: str

    async def validate_input(
        self,
        *,
        source_context: Any,
        request: Any,
        presentation_id: str,
    ) -> None:
        """Raise LessonSafetyError to reject generation for unsafe source."""
        ...

    async def validate_output(
        self,
        *,
        payload: Any,
        source_context: Any,
        request: Any,
    ) -> None:
        """Raise LessonSafetyError to reject generated output."""
        ...


class NoopLessonSafetyValidator:
    """Default validator: accepts everything. Extension point for production."""

    name = "noop"

    async def validate_input(
        self,
        *,
        source_context: Any,
        request: Any,
        presentation_id: str,
    ) -> None:
        return None

    async def validate_output(
        self,
        *,
        payload: Any,
        source_context: Any,
        request: Any,
    ) -> None:
        return None


def _text_of(source_context: Any) -> str:
    """Best-effort extraction of the raw source text from a context object."""
    to_text = getattr(source_context, "to_text", None)
    if callable(to_text):
        try:
            text = to_text()
            if isinstance(text, str):
                return text
        except Exception:
            pass
    units = getattr(source_context, "units", None)
    if isinstance(units, list):
        parts: list[str] = []
        for unit in units:
            title = getattr(unit, "title", None)
            if title:
                parts.append(str(title))
            raw = getattr(unit, "raw_text", None)
            if raw:
                parts.append(str(raw))
            for block in getattr(unit, "blocks", []) or []:
                content = block.get("content") if isinstance(block, dict) else getattr(block, "content", None)
                if content:
                    parts.append(str(content))
        return "\n".join(parts)

    # A single content unit (title/raw_text/blocks) passed directly.
    parts = []
    for attr in ("title", "raw_text"):
        value = getattr(source_context, attr, None)
        if value:
            parts.append(str(value))
    return "\n".join(parts)


class GroundedLessonSafetyValidator:
    """Meaningful, deterministic safety/grounding checks for lesson generation.

    Input checks (run before the AI is ever called):
    * scans the assembled source context for prompt-injection patterns and
      rejects generation when a *reliable* injection attempt is present (see
      ``app.ai.prompt_injection``);
    * requires the source context to contain extractable text (empty source
      cannot be grounded).

    Output checks (run on a parsed AI payload), as a layered pipeline:

    Layer 3 (preliminary, deterministic): rejects outputs whose content words
    share too little vocabulary with the source (below
    ``AI_LESSON_SOURCE_COVERAGE_THRESHOLD``), catching fully fabricated lessons
    while allowing legitimate paraphrasing. This is a coarse lexical source-
    coverage estimate only — it is NOT a semantic-grounding judgment.

    Layers 4-6 (claim-level semantic grounding, behind
    ``AI_LESSON_GROUNDING_ENABLED``): topic descriptions are segmented into
    claims, candidate evidence is retrieved semantically against the source
    context, each claim is verified (LLM verifier via the existing provider
    abstraction, or the conservative deterministic fallback), and a fail-safe
    deterministic policy accepts only supported claims. Unsupported,
    contradicted, or uncertain-but-high-risk claims reject the topic and
    therefore the lesson. The full structured report is exposed via
    ``grounding_report`` so the caller can persist provenance in the version
    ``generation_metadata``.

    All checks are recorded through the ``eduvision.ai_safety.*`` metrics and
    structured logs with no raw prompts or model output.

    Terminology: this validator estimates *source grounding*. It does not
    establish truth against the real world, and cosine similarity is used only
    to rank candidate evidence — never as the final verdict.
    """

    name = "grounded"

    def __init__(
        self,
        *,
        ai_service: Any | None = None,
        embedding_provider: Any | None = None,
    ) -> None:
        self._ai_service = ai_service
        self._embedding_provider = embedding_provider
        self.grounding_report: dict[str, Any] | None = None

    async def validate_input(
        self,
        *,
        source_context: Any,
        request: Any,
        presentation_id: str,
    ) -> None:
        from app.ai.prompt_injection import (
            is_reliably_flagged,
            scan_for_prompt_injection,
        )
        from app.core.config import settings

        text = _text_of(source_context)
        if not text.strip():
            metrics.increment("ai_safety_input_empty_total")
            raise LessonSafetyError(
                message="Source content contains no extractable text to ground a lesson on",
                details={"presentation_id": presentation_id},
            )

        if not settings.AI_PROMPT_INJECTION_ENABLED:
            metrics.increment("ai_safety_input_scan_skipped_total")
            return

        result = scan_for_prompt_injection(
            text, threshold=settings.AI_PROMPT_INJECTION_THRESHOLD
        )
        if is_reliably_flagged(result):
            metrics.increment(
                "ai_safety_input_injection_total",
                rules=",".join(result.matched_rules),
            )
            logger.warning(
                "lesson_safety_prompt_injection_rejected",
                presentation_id=presentation_id,
                matched_rules=result.matched_rules,
            )
            raise LessonSafetyError(
                message=(
                    "The uploaded source content contains embedded instructions "
                    "that could manipulate the learning model. Generation was "
                    "blocked for safety."
                ),
                details={
                    "presentation_id": presentation_id,
                    "matched_rules": list(result.matched_rules),
                },
            )
        metrics.increment("ai_safety_input_clean_total")

    async def validate_output(
        self,
        *,
        payload: Any,
        source_context: Any,
        request: Any,
    ) -> None:

        topics = getattr(payload, "topics", None)
        if topics is None or len(topics) == 0:
            metrics.increment("ai_safety_output_empty_total")
            raise LessonSafetyError(
                message="Generated lesson contained no topic blocks",
                details={"topics": 0},
            )

        coverage = _estimate_source_coverage(payload, source_context)
        metrics.observe("ai_safety_output_source_coverage", coverage)
        metrics.increment("ai_safety_output_accepted_total", coverage_bucket=_coverage_bucket(coverage))

        from app.core.config import settings
        threshold = settings.AI_LESSON_SOURCE_COVERAGE_THRESHOLD
        rejected = _first_weak_topic(payload, source_context, coverage_threshold=threshold)
        if rejected is not None:
            topic_coverage = _estimate_topic_coverage(rejected[0], source_context)
            metrics.increment("ai_safety_output_coverage_rejected_total")
            raise LessonSafetyError(
                message=(
                    "The generated lesson contains a topic block that does not "
                    "reference the source material closely enough "
                    f"(coverage {topic_coverage:.2%} < threshold {threshold:.2%}). "
                    "Generation was rejected for safety."
                ),
                details={
                    "topic": rejected[1],
                    "topic_coverage": topic_coverage,
                    "overall_coverage": coverage,
                    "threshold": threshold,
                    "grounding_layer": "lexical_coverage",
                },
            )

        self.grounding_report = None
        if settings.AI_LESSON_GROUNDING_ENABLED:
            from app.services.claim_grounding import run_claim_grounding

            report, failed = await run_claim_grounding(
                topics,
                source_context,
                settings=settings,
                ai_service=self._ai_service,
                embedding_provider=self._embedding_provider,
            )
            self.grounding_report = report
            if failed is not None:
                metrics.increment(
                    "ai_safety_grounding_lesson_rejected_total",
                    verdict=str(failed.get("verdict", "")),
                    method=str(failed.get("method", "")),
                )
                message = (
                    "The generated lesson contains a claim in topic "
                    f"'{failed.get('topic', '')}' that is not supported by the "
                    "source material. Generation was rejected for safety."
                )
                raise LessonSafetyError(
                    message=message,
                    details={
                        "grounding_layer": "claim_grounding",
                        "grounding": failed,
                    },
                )


def _coverage_bucket(coverage: float) -> str:
    if coverage >= 0.35:
        return "high"
    if coverage >= 0.15:
        return "medium"
    if coverage >= 0.0:
        return "low"
    return "none"


def _estimate_source_coverage(payload: Any, source_context: Any) -> float:
    """Fraction of the payload's content keywords that also occur in the source.

    Deterministic and dependency-free. ``1.0`` means every content word said
    by the model also appears in the source material; ``0.0`` means nothing it
    said is traceable to the source. This is a coarse lexical estimate of
    grounding, not a semantic claim.
    """
    import re

    source_text = _text_of(source_context).lower()

    def _words(value: str) -> list[str]:
        return [w for w in re.findall(r"[a-z]{4,}", value.lower()) if w not in _STOPWORDS]

    parts: list[str] = []
    for topic in getattr(payload, "topics", []) or []:
        title = getattr(topic, "topic", None)
        description = getattr(topic, "description", None)
        if title:
            parts.append(str(title))
        if description:
            parts.append(str(description))
    if not parts:
        return 0.0

    content_words = _words(" ".join(parts))
    if not content_words:
        return 0.0
    present = sum(1 for w in content_words if w in source_text)
    return round(present / len(content_words), 4)


def _estimate_topic_coverage(topic: Any, source_context: Any) -> float:
    """Coverage estimate for a single topic block (title + description)."""
    import re

    source_text = _text_of(source_context).lower()

    def _words(value: str) -> list[str]:
        return [w for w in re.findall(r"[a-z]{4,}", value.lower()) if w not in _STOPWORDS]

    parts: list[str] = []
    title = getattr(topic, "topic", None)
    description = getattr(topic, "description", None)
    if title:
        parts.append(str(title))
    if description:
        parts.append(str(description))
    content_words = _words(" ".join(parts))
    if not content_words:
        return 0.0
    present = sum(1 for w in content_words if w in source_text)
    return round(present / len(content_words), 4)


def _first_weak_topic(
    payload: Any,
    source_context: Any,
    *,
    coverage_threshold: float,
) -> tuple[Any, str] | None:
    """Return the first topic block whose individual coverage is below the
    threshold (and, in the degenerate all-empty case, the whole payload)."""
    topics = getattr(payload, "topics", None) or []
    for topic in topics:
        topic_cov = _estimate_topic_coverage(topic, source_context)
        label = str(getattr(topic, "topic", "") or "untitled")
        if topic_cov < coverage_threshold:
            return topic, label
    return None


_STOPWORDS = frozenset(
    ["a", "an", "the", "and", "or", "but", "if", "then", "else", "for", "with", "this", "that", "these", "those", "from", "over", "under", "into", "about", "what", "when", "where", "which", "who", "whom", "whose", "your", "their", "our", "its", "of", "to", "in", "on", "at", "by", "as", "per", "before", "after", "during", "will", "would", "could", "should", "may", "might", "must", "not", "no", "yes", "because", "between", "each", "every", "within", "without", "through", "between", "another", "some", "most", "more", "less", "all", "both", "one", "two", "how", "why", "also", "only", "just", "very", "such", "them", "they", "it", "he", "she", "we", "you", "i", "has", "have", "had", "been", "being"]
)


def build_safety_validator(
    name: str | None,
    *,
    ai_service: Any | None = None,
    embedding_provider: Any | None = None,
) -> LessonSafetyValidator:
    """Resolve a validator by name; unknown names fall back to no-op.

    Optional ``ai_service`` (the existing ``AIContentService``) enables the LLM
    grounding verifier when a real provider is configured. Optional
    ``embedding_provider`` enables semantic evidence retrieval; when not
    provided, an instance is resolved from the global config (falling back to
    lexical ranking when embeddings are unavailable).
    """
    if not name or name == "noop":
        return NoopLessonSafetyValidator()
    if name == "grounded":
        return GroundedLessonSafetyValidator(
            ai_service=ai_service,
            embedding_provider=embedding_provider,
        )
    return NoopLessonSafetyValidator()
