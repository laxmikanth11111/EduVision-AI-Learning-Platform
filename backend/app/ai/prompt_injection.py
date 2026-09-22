"""Deterministic prompt-injection defense for untrusted AI inputs.

Uploaded educational documents and learner messages are treated as DATA, never
as instructions. This module provides a lightweight, deterministic lexical
detector that flags instruction-override, system-reveal, jailbreak, and tool-
invocation patterns in arbitrary text (document content, user messages, model
context) so AI pipelines can reject or sandbox hostile input before it reaches
a model prompt.

The detector is deliberately high-precision: each rule carries a weight and the
overall decision is score-based against ``settings.AI_PROMPT_INJECTION_THRESHOLD``.
Benign academic content (e.g. a lesson titled "What is a system prompt?") will
only ever contribute a low-weight single match and will not be flagged.

This is defense-in-depth, not a claim of complete immunity. It complements the
delimiter-fenced context boundaries already used by the prompt builders.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.core.error_codes import ErrorCode
from app.core.exceptions import EduVisionError
from app.core.logging import get_logger
from app.observability.metrics import metrics

logger = get_logger(__name__)


class AIInputSecurityError(EduVisionError):
    """Raised when the central gateway scan blocks an AI request."""

    def __init__(
        self,
        message: str = "AI request blocked by input security scan",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=ErrorCode.SAFETY_ERROR,
            status_code=422,
            details=details,
        )


@dataclass(frozen=True)
class InjectionScanResult:
    """Outcome of scanning one blob of untrusted text."""

    flagged: bool
    score: float
    matched_rules: tuple[str, ...] = field(default_factory=tuple)


# (rule_name, compiled pattern, weight)
# Weights: 3 = direct instruction override / jailbreak, 2 = system-boundary
# reveal, 1 = weak indicator that alone should never flag.
_INJECTION_RULES: tuple[tuple[str, re.Pattern[str], float], ...] = tuple(
    (name, re.compile(pattern, re.IGNORECASE), weight)
    for name, pattern, weight in (
        ("ignore_previous", r"\bignore\s+all?\s+(previous|prior)\s+(instructions|prompts?|context|text)", 3.0),
        ("override_instructions", r"\b(override|replace|change|disregard|forget)\s+(all\s+|your\s+)?(previous\s+)?instructions", 3.0),
        ("bypass_safety", r"\b(bypass|ignore|disregard)\s+(the\s+|your\s+)?(safety|content|policy|guidelines?)\b", 3.0),
        ("new_persona", r"\byou\s+are\s+now\s+(an?\s+)?(uncensored|unrestricted|free|another|a\s+different|a\s+new)\b", 2.0),
        ("reveal_system_prompt", r"\b(reveal|show|share|print|repeat|output|paste)\s+(your\s+|the\s+)?(system\s+)?prompt\b", 2.0),
        ("reveal_instructions", r"\b(reveal|show|share|print|repeat|output|paste)\s+(your\s+|the\s+)?(developer\s+)?instructions\b", 2.0),
        ("jailbreak", r"\bjail\s*break\b|\bDAN\s+mode\b|\bdeveloper\s+mode\b", 3.0),
        ("tool_invoke", r"\b(call|invoke|use|execute)\s+(the\s+)?(tool|function|api|action)\b", 1.5),
        ("unfi_behavior", r"\b(say|do|act|respond)\s+(anything|whatever)\b", 2.0),
        ("system_masquerade", r"\b(?:system|developer|admin)\b\s*[:\-]\s*you\s+must\b", 3.0),
        ("exfil_secrets", r"\b(output|reveal)\s+(the\s+)?(secrets?|private|internal)\b", 2.0),
        ("disregard_source", r"\bdisregard\s+the\s+(source|context|previous)\b", 3.0),
        ("execute_this_instruction", r"\bexecute\s+this\s+instruction\b", 2.0),
        ("weak_no_restrictions", r"\bno\s+restrictions\b|\bno\s+rules\b|\buncensored\b", 1.0),
    )
)

_RULE_WEIGHTS: dict[str, float] = {name: weight for name, _, weight in _INJECTION_RULES}
_STRONG_WEIGHT = 2.0


def scan_for_prompt_injection(
    text: str | None,
    *,
    threshold: float = 3.0,
) -> InjectionScanResult:
    """Scan untrusted text for instruction-override / system-reveal patterns.

    Returns a frozen result with a total score and the matched rule names. Only
    rules whose pattern matches are added to ``matched_rules``; the score is the
    sum of the weights of every distinct rule that matched (a rule counts at
    most once per scan, regardless of how many times its pattern appears, so
    repetition alone cannot inflate the score).

    ``flagged`` is ``True`` iff ``score >= threshold``.
    """
    if not text:
        return InjectionScanResult(flagged=False, score=0.0, matched_rules=())

    score = 0.0
    matched: list[str] = []
    for name, pattern, weight in _INJECTION_RULES:
        if pattern.search(text):
            score += weight
            matched.append(name)

    return InjectionScanResult(
        flagged=score >= threshold,
        score=score,
        matched_rules=tuple(matched),
    )


def guard_ai_request(request: object) -> None:
    """Central gateway check: scan all untrusted text surfaces in an AIRequest.

    Scans ``user_prompt``, ``system_prompt``, and every ``messages[*].content``.
    Raises ``AIInputSecurityError`` when the scanner detects a reliable injection
    pattern.  Only fires when ``request.scan_for_injection`` is ``True`` and
    ``settings.AI_PROMPT_INJECTION_ENABLED`` is ``True``.
    """
    if not getattr(request, "scan_for_injection", False):
        return

    from app.core.config import settings

    if not settings.AI_PROMPT_INJECTION_ENABLED:
        return

    threshold = settings.AI_PROMPT_INJECTION_THRESHOLD
    surfaces: list[tuple[str, str]] = []

    user_prompt = getattr(request, "user_prompt", "")
    if user_prompt:
        surfaces.append(("user_prompt", user_prompt))

    system_prompt = getattr(request, "system_prompt", None)
    if system_prompt:
        surfaces.append(("system_prompt", system_prompt))

    messages = getattr(request, "messages", None) or []
    for idx, msg in enumerate(messages):
        content = getattr(msg, "content", None)
        if content:
            surfaces.append((f"messages[{idx}].content", content))

    for label, text in surfaces:
        result = scan_for_prompt_injection(text, threshold=threshold)
        if is_reliably_flagged(result):
            metrics.increment(
                "ai_gateway_injection_blocked_total",
                surface=label,
                rules=",".join(result.matched_rules),
            )
            logger.warning(
                "ai_gateway_injection_blocked",
                surface=label,
                matched_rules=list(result.matched_rules),
            )
            raise AIInputSecurityError(
                message=(
                    "The AI request was blocked because the input contains "
                    "instruction-override or system-reveal patterns that could "
                    "manipulate the learning model."
                ),
                details={
                    "surface": label,
                    "matched_rules": list(result.matched_rules),
                },
            )


def is_reliably_flagged(result: InjectionScanResult) -> bool:
    """True when a scan matched a *strong* rule (weight >= 2).

    Strong rules are unambiguous instruction-override, persona-shift, or
    system-boundary-reveal intent. Their presence alone is enough for the
    blocking path even if the combined score is below the soft-flag threshold.
    Weak-only matches (for example a slide that merely mentions "no
    restrictions" inside a lesson about responsible AI) are never reliable.
    """
    return any(
        _RULE_WEIGHTS.get(name, 0.0) >= _STRONG_WEIGHT for name in result.matched_rules
    )
