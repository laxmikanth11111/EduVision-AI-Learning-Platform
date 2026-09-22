"""C4 Animation Need Analyzer — decides whether animation genuinely teaches
more than the underlying C3 static visual.

The core educational principle of C4: an animation is only worth generating if
it expresses temporal, causal, sequential, or progressive content that a static
diagram cannot. Decorative motion (spins, zooms, bounces) is a failure, not a
feature — therefore this analyzer deliberately skips content whose benefit is
purely spatial or textual.

The analyzer consumes the C3 visual type that was already planned for the
topic. Animation is always derived from a static visual foundation; without one
there is nothing to animate.
"""

from __future__ import annotations

import re
from typing import Any

from app.core.logging import get_logger
from app.schemas.c3_visual_intelligence import C3VisualType
from app.schemas.c4_animation_intelligence import (
    AnimationNeedDecision,
    C4AnimationType,
)

logger = get_logger(__name__)

MIN_CONTENT_LENGTH_FOR_ANIMATION = 80

# Keywords that indicate inherently temporal/causal/sequential content where
# motion carries meaning rather than decoration.
TEMPORAL_BENEFIT_KEYWORDS: list[str] = [
    "steps",
    "stage",
    "phase",
    "sequence",
    "ordered",
    "first",
    "then",
    "next",
    "finally",
    "order",
    "cause",
    "effect",
    "trigger",
    "triggers",
    "leads to",
    "results in",
    "transition",
    "state change",
    "handshake",
    "request",
    "response",
    "traverse",
    "propagat",
    "ripple",
    "evolves",
    "evolving",
    "progressive",
    "gradually",
    "pipeline",
    "flow",
    "loop",
    "cycle",
    "expires",
    "timeout",
    "procedure",
]

# Causal vocabulary that promotes an animation towards a cause->effect chain.
CAUSAL_KEYWORDS: list[str] = [
    "cause",
    "effect",
    "trigger",
    "leads to",
    "results in",
    "propagat",
    "ripple",
    "depends on",
    "if",
    "when",
]

# C3 visual types whose static form is already temporal enough to animate.
STRONG_TEMPORAL_BASE_SCORE: dict[C3VisualType, float] = {
    C3VisualType.SEQUENCE_DIAGRAM: 0.80,
    C3VisualType.STEP_BY_STEP: 0.80,
    C3VisualType.PROCESS_DIAGRAM: 0.78,
    C3VisualType.STATE_DIAGRAM: 0.80,
    C3VisualType.TIMELINE: 0.78,
    C3VisualType.CYCLE: 0.75,
    C3VisualType.FLOWCHART: 0.70,
    C3VisualType.NETWORK_DIAGRAM: 0.72,
    C3VisualType.SYSTEM_DIAGRAM: 0.70,
    C3VisualType.ARCHITECTURE_DIAGRAM: 0.68,
    C3VisualType.RELATIONSHIP_GRAPH: 0.65,
}

# Visual types that benefit from progressive disclosure even without strong
# temporal vocabulary (e.g. reveal a side-by-side comparison row by row).
MEDIUM_TEMPORAL_BASE_SCORE: dict[C3VisualType, float] = {
    C3VisualType.COMPARISON: 0.65,
    C3VisualType.HIERARCHY: 0.62,
}

# Visual types whose information is entirely static and spatial; animation
# would add decoration, so it is always rejected.
STATIC_ONLY_VISUAL_TYPES: frozenset[C3VisualType] = frozenset(
    {
        C3VisualType.TABLE_VISUALIZATION,
        C3VisualType.CHART,
        C3VisualType.FORMULA_VISUALIZATION,
        C3VisualType.ANNOTATED_ILLUSTRATION,
        C3VisualType.TECHNICAL_DIAGRAM,
        C3VisualType.CONCEPT_MAP,
    }
)

# Preferred animation type candidates for each animatable C3 visual type.
ANIMATION_WORTHY_VISUAL_TYPES: dict[C3VisualType, tuple[C4AnimationType, ...]] = {
    C3VisualType.SEQUENCE_DIAGRAM: (
        C4AnimationType.PROCESS_SEQUENCE,
        C4AnimationType.CAUSE_EFFECT_CHAIN,
    ),
    C3VisualType.STEP_BY_STEP: (C4AnimationType.PROCESS_SEQUENCE,),
    C3VisualType.PROCESS_DIAGRAM: (
        C4AnimationType.PROCESS_SEQUENCE,
        C4AnimationType.CAUSE_EFFECT_CHAIN,
    ),
    C3VisualType.FLOWCHART: (C4AnimationType.PROCESS_SEQUENCE,),
    C3VisualType.STATE_DIAGRAM: (C4AnimationType.STATE_TRANSITION,),
    C3VisualType.TIMELINE: (C4AnimationType.TIMELINE_PROGRESS,),
    C3VisualType.CYCLE: (C4AnimationType.CYCLE_LOOP,),
    C3VisualType.NETWORK_DIAGRAM: (
        C4AnimationType.NETWORK_FLOW,
        C4AnimationType.CAUSE_EFFECT_CHAIN,
    ),
    C3VisualType.SYSTEM_DIAGRAM: (
        C4AnimationType.NETWORK_FLOW,
        C4AnimationType.PROCESS_SEQUENCE,
    ),
    C3VisualType.ARCHITECTURE_DIAGRAM: (
        C4AnimationType.NETWORK_FLOW,
        C4AnimationType.PROCESS_SEQUENCE,
    ),
    C3VisualType.RELATIONSHIP_GRAPH: (
        C4AnimationType.CAUSE_EFFECT_CHAIN,
        C4AnimationType.NETWORK_FLOW,
    ),
    C3VisualType.COMPARISON: (C4AnimationType.COMPARISON_REVEAL,),
    C3VisualType.HIERARCHY: (C4AnimationType.HIERARCHY_ZOOM,),
}


def analyze_animation_need(
    topic_title: str,
    topic_content: str,
    subtopic_title: str | None = None,
    subtopic_content: str | None = None,
    base_visual_type: C3VisualType | None = None,
    concepts: list[dict[str, Any]] | None = None,
    source_references: list[dict[str, Any]] | None = None,
) -> AnimationNeedDecision:
    """Analyze whether animation genuinely advances learning beyond a static
    visual for this topic.

    Returns an AnimationNeedDecision with:
    - animation_needed: True/False
    - reason: educational justification
    - confidence: 0.0-1.0
    - suggested_type: recommended animation type if needed
    - base_visual_type: the C3 visual this animation would derive from
    - skip_reason: why animation was skipped if not needed
    """
    effective_title = subtopic_title or topic_title
    effective_content = subtopic_content or topic_content
    concepts = concepts or []
    _ = source_references or []

    # 1. Animation must derive from an animatable static foundation.
    if base_visual_type is None:
        return AnimationNeedDecision(
            animation_needed=False,
            reason="No C3 visual foundation exists to animate",
            confidence=0.9,
            skip_reason="Topics without a planned visual foundation cannot be animated",
        )
    if base_visual_type in STATIC_ONLY_VISUAL_TYPES:
        return AnimationNeedDecision(
            animation_needed=False,
            reason=f"Visual type '{base_visual_type.value}' is static; animation would be decorative",
            confidence=0.9,
            skip_reason="Static-only visual type is better served by the visual plus text",
        )

    # 2. Skip section-heading fragments (deterministic C2 fallback headings).
    if effective_title.rstrip().endswith(":"):
        return AnimationNeedDecision(
            animation_needed=False,
            reason="Title is a section heading fragment, not an animation-worthy concept",
            confidence=0.9,
            skip_reason="Section-heading subtopic (trailing colon) is better served by text",
        )

    # 3. Skip very short content — too little to animate meaningfully.
    if len(effective_content) < MIN_CONTENT_LENGTH_FOR_ANIMATION:
        return AnimationNeedDecision(
            animation_needed=False,
            reason="Content too short to animate meaningfully",
            confidence=0.9,
            skip_reason="Content below minimum length threshold for animation",
        )

    content_lower = effective_content.lower()
    title_lower = effective_title.lower()

    # 4. Deterministic temporal-interest scoring.
    matched = sorted(
        kw
        for kw in TEMPORAL_BENEFIT_KEYWORDS
        if _contains_signal(kw, content_lower) or _contains_signal(kw, title_lower)
    )
    base_score = STRONG_TEMPORAL_BASE_SCORE.get(base_visual_type) or MEDIUM_TEMPORAL_BASE_SCORE.get(
        base_visual_type, 0.0
    )

    if base_score == 0.0:
        return AnimationNeedDecision(
            animation_needed=False,
            reason=f"Visual type '{base_visual_type.value}' has no temporal animation template",
            confidence=0.85,
            skip_reason="No animation template defined for this visual type",
        )

    benefit_score = base_score + min(len(matched) * 0.05, 0.2)
    has_multiple_temporal_signals = len(matched) >= 2
    has_causal_language = any(
        _contains_signal(kw, content_lower) or _contains_signal(kw, title_lower)
        for kw in CAUSAL_KEYWORDS
    )
    if has_multiple_temporal_signals:
        benefit_score += 0.05
    if has_causal_language and base_visual_type not in (
        C3VisualType.COMPARISON,
        C3VisualType.HIERARCHY,
    ):
        benefit_score += 0.05
    if len(concepts) >= 3:
        benefit_score += 0.05

    confidence = min(0.95, benefit_score)

    candidates = ANIMATION_WORTHY_VISUAL_TYPES.get(base_visual_type, ())
    if not candidates:
        return AnimationNeedDecision(
            animation_needed=False,
            reason=f"Visual type '{base_visual_type.value}' is not animation-worthy",
            confidence=0.9,
            skip_reason="No animation candidates defined for this visual type",
        )

    # 5. Choose the animation type deterministically: prefer a cause->effect
    #    chain over the generic sequencing if the content is causal.
    suggested = candidates[0]
    if has_causal_language and C4AnimationType.CAUSE_EFFECT_CHAIN in candidates:
        suggested = C4AnimationType.CAUSE_EFFECT_CHAIN

    return AnimationNeedDecision(
        animation_needed=True,
        reason=_build_reason(base_visual_type, suggested, effective_title, matched),
        confidence=confidence,
        suggested_type=suggested,
        base_visual_type=base_visual_type,
    )


def _contains_signal(keyword: str, text: str) -> bool:
    # Match whole words; only the explicit propagation stem accepts suffixes.
    suffix = r"\w*\b" if keyword == "propagat" else r"\b"
    return re.search(r"\b" + re.escape(keyword) + suffix, text) is not None


def _build_reason(
    base_visual_type: C3VisualType,
    suggested_type: C4AnimationType,
    title: str,
    matched: list[str],
) -> str:
    """Build a human-readable justification naming what the animation teaches."""
    type_phrases = {
        C4AnimationType.PROCESS_SEQUENCE: "order and pacing of its steps",
        C4AnimationType.CAUSE_EFFECT_CHAIN: "how an effect propagates across the system",
        C4AnimationType.STATE_TRANSITION: "how the system moves between states",
        C4AnimationType.COMPARISON_REVEAL: "side-by-side differences one dimension at a time",
        C4AnimationType.HIERARCHY_ZOOM: "the tree one level at a time",
        C4AnimationType.TIMELINE_PROGRESS: "how the system evolves over time",
        C4AnimationType.CYCLE_LOOP: "how the cycle repeats and feeds back",
        C4AnimationType.NETWORK_FLOW: "how tokens and signals traverse the network",
    }
    phrase = type_phrases.get(suggested_type, "its temporal behaviour")
    coverage = sorted(set(matched))[0] if matched else "temporal"
    return (
        f"Animating '{base_visual_type.value}' as {suggested_type.value} teaches {phrase} "
        f"of '{title}' by guiding attention through each stage (signal: {coverage})."
    )
