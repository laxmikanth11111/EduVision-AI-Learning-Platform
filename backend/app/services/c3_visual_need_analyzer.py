"""C3 Visual Need Analyzer — determines whether a visual genuinely helps learning.

The analyzer inspects topic/subtopic content and decides if a visual would improve
understanding. Not every concept benefits from a visual — text may be sufficient.
A decorative visual that doesn't teach is worse than no visual.
"""

from __future__ import annotations

import re
from typing import Any

from app.core.logging import get_logger
from app.schemas.c3_visual_intelligence import (
    C3VisualType,
    VisualNeedDecision,
)

logger = get_logger(__name__)

# Keywords indicating content that benefits from visual representation
VISUAL_BENEFIT_KEYWORDS: dict[str, list[str]] = {
    "process": ["process", "steps", "stages", "flow", "pipeline", "workflow", "procedure"],
    "architecture": ["architecture", "system", "layers", "modules", "components", "structure"],
    "comparison": ["compare", "versus", "vs", "difference", "similarities", "contrast", "types"],
    "hierarchy": ["hierarchy", "levels", "tiers", "parent", "child", "tree", "classification"],
    "network": ["network", "connections", "topology", "nodes", "links", "protocols"],
    "cycle": ["cycle", "loop", "feedback", "recurrence", "phases", "循环"],
    "timeline": ["timeline", "history", "evolution", "chronological", "milestones"],
    "relationship": ["relationship", "depends", "requires", "triggers", "causes", "relates"],
    "sequence": ["sequence", "order", "execution", "request.*response", "handshake"],
    "state": ["state", "transition", "mode", "status", "lifecycle", "finite.*machine"],
    "diagram": ["diagram", "schema", "blueprint", "map", "model", "representation"],
    "formula": ["formula", "equation", "theorem", "derivation", "proof", "calculation"],
    "table": ["table", "matrix", "specification", "properties", "features", "attributes"],
    "data_flow": ["data.*flow", "pipeline", "source.*sink", "transformation", "etl"],
}

# Keywords indicating content that does NOT benefit from visuals
TEXT_PREFERRED_KEYWORDS: list[str] = [
    "definition",
    "glossary",
    "introduction",
    "overview",
    "summary",
    "acknowledgment",
    "biography",
    "reference",
    "citation",
    "appendix",
]

# Content length thresholds
MIN_CONTENT_LENGTH_FOR_VISUAL = 50
MAX_CONTENT_LENGTH_FOR_SINGLE_VISUAL = 5000


def analyze_visual_need(
    topic_title: str,
    topic_content: str,
    subtopic_title: str | None = None,
    subtopic_content: str | None = None,
    concepts: list[dict[str, Any]] | None = None,
    source_references: list[dict[str, Any]] | None = None,
) -> VisualNeedDecision:
    """Analyze whether a visual would genuinely help a learner understand this content.

    Returns a VisualNeedDecision with:
    - visual_needed: True/False
    - reason: educational justification
    - confidence: 0.0-1.0
    - suggested_type: recommended visual type if needed
    - skip_reason: why visual was skipped if not needed
    """
    effective_title = subtopic_title or topic_title
    effective_content = subtopic_content or topic_content
    concepts = concepts or []

    content_lower = effective_content.lower()
    title_lower = effective_title.lower()

    # 1. Skip section/heading fragments (e.g. "Physical scope and scale:")
    #    Deterministic C2 fallback can surface headings as subtopics; a trailing
    #    colon marks a heading, not a concept worth a full diagram.
    if effective_title.rstrip().endswith(":"):
        return VisualNeedDecision(
            visual_needed=False,
            reason="Title is a section heading fragment, not a visual-worthy concept",
            confidence=0.9,
            skip_reason="Section-heading subtopic (trailing colon) is better served by text",
        )

    # 2. Skip very short content — text is sufficient
    if len(effective_content) < MIN_CONTENT_LENGTH_FOR_VISUAL:
        return VisualNeedDecision(
            visual_needed=False,
            reason="Content too short for a meaningful visual",
            confidence=0.9,
            skip_reason="Content below minimum length threshold",
        )

    # 2. Skip text-preferred content types
    for keyword in TEXT_PREFERRED_KEYWORDS:
        if keyword in title_lower:
            return VisualNeedDecision(
                visual_needed=False,
                reason=f"Content type '{keyword}' is better served by text",
                confidence=0.85,
                skip_reason=f"Title contains text-preferred keyword: {keyword}",
            )

    # 3. Detect the best visual type based on content analysis
    detected_type, type_confidence = _detect_visual_type(effective_title, content_lower, concepts)

    # 4. Check for list/enumeration patterns (good for comparison/hierarchy)
    has_list_pattern = bool(re.search(r"[\n•\-\d]+[.)]\s", effective_content))
    has_table_like = "table" in content_lower or "|" in effective_content
    has_numbered_steps = bool(re.search(r"step\s*\d|phase\s*\d|\d+\.\s", content_lower))

    # 5. Score the visual benefit
    benefit_score = 0.0
    matched_categories: list[str] = []

    for category, keywords in VISUAL_BENEFIT_KEYWORDS.items():
        for kw in keywords:
            if re.search(kw, content_lower) or re.search(kw, title_lower):
                benefit_score += 0.15
                matched_categories.append(category)
                break

    # Boost score for structural patterns
    if has_list_pattern:
        benefit_score += 0.1
    if has_table_like:
        benefit_score += 0.15
    if has_numbered_steps:
        benefit_score += 0.12

    # Boost for multiple concepts (relationships benefit from visuals)
    if len(concepts) >= 3:
        benefit_score += 0.1
    if len(concepts) >= 5:
        benefit_score += 0.1

    # Reduce benefit for very long content (might need multiple visuals)
    if len(effective_content) > MAX_CONTENT_LENGTH_FOR_SINGLE_VISUAL:
        benefit_score -= 0.05

    # 6. Decision threshold
    if benefit_score >= 0.3:
        suggested = detected_type or _infer_type_from_categories(matched_categories)
        confidence = min(0.95, type_confidence + 0.1)
        return VisualNeedDecision(
            visual_needed=True,
            reason=_build_reason(matched_categories, effective_title),
            confidence=confidence,
            suggested_type=suggested,
        )

    # 7. Low benefit — skip
    return VisualNeedDecision(
        visual_needed=False,
        reason="Content does not significantly benefit from visual representation",
        confidence=max(0.6, 0.9 - benefit_score),
        skip_reason=f"Benefit score {benefit_score:.2f} below threshold 0.3",
    )


def _detect_visual_type(
    title: str,
    content_lower: str,
    concepts: list[dict[str, Any]],
) -> tuple[C3VisualType | None, float]:
    """Detect the most appropriate visual type from content analysis."""
    type_scores: dict[C3VisualType, float] = {
        C3VisualType.FLOWCHART: 0.0,
        C3VisualType.PROCESS_DIAGRAM: 0.0,
        C3VisualType.COMPARISON: 0.0,
        C3VisualType.HIERARCHY: 0.0,
        C3VisualType.CONCEPT_MAP: 0.0,
        C3VisualType.TIMELINE: 0.0,
        C3VisualType.CYCLE: 0.0,
        C3VisualType.NETWORK_DIAGRAM: 0.0,
        C3VisualType.SEQUENCE_DIAGRAM: 0.0,
        C3VisualType.STEP_BY_STEP: 0.0,
        C3VisualType.TABLE_VISUALIZATION: 0.0,
        C3VisualType.ARCHITECTURE_DIAGRAM: 0.0,
        C3VisualType.STATE_DIAGRAM: 0.0,
        C3VisualType.FORMULA_VISUALIZATION: 0.0,
        C3VisualType.RELATIONSHIP_GRAPH: 0.0,
    }

    # Flowchart signals
    if any(
        kw in content_lower for kw in ("flow", "pipeline", "workflow", "step by step", "sequential")
    ):
        type_scores[C3VisualType.FLOWCHART] += 0.3
    if any(kw in content_lower for kw in ("process", "stages", "procedure")):
        type_scores[C3VisualType.PROCESS_DIAGRAM] += 0.3

    # Comparison signals
    if any(kw in content_lower for kw in ("versus", "vs", "compare", "comparison", "difference")):
        type_scores[C3VisualType.COMPARISON] += 0.4
    if any(kw in title.lower() for kw in ("comparison", "versus", "vs")):
        type_scores[C3VisualType.COMPARISON] += 0.2

    # Hierarchy signals
    if any(
        kw in content_lower for kw in ("hierarchy", "levels", "tree", "parent", "child", "taxonomy")
    ):
        type_scores[C3VisualType.HIERARCHY] += 0.35

    # Timeline signals
    if any(kw in content_lower for kw in ("timeline", "history", "evolution", "chronological")):
        type_scores[C3VisualType.TIMELINE] += 0.4

    # Cycle signals
    if any(kw in content_lower for kw in ("cycle", "loop", "feedback", "recurrence")):
        type_scores[C3VisualType.CYCLE] += 0.4

    # Network signals
    if any(kw in content_lower for kw in ("network", "topology", "connected", "nodes")):
        type_scores[C3VisualType.NETWORK_DIAGRAM] += 0.35

    # Sequence signals
    if any(
        kw in content_lower
        for kw in ("sequence", "handshake", "request.*response", "message.*passing")
    ):
        type_scores[C3VisualType.SEQUENCE_DIAGRAM] += 0.4

    # Step-by-step signals
    if any(kw in content_lower for kw in ("step", "phase", "stage", "iteration")):
        type_scores[C3VisualType.STEP_BY_STEP] += 0.25

    # Table signals
    if any(kw in content_lower for kw in ("table", "matrix", "specification", "properties")):
        type_scores[C3VisualType.TABLE_VISUALIZATION] += 0.35

    # Architecture signals
    if any(kw in content_lower for kw in ("architecture", "system design", "layers", "modules")):
        type_scores[C3VisualType.ARCHITECTURE_DIAGRAM] += 0.35

    # State machine signals
    if any(kw in content_lower for kw in ("state", "transition", "finite state", "mode")):
        type_scores[C3VisualType.STATE_DIAGRAM] += 0.35

    # Formula signals
    if any(kw in content_lower for kw in ("formula", "equation", "theorem", "derivation")):
        type_scores[C3VisualType.FORMULA_VISUALIZATION] += 0.35

    # Relationship signals
    if len(concepts) >= 3:
        type_scores[C3VisualType.RELATIONSHIP_GRAPH] += 0.2
        type_scores[C3VisualType.CONCEPT_MAP] += 0.2

    # Find the winner
    best_type = max(type_scores, key=lambda t: type_scores[t])
    best_score = type_scores[best_type]

    if best_score < 0.15:
        return None, 0.5

    return best_type, min(0.95, 0.6 + best_score)


def _infer_type_from_categories(categories: list[str]) -> C3VisualType:
    """Infer visual type from detected content categories."""
    category_type_map: dict[str, C3VisualType] = {
        "process": C3VisualType.PROCESS_DIAGRAM,
        "architecture": C3VisualType.ARCHITECTURE_DIAGRAM,
        "comparison": C3VisualType.COMPARISON,
        "hierarchy": C3VisualType.HIERARCHY,
        "network": C3VisualType.NETWORK_DIAGRAM,
        "cycle": C3VisualType.CYCLE,
        "timeline": C3VisualType.TIMELINE,
        "relationship": C3VisualType.RELATIONSHIP_GRAPH,
        "sequence": C3VisualType.SEQUENCE_DIAGRAM,
        "state": C3VisualType.STATE_DIAGRAM,
        "diagram": C3VisualType.CONCEPT_MAP,
        "formula": C3VisualType.FORMULA_VISUALIZATION,
        "table": C3VisualType.TABLE_VISUALIZATION,
        "data_flow": C3VisualType.FLOWCHART,
    }

    for cat in categories:
        if cat in category_type_map:
            return category_type_map[cat]

    return C3VisualType.CONCEPT_MAP


def _build_reason(categories: list[str], title: str) -> str:
    """Build a human-readable reason for the visual need decision."""
    if not categories:
        return f"Content about '{title}' would benefit from visual representation"

    category_descriptions = {
        "process": "Sequential process stages are best understood visually",
        "architecture": "System architecture is inherently visual",
        "comparison": "Comparing multiple items benefits from side-by-side layout",
        "hierarchy": "Hierarchical structures are naturally tree-shaped",
        "network": "Network topologies require visual node-edge representation",
        "cycle": "Cyclical processes are best shown as circular diagrams",
        "timeline": "Chronological sequences benefit from timeline layout",
        "relationship": "Multiple related concepts benefit from a relationship graph",
        "sequence": "Sequential interactions are clearest as sequence diagrams",
        "state": "State machines require visual state-transition diagrams",
        "diagram": "Conceptual diagrams improve understanding",
        "formula": "Mathematical relationships benefit from visual structure",
        "table": "Structured data benefits from tabular visualization",
        "data_flow": "Data flows are best traced through visual pipelines",
    }

    primary = categories[0]
    desc = category_descriptions.get(primary, "Visual representation improves comprehension")
    return f"{desc} — {title}"
