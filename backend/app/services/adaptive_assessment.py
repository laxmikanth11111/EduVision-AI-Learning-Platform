"""Deterministic adaptive assessment selection (P12).

Pure, dependency-free ordering and selection logic. There is **no randomness**
and **no AI**: every tie-break is fully deterministic (``band → difficulty fit
→ difficulty rank → bloom rank → position → public_id``), so two servers over
the same learner state, candidates and answered history always produce the
same delivery order.

Signals
-------
* ``Question.difficulty``   — ``"beginner" | "intermediate" | "advanced"``
  (legacy aliases ``easy/medium/hard`` accepted; unknown maps to intermediate).
* ``Question.bloom_level``  — ``"remember" | "understand" | "apply" |
  "analyze" | "evaluate" | "create"``; unknown maps to ``understand``.
* Concept mastery          — the EducationalMemory ``mastery_score``
  (0..100) keyed by *concept public_id*, the same key the review and
  recommendation engines read. Unknown concepts default to 50.0 so brand-new
  learners behave like "developing" and stay fully deterministic.
* Within-attempt answers   — evaluated correct/incorrect history.

Rules (deterministic, documented product behaviour)
---------------------------------------------------
1. **Weak concepts first**: a concept is band 0 (weak, <50), band 1
   (developing, 50–85) or band 2 (mastered, ≥85). Lower bands are delivered
   before higher bands, so the learner closes gaps before being pushed.
2. **Matched difficulty**: each band targets a difficulty —
   weak → beginner(0), developing → intermediate(1), mastered → advanced(2).
   Questions whose difficulty is closest to the band target sort first.
3. **Within-attempt reaction**: every correct answer on a concept raises that
   concept's effective target by one step, every incorrect answer lowers it by
   one step (clamped 0..2). Because selection re-runs against the *updated*
   target, the next question genuinely changes with the learner's answer.
   Generic questions (no concept) share the ``"__generic__"`` bucket so they
   still react deterministically to within-attempt performance.
4. **Stable fallback**: questions without usable metadata degrade to
   position/public_id ordering — still deterministic, never random.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

# Mastery band boundaries — must mirror the EducationalMemory categorisation in
# ``app/services/educational_memory_service.py`` (mastered ≥85, developing
# 50–85, weak <50).
MASTERY_DEVELOPING = 50.0
MASTERY_MASTERED = 85.0

GENERIC_CONCEPT_KEY = "__generic__"

_MIN_TARGET = 0
_MAX_TARGET = 2

# Difficulty vocabulary used across the platform (see quiz generation).
DIFFICULTY_RANK = {
    "beginner": 0,
    "easy": 0,
    "intermediate": 1,
    "medium": 1,
    "advanced": 2,
    "hard": 2,
}
_UNKNOWN_DIFFICULTY_RANK = 1

# Bloom's taxonomy — higher-order thinking ranks above recall.
BLOOM_RANK = {
    "remember": 1,
    "understand": 2,
    "apply": 3,
    "analyze": 4,
    "evaluate": 5,
    "create": 6,
}
_UNKNOWN_BLOOM_RANK = 2

# Rationale strings — short, deterministic, learner friendly.
RATIONALE_START = "Matched to your current mastery level."
RATIONALE_CORRECT = "Stepping up after a correct answer."
RATIONALE_INCORRECT = "Returning to an easier level to build your confidence."


def rank_difficulty(value: str | None) -> int:
    """Map a difficulty label to a stable rank (0 beginner .. 2 advanced)."""
    if not value:
        return _UNKNOWN_DIFFICULTY_RANK
    return DIFFICULTY_RANK.get(value.strip().lower(), _UNKNOWN_DIFFICULTY_RANK)


def rank_bloom(value: str | None) -> int:
    """Map a Bloom level to a stable rank (1 remember .. 6 create)."""
    if not value:
        return _UNKNOWN_BLOOM_RANK
    return BLOOM_RANK.get(value.strip().lower(), _UNKNOWN_BLOOM_RANK)


def band_for_mastery(mastery_score: float) -> int:
    """0 = weak, 1 = developing, 2 = mastered."""
    if mastery_score < MASTERY_DEVELOPING:
        return 0
    if mastery_score < MASTERY_MASTERED:
        return 1
    return 2


def _band_target(band: int) -> int:
    """Difficulty rank a band is measured against (weak→0 .. mastered→2)."""
    targets = {
        0: 0,
        1: 1,
        2: 2,
    }
    return targets[band]


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


class AdaptiveCandidate:
    """A question ready to be delivered, annotated for adaptive ordering."""

    __slots__ = (
        "question_public_id",
        "position",
        "difficulty_rank",
        "bloom_rank",
        "concept_key",
        "mastery_score",
    )

    def __init__(
        self,
        *,
        question_public_id: str,
        position: int,
        difficulty: str | None,
        bloom_level: str | None,
        concept_key: str | None,
        mastery_score: float,
    ) -> None:
        self.question_public_id = question_public_id
        self.position = position
        self.difficulty_rank = rank_difficulty(difficulty)
        self.bloom_rank = rank_bloom(bloom_level)
        self.concept_key = concept_key
        self.mastery_score = mastery_score

    @property
    def band(self) -> int:
        """Mastery band of this question's concept (0 weak .. 2 mastered)."""
        return band_for_mastery(self.mastery_score)

    @property
    def base_target(self) -> int:
        """Difficulty targeted for this question's band before within-attempt adjustment."""
        return _band_target(self.band)


class AnsweredQuestion:
    """A single evaluated answer already given within the attempt."""

    __slots__ = ("concept_key", "is_correct")

    def __init__(self, *, concept_key: str | None, is_correct: bool) -> None:
        self.concept_key = concept_key
        self.is_correct = is_correct


def _bucket(concept_key: str | None) -> str:
    return concept_key if concept_key else GENERIC_CONCEPT_KEY


def mastery_deltas(answered: Sequence[AnsweredQuestion]) -> dict[str, int]:
    """Per-concept within-attempt target deltas from answered correctness.

    Each correct answer lifts a concept's effective target by one step, each
    incorrect answer lowers it by one (clamped so ``target + delta`` stays in
    ``0..2``). Generic questions share one bucket so they still adapt
    deterministically without a concept record.
    """
    deltas: dict[str, int] = {}
    for item in answered:
        key = _bucket(item.concept_key)
        delta = deltas.get(key, 0)
        if item.is_correct:
            delta = _clamp(delta + 1, -(_MAX_TARGET - _MIN_TARGET), _MAX_TARGET - _MIN_TARGET)
        else:
            delta = _clamp(delta - 1, -(_MAX_TARGET - _MIN_TARGET), _MAX_TARGET - _MIN_TARGET)
        deltas[key] = delta
    return deltas


def effective_target(candidate: AdaptiveCandidate, deltas: dict[str, int]) -> int:
    """Difficulty this candidate should be compared against right now."""
    return _clamp(candidate.base_target + deltas.get(_bucket(candidate.concept_key), 0), _MIN_TARGET, _MAX_TARGET)


def _selection_key(candidate: AdaptiveCandidate, deltas: dict[str, int]) -> tuple[Any, ...]:
    """Full deterministic ordering key: band, fit, difficulty, bloom, position, id."""
    target = effective_target(candidate, deltas)
    fit = abs(candidate.difficulty_rank - target)
    return (
        candidate.band,
        fit,
        candidate.difficulty_rank,
        candidate.bloom_rank,
        candidate.position,
        candidate.question_public_id,
    )


def order_candidate_questions(
    candidates: Sequence[AdaptiveCandidate],
    answered: Sequence[AnsweredQuestion] = (),
) -> list[AdaptiveCandidate]:
    """Return candidates in adaptive delivery order (deterministic).

    With no answered history this is the initial "weak concepts at matched
    difficulty first" ordering used by ``start_attempt``. With answered history
    the band targets have moved, so the order genuinely reacts to the learner.
    """
    deltas = mastery_deltas(answered)
    return sorted(candidates, key=lambda c: _selection_key(c, deltas))


def select_next_question(
    candidates: Sequence[AdaptiveCandidate],
    answered: Sequence[AnsweredQuestion] = (),
) -> tuple[AdaptiveCandidate | None, str]:
    """Pick the next adaptive question and a short, deterministic rationale.

    Returns ``(None, "")`` when no candidates remain (attempt complete).
    """
    ordered = order_candidate_questions(candidates, answered)
    if not ordered:
        return None, ""
    return ordered[0], _rationale(answered)


def _rationale(answered: Sequence[AnsweredQuestion]) -> str:
    last = answered[-1] if answered else None
    if last is None:
        return RATIONALE_START
    if last.is_correct:
        return RATIONALE_CORRECT
    return RATIONALE_INCORRECT
