"""Dependency-free markdown sanitizer for learner notes.

Notes are stored as markdown and rendered client-side, where raw HTML in the
source is typically passed through the markdown renderer. To keep stored
content safe without a heavy sanitizer dependency (``bleach`` / ``markdown``
are not in the runtime requirements) we:

* neutralise dangerous URL schemes (``javascript:``, ``vbscript:``,
  ``data:text/html``) wherever they appear,
* HTML-escape ``&``, ``<`` and ``>`` so any embedded HTML is rendered as
  literal text instead of being injected.

The returned ``bool`` reports whether the input was modified so callers can
record ``is_sanitized`` faithfully.
"""

from __future__ import annotations

import re

_AMP = re.compile("&")
_LT = re.compile("<")
_GT = re.compile(">")
_DANGEROUS_SCHEME = re.compile(r"(?i)\b(javascript|vbscript|data):")


def _neutralize_schemes(text: str) -> str:
    return _DANGEROUS_SCHEME.sub(lambda m: f"{m.group(1)}&#58;", text)


def sanitize_markdown(content: str) -> tuple[str, bool]:
    """Return ``(sanitized_content, was_modified)``."""
    modified = False
    scrubbed = _neutralize_schemes(content)
    if scrubbed != content:
        modified = True
        content = scrubbed

    # Escape HTML special characters (in this order so entities stay escaped).
    escaped = _AMP.sub("&amp;", content)
    escaped = _LT.sub("&lt;", escaped)
    escaped = _GT.sub("&gt;", escaped)
    if escaped != content:
        modified = True
    return escaped, modified
