"""Deterministic review-outcome & retention helpers (P14).

Pure, side-effect-free functions that turn a learner's self-reported recall
outcome into (a) a spacing decision and (b) an honest retention signal. Mirrors
the ``learner_analytics.py`` / ``adaptive_assessment.py`` style: no database,
no AI, no ML — the same inputs always yield the same outputs.

Contracts (P14 scope, §6/§8):
  * Small controlled outcome vocabulary — ``again`` / ``hard`` / ``good`` /
    ``easy`` (successful / partial-uncertain / failed recall are distinguished;
    ``good`` is the default so legacy callers keep today's exact behavior).
  * Outcome -> next ladder step is deterministic and bounded: ``again`` -> 0,
    ``hard`` -> hold, ``good`` -> +1, ``easy`` -> +2 (capped at MAX_STEP).
  * Outcome history + per-outcome counts persist inside the existing
    ``review_metadata`` JSONB (versioned ``"v": 2``, history capped at
    ``MAX_HISTORY``), fully backward compatible with pre-P14 rows.
  * ``retention_signal`` derives OBSERVED RECALL (weighted recent outcomes,
    decayed by time since review) — it NEVER rewrites the quiz-owned mastery
    scalar and is clearly distinct from ``review_accuracy``.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from app.services.review_scheduler import MAX_STEP, interval_at_step

# Shared, controlled outcome vocabulary (validated strictly at the API too).
OUTCOME_AGAIN = "again"  # failed / forgotten recall
OUTCOME_HARD = "hard"  # partial / uncertain recall
OUTCOME_GOOD = "good"  # successful recall (the default path)
OUTCOME_EASY = "easy"  # very successful recall (skip-ahead)
REVIEW_OUTCOMES: tuple[str, ...] = (
    OUTCOME_AGAIN,
    OUTCOME_HARD,
    OUTCOME_GOOD,
    OUTCOME_EASY,
)
DEFAULT_OUTCOME = OUTCOME_GOOD

# Outcome history is capped so ``review_metadata`` JSONB growth stays bounded
# on every schedule regardless of how often a learner reviews.
MAX_HISTORY = 20
# Version stamp written by P14 under ``review_metadata["v"]``.
METADATA_VERSION = 2

# Retention statuses surfaced to the learner (D1-B).
STATUS_ON_TRACK = "on_track"
STATUS_AT_RISK = "at_risk"
STATUS_OVERDUE = "overdue"
STATUS_NEW = "new"
STATUS_COMPLETED = "completed"

# Self-reported accuracy "bands" shown with the retained strength (0-100).
BAND_STRONG = "strong"
BAND_DEVELOPING = "developing"
BAND_WEAK = "weak"

# Deterministic recall weighting: the most recent outcomes carry the most
# weight; these constants make the signal stable and testable.
_OUTCOME_WEIGHT: dict[str, float] = {
    OUTCOME_AGAIN: 0.0,
    OUTCOME_HARD: 0.5,
    OUTCOME_GOOD: 0.85,
    OUTCOME_EASY: 1.0,
}
_RECENT_WINDOW = 3
_RECENT_WEIGHTS = (0.5, 0.3, 0.2)  # newest -> older
# Retained strength erodes by recency: after this many days unreviewed it hits 0.
_DECAY_HORIZON_DAYS = 30.0
# Strength at/above this is reported as "on track".
_STRENGTH_ON_TRACK = 80.0
_STRENGTH_WEAK = 50.0

# Deterministic sort order for learner surfaces (overdue first).
_STATUS_SORT: dict[str, int] = {
    STATUS_OVERDUE: 0,
    STATUS_AT_RISK: 1,
    STATUS_ON_TRACK: 2,
    STATUS_NEW: 3,
    STATUS_COMPLETED: 4,
}


def validate_outcome(outcome: str) -> str:
    """Return the outcome if it is in the controlled vocabulary else raise."""
    if outcome not in REVIEW_OUTCOMES:
        raise ValueError(f"invalid review outcome: {outcome!r}")
    return outcome


def outcome_next_step(step: int, outcome: str) -> int:
    """Map a recall outcome onto the next ladder step (deterministic, bounded).

    ``again`` -> 0 (tightest interval; lapse), ``hard`` -> hold the step,
    ``good`` -> +1 (today's progression), ``easy`` -> +2 capped at ``MAX_STEP``.
    """
    validate_outcome(outcome)
    base = max(0, int(step))
    if outcome == OUTCOME_AGAIN:
        candidate = 0
    elif outcome == OUTCOME_HARD:
        candidate = base
    elif outcome == OUTCOME_GOOD:
        candidate = base + 1
    else:  # OUTCOME_EASY
        candidate = base + 2
    return min(candidate, MAX_STEP)


def outcome_interval_days(step: int, outcome: str) -> int:
    """Interval in days after applying an outcome to a current step."""
    return interval_at_step(outcome_next_step(step, outcome))


# ---------------------------------------------------------------------------
# review_metadata JSONB helpers (D1-E: bounded, versioned, backward compatible)
# ---------------------------------------------------------------------------


def _entry_outcome(entry: Any) -> str | None:
    """Tolerantly read a history entry's outcome value (None for junk)."""
    if isinstance(entry, dict):
        value = entry.get("outcome")
        if isinstance(value, str) and value in REVIEW_OUTCOMES:
            return value
    return None


def _history_entries(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    """Return valid history entries from metadata (raw shape preserved)."""
    if not isinstance(metadata, dict):
        return []
    raw = metadata.get("history")
    if not isinstance(raw, list):
        return []
    entries = [dict(item) for item in raw if isinstance(item, dict) and _entry_outcome(item)]
    return entries[-MAX_HISTORY:]


def history_outcomes(metadata: dict[str, Any] | None) -> list[str]:
    """Extract the chronological outcome list from review metadata (tolerant)."""
    if not isinstance(metadata, dict):
        return []
    return [entry["outcome"] for entry in _history_entries(metadata)]


def last_outcome(metadata: dict[str, Any] | None) -> str | None:
    """Most recent recorded outcome, or ``None`` when nothing is recorded yet."""
    outcomes = history_outcomes(metadata)
    return outcomes[-1] if outcomes else None


def apply_outcome_to_metadata(
    metadata: dict[str, Any] | None,
    outcome: str,
    at: datetime,
) -> dict[str, Any]:
    """Merge one recall outcome into a copy of the schedule's review_metadata.

    Backward compatible: pre-P14 rows (no ``v`` / no ``history``) are merged in
    place; every existing key (``step``, ``last_pressure``, ``skipped_at`` …)
    is preserved; history is capped at ``MAX_HISTORY``; per-outcome counts are
    fixed-size. Malformed/missing metadata degrades to a fresh, valid shape.
    """
    validate_outcome(outcome)
    merged = dict(metadata) if isinstance(metadata, dict) else {}
    entries = _history_entries(merged)
    entries.append({"outcome": outcome, "at": at.isoformat()})
    entries = entries[-MAX_HISTORY:]
    merged["history"] = entries
    counts = dict.fromkeys(REVIEW_OUTCOMES, 0)
    for entry in entries:
        name = entry.get("outcome")
        if name in counts:
            counts[name] += 1
    merged["counts"] = counts
    merged["v"] = METADATA_VERSION
    return merged


def review_accuracy(history: Sequence[str]) -> float | None:
    """Share (0..100) of successful recalls across an outcome history.

    ``None`` when there is no valid recall evidence (never fabricated zero);
    all-``again`` history returns 0.0.
    """
    valid = [outcome for outcome in history if outcome in REVIEW_OUTCOMES]
    if not valid:
        return None
    recalled = sum(1 for outcome in valid if outcome in (OUTCOME_GOOD, OUTCOME_EASY))
    return round(100.0 * recalled / len(valid), 1)


def band_for_strength(strength: float | None) -> str:
    """Map retained strength onto a coarse strong/developing/weak band."""
    if strength is None:
        return "new"
    if strength >= _STRENGTH_ON_TRACK:
        return BAND_STRONG
    if strength >= _STRENGTH_WEAK:
        return BAND_DEVELOPING
    return BAND_WEAK


def status_sort_key(status: str) -> int:
    """Deterministic sort key: overdue < at_risk < on_track < new < completed."""
    return _STATUS_SORT.get(status, 5)


def retention_summary(
    strengths: Sequence[float | None],
    statuses: Sequence[str],
) -> dict[str, Any]:
    """Bucketed, bounded summary over a set of concept signals.

    ``retention_average`` is the mean of the non-null strengths (``None`` when
    no concept has recall evidence yet); the four counts are exact.
    """
    present = [float(strength) for strength in strengths if strength is not None]
    return {
        "retention_average": (round(sum(present) / len(present), 1) if present else None),
        "on_track_count": statuses.count(STATUS_ON_TRACK),
        "at_risk_count": statuses.count(STATUS_AT_RISK),
        "overdue_count": statuses.count(STATUS_OVERDUE),
        "new_count": statuses.count(STATUS_NEW),
    }


# ---------------------------------------------------------------------------
# Retention / recall signal (D1-B)
# ---------------------------------------------------------------------------


def _recall_strength(history: Sequence[str]) -> float | None:
    """Weighted recent-recall strength in 0..100 (None when no evidence)."""
    outcomes = [outcome for outcome in history if outcome in REVIEW_OUTCOMES]
    if not outcomes:
        return None
    recent = outcomes[-_RECENT_WINDOW:]
    weights = _RECENT_WEIGHTS[-len(recent) :]
    weighted = sum(
        _OUTCOME_WEIGHT[outcome] * weight * 100.0
        for outcome, weight in zip(recent, weights, strict=False)
    )
    return round(weighted / sum(weights), 1)


def _classify_status(
    *,
    days_since_review: float | None,
    is_due: bool,
    recent_outcomes: list[str],
    retained_strength: float | None,
) -> str:
    """Deterministic status: overdue > new > recent lapse > strength threshold."""
    if is_due:
        return STATUS_OVERDUE
    if days_since_review is None:
        return STATUS_NEW
    if recent_outcomes and recent_outcomes[-1] == OUTCOME_AGAIN:
        return STATUS_AT_RISK
    if retained_strength is not None and retained_strength >= _STRENGTH_ON_TRACK:
        return STATUS_ON_TRACK
    return STATUS_AT_RISK


def retention_signal(
    *,
    mastery: float | None,
    days_since_review: float | None,
    is_due: bool,
    history: Sequence[str],
) -> dict[str, Any]:
    """Deterministic per-concept retention/recall signal.

    Returns ``{"retained_strength": float | None, "status": str}``.

    The signal is distinct from OBSERVED MASTERY: retained strength is derived
    from self-reported recall outcomes decayed by recency (``mastery`` is only
    a fallback anchor when a legacy review predates recall history), and the
    status is driven by due/lapse facts — never by mastery alone. A concept
    that has never been reviewed reports ``new`` with no fabricated strength.
    Nothing here ever writes the quiz-owned mastery scalar.
    """
    if days_since_review is None:
        return {"retained_strength": None, "status": STATUS_NEW}
    recent = [outcome for outcome in history if outcome in REVIEW_OUTCOMES][-_RECENT_WINDOW:]
    recall = _recall_strength(history)

    time_factor = _clamp01(
        1.0 - (max(0.0, float(days_since_review)) / _DECAY_HORIZON_DAYS)
        if days_since_review is not None
        else 1.0
    )

    if recall is not None:
        base: float | None = recall
    elif mastery is not None:
        base = max(0.0, min(100.0, float(mastery)))
    else:
        base = None

    retained_strength = round(base * time_factor, 1) if base is not None else None
    status = _classify_status(
        days_since_review=days_since_review,
        is_due=is_due,
        recent_outcomes=recent,
        retained_strength=retained_strength,
    )
    return {"retained_strength": retained_strength, "status": status}


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
