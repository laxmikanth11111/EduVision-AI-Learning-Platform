"""Mastery-driven recommendation engine.

Produces structured NextActions based on concept mastery levels.
Deterministic — no AI calls for basic mastery decisions.

Design principles:
  WEAK      → understanding first
  DEVELOPING → practice
  ADVANCED  → deeper/challenging practice
  MASTERED  → progression
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.schemas.educational_memory import EducationalMemory
from app.schemas.next_action import (
    ActionType,
    ActivityType,
    LearningRecommendation,
    NextAction,
    Priority,
)

logger = get_logger(__name__)

# Mastery thresholds (aligned with EducationalMemoryService)
THRESHOLD_WEAK = 50.0
THRESHOLD_DEVELOPING = 85.0
THRESHOLD_ADVANCED = 95.0


def generate_recommendations(
    user_id: str,
    memory: EducationalMemory,
    *,
    max_actions: int = 5,
) -> LearningRecommendation:
    """Generate structured learning recommendations from mastery state.

    This is deterministic — no AI calls.  Rules:

    mastery < 50%  → simplify explanation + visual + prerequisite check
    50-85%         → knowledge check + visual reinforcement
    85-95%         → advanced knowledge check
    > 95%          → move to next concept
    """
    if memory.user_id != user_id:
        logger.warning(
            "user_memory_mismatch",
            requested_user=user_id,
            memory_user=memory.user_id,
        )

    concept_mastery: dict[str, float] = {}
    for cid, record in memory.concept_records.items():
        concept_mastery[cid] = record.mastery_score

    # --- Phase 1: Pick the best action per concept ---
    # Each concept gets at most 2 actions (its most impactful ones).
    # This prevents one weak concept from consuming all slots.
    per_concept: dict[str, list[NextAction]] = {}
    for concept_id, record in memory.concept_records.items():
        per_concept[concept_id] = _actions_for_concept(
            concept_id, record.concept_name, record.mastery_score
        )

    # --- Phase 2: Prioritise concepts, pick best action from each ---
    prioritised_concepts = _prioritise_concepts(memory)
    selected: list[NextAction] = []
    slots_remaining = max_actions

    # Round 1: one best action per prioritised concept
    for concept_id in prioritised_concepts:
        if slots_remaining <= 0:
            break
        candidates = per_concept.get(concept_id, [])
        if candidates:
            selected.append(candidates[0])
            slots_remaining -= 1

    # Round 2: second-best action for the weakest concepts only
    for concept_id in prioritised_concepts:
        if slots_remaining <= 0:
            break
        if concept_id not in memory.weak_concepts:
            continue
        candidates = per_concept.get(concept_id, [])
        if len(candidates) > 1:
            selected.append(candidates[1])
            slots_remaining -= 1

    # --- Phase 3: Deduplicate (same action_type + concept_id) ---
    seen: set[tuple[str, str]] = set()
    deduped: list[NextAction] = []
    for action in selected:
        key = (action.action_type.value, action.concept_id)
        if key not in seen:
            seen.add(key)
            deduped.append(action)
    selected = deduped

    # --- Phase 4: Sort by priority ---
    priority_order = {
        Priority.CRITICAL: 0,
        Priority.HIGH: 1,
        Priority.MEDIUM: 2,
        Priority.LOW: 3,
    }
    selected.sort(key=lambda a: priority_order.get(a.priority, 99))

    # --- Summary ---
    summary = _build_summary(memory)

    return LearningRecommendation(
        user_id=user_id,
        concept_mastery=concept_mastery,
        weak_concepts=memory.weak_concepts,
        developing_concepts=memory.developing_concepts,
        mastered_concepts=memory.mastered_concepts,
        actions=selected,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Prioritisation
# ---------------------------------------------------------------------------

def _prioritise_concepts(memory: EducationalMemory) -> list[str]:
    """Rank concepts by learning priority.

    Weakest concepts first (highest impact on learning).
    Within the same tier, prefer concepts with fewer reviews
    (less practice = more urgent).
    """
    records = list(memory.concept_records.values())
    if not records:
        return []

    # Sort by mastery ascending, then by review_count ascending
    records.sort(key=lambda r: (r.mastery_score, r.review_count))
    return [r.concept_id for r in records]


# ---------------------------------------------------------------------------
# Per-concept action generation
# ---------------------------------------------------------------------------

def _actions_for_concept(
    concept_id: str, concept_name: str, mastery: float
) -> list[NextAction]:
    """Return up to 2 prioritised actions for a single concept."""
    if mastery < THRESHOLD_WEAK:
        return _weak_concept_actions(concept_id, concept_name, mastery)
    if mastery < THRESHOLD_DEVELOPING:
        return _developing_concept_actions(concept_id, concept_name, mastery)
    if mastery < THRESHOLD_ADVANCED:
        return _advanced_concept_actions(concept_id, concept_name, mastery)
    return [_next_concept_action(concept_id, concept_name)]


def _weak_concept_actions(
    concept_id: str, concept_name: str, mastery: float
) -> list[NextAction]:
    """Concept is weak (< 50%). Foundational support."""
    return [
        NextAction(
            action_type=ActionType.SIMPLIFY_EXPLANATION,
            concept_id=concept_id,
            concept_name=concept_name,
            reason=f"Mastery is {mastery:.0f}% — needs a simpler explanation",
            activity_type=ActivityType.EXPLANATION,
            priority=Priority.HIGH,
            title=f"Get a simpler explanation of {concept_name}",
            description=(
                f"Your understanding of {concept_name} needs reinforcement. "
                "Let's try a different approach."
            ),
            metadata={"mastery": mastery, "difficulty": "beginner"},
        ),
        NextAction(
            action_type=ActionType.SHOW_VISUAL,
            concept_id=concept_id,
            concept_name=concept_name,
            reason=f"Mastery is {mastery:.0f}% — visual learning can help",
            activity_type=ActivityType.VISUAL,
            priority=Priority.HIGH,
            title=f"See a visual breakdown of {concept_name}",
            description=(
                f"A visual representation can make {concept_name} easier to understand."
            ),
            metadata={"mastery": mastery},
        ),
    ]


def _developing_concept_actions(
    concept_id: str, concept_name: str, mastery: float
) -> list[NextAction]:
    """Concept is developing (50-85%). Reinforce with practice."""
    return [
        NextAction(
            action_type=ActionType.TAKE_KNOWLEDGE_CHECK,
            concept_id=concept_id,
            concept_name=concept_name,
            reason=f"Mastery is {mastery:.0f}% — ready for practice",
            activity_type=ActivityType.QUIZ,
            priority=Priority.MEDIUM,
            title=f"Test your understanding of {concept_name}",
            description=(
                f"A knowledge check will help solidify your understanding of {concept_name}."
            ),
            metadata={"mastery": mastery, "difficulty": "intermediate"},
        ),
        NextAction(
            action_type=ActionType.SHOW_VISUAL,
            concept_id=concept_id,
            concept_name=concept_name,
            reason=f"Mastery is {mastery:.0f}% — visual reinforcement helps",
            activity_type=ActivityType.VISUAL,
            priority=Priority.LOW,
            title=f"Explore the visual for {concept_name}",
            description="An interactive visual can deepen your understanding.",
            metadata={"mastery": mastery},
        ),
    ]


def _advanced_concept_actions(
    concept_id: str, concept_name: str, mastery: float
) -> list[NextAction]:
    """Concept is advanced (85-95%). Push toward mastery."""
    return [
        NextAction(
            action_type=ActionType.TAKE_KNOWLEDGE_CHECK,
            concept_id=concept_id,
            concept_name=concept_name,
            reason=f"Mastery is {mastery:.0f}% — almost there",
            activity_type=ActivityType.QUIZ,
            priority=Priority.LOW,
            title=f"Final check on {concept_name}",
            description=(
                f"A challenging question to confirm your mastery of {concept_name}."
            ),
            metadata={"mastery": mastery, "difficulty": "advanced"},
        ),
    ]


def _next_concept_action(concept_id: str, concept_name: str) -> NextAction:
    """Concept is mastered (> 95%). Ready to move on."""
    return NextAction(
        action_type=ActionType.MOVE_TO_NEXT_CONCEPT,
        concept_id=concept_id,
        concept_name=concept_name,
        reason="Concept mastered",
        activity_type=ActivityType.EXPLANATION,
        priority=Priority.LOW,
        title=f"Well done! {concept_name} mastered",
        description="You've demonstrated strong understanding. Ready for the next concept.",
        metadata={"mastery": 100.0},
    )


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def _build_summary(memory: EducationalMemory) -> str:
    weak = len(memory.weak_concepts)
    dev = len(memory.developing_concepts)
    mastered = len(memory.mastered_concepts)

    if weak > 0:
        return (
            f"You have {weak} concept{'s' if weak != 1 else ''} needing review, "
            f"{dev} developing, and {mastered} mastered."
        )
    if dev > 0:
        return (
            f"{dev} concept{'s' if dev != 1 else ''} developing, "
            f"{mastered} mastered. Keep going!"
        )
    return (
        f"All {mastered} concept{'s' if mastered != 1 else ''} mastered! "
        "Ready for advanced topics."
    )
