"""Deterministic token estimation helpers.

Providers that do not report token usage (e.g. some local/self-hosted
endpoints) fall back to these heuristics. Estimations are intentionally
conservative and deterministic so they are testable.
"""

from __future__ import annotations

import math
import re

_WORD_TOKEN_FACTOR = 1.3
_PUNCTUATION_TOKENS = 0.5

_WHITESPACE_RE = re.compile(r"\s+")
_SENTENCE_BOUNDARY_RE = re.compile(r"[.!?…]")


def estimate_tokens(text: str) -> int:
    """Estimate the number of tokens in ``text``.

    Uses a hybrid heuristic: words * factor + punctuation counts. Returns at
    least 1 for any non-empty input and 0 for empty input.
    """
    if not text or not text.strip():
        return 0

    normalized = _WHITESPACE_RE.sub(" ", text.strip())
    word_count = len(normalized.split())
    punctuation_count = len(_SENTENCE_BOUNDARY_RE.findall(text))

    raw = (word_count * _WORD_TOKEN_FACTOR) + (punctuation_count * _PUNCTUATION_TOKENS)
    return max(1, math.ceil(raw))


def estimate_request_tokens(
    user_prompt: str,
    system_prompt: str | None = None,
    messages: list[dict[str, str]] | None = None,
) -> int:
    """Estimate the input/prompt token count for a request."""
    total = estimate_tokens(user_prompt)
    if system_prompt:
        total += estimate_tokens(system_prompt)
    if messages:
        for message in messages:
            total += estimate_tokens(message.get("content", ""))
    return total
