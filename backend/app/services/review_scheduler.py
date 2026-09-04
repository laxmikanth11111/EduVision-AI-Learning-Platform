"""Deterministic spaced-repetition scheduling (P10).

Pure, deterministic helpers that turn mastery + time into review scheduling
decisions. No AI, no ML, no RNG — the same inputs always yield the same
output. These functions are intentionally side-effect free so the scheduler is
trivial to unit test and reason about.

Interval progression (spaced repetition) is a fixed ladder::

    step 0 -> 1d, step 1 -> 3d, step 2 -> 7d, step 3 -> 14d, then plateaus at 14d.

``compute_decay_signal`` provides a deterministic "review pressure" for a
concept — used only for ranking/annotating the review queue (it never rewrites
persisted mastery, per the P10 contract).
"""

from __future__ import annotations

from datetime import datetime

from app.schemas.educational_memory import ConceptMasteryRecord

# Mastery thresholds (aligned with educational_memory_service / learner_progress
# service — do NOT redefine).
THRESHOLD_WEAK = 50.0
THRESHOLD_MASTERED = 85.0

# Spaced-repetition interval ladder (in days), indexed by review step.
INTERVAL_LADDER: tuple[int, ...] = (1, 3, 7, 14)
MAX_STEP = len(INTERVAL_LADDER) - 1

# Review pressure bounds.
PRESSURE_LOW = 0.3
PRESSURE_MEDIUM = 0.6
PRESSURE_HIGH = 0.9


def initial_step(mastery: float) -> int:
    """A weak concept starts at the tightest interval; mastered at a looser one."""
    if mastery < THRESHOLD_WEAK:
        return 0
    if mastery < THRESHOLD_MASTERED:
        return 1
    return 2


def interval_at_step(step: int) -> int:
    """Return the interval in days for a given review step (clamped)."""
    if step < 0:
        step = 0
    if step >= len(INTERVAL_LADDER):
        step = MAX_STEP
    return INTERVAL_LADDER[step]


def next_step(step: int) -> int:
    """Advance one step up the ladder and return the clamped step index."""
    return min(step + 1, MAX_STEP)


def next_interval(step: int) -> tuple[int, int]:
    """Return ``(next_step, next_interval_days)`` after completing a review.

    A concept that is still weak does not advance up the ladder — it stays at
    the tightest interval so it is revisited sooner (remediation loop).
    """
    advanced = next_step(step)
    return advanced, interval_at_step(advanced)


def lerp_scale(
    mastery: float,
    *,
    out_min: float = 0.0,
    out_max: float = 1.0,
) -> float:
    """Map mastery (0..100) onto [out_min, out_max] deterministically."""
    clamped = max(0.0, min(100.0, float(mastery)))
    return out_min + (out_max - out_min) * (clamped / 100.0)


def compute_decay_signal(
    record: ConceptMasteryRecord,
    *,
    now: datetime,
    interval_override_days: int | None = None,
) -> dict[str, float]:
    """Compute a deterministic review-pressure signal for a concept.

    The signal blends how long it has been since the concept was last reviewed
    (recency decay) with how weak the concept currently is. It is bounded to
    ``[0, 1]`` and used to rank/annotate the review queue — never to rewrite the
    persisted mastery score.

    Returns ``{"days_since_review", "pressure"}``.
    """
    interval = interval_override_days if interval_override_days is not None else 1
    last_anchor = record.last_reviewed_at or record.first_learned_at or now.timestamp()
    last_dt = datetime.fromtimestamp(last_anchor, tz=now.tzinfo)
    days_since = max(0.0, (now - last_dt).total_seconds() / 86400.0)

    # Recency component: grows toward 1 as the concept stays unreviewed.
    horizon_days = max(1, interval)
    recency = min(1.0, days_since / float(horizon_days))

    # Mastery component: weaker concepts carry higher intrinsic pressure.
    mastery_component = 1.0 - lerp_scale(record.mastery_score)

    # Odd/stable weighting: recency dominates; mastery pulls the remainder.
    pressure = clamp01(0.5 * recency + 0.5 * mastery_component + 0.1 * recency * mastery_component)

    return {
        "days_since_review": round(days_since, 1),
        "pressure": round(pressure, 3),
    }


def priority_bucket(pressure: float, *, due: bool) -> str:
    """Map a decay pressure onto a coarse priority label for the review queue."""
    if due:
        return "high"
    if pressure >= PRESSURE_HIGH:
        return "high"
    if pressure >= PRESSURE_MEDIUM:
        return "medium"
    if pressure >= PRESSURE_LOW:
        return "low"
    return "low"


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
