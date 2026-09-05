"""Pure, deterministic learner-analytics helpers (P13).

Mirrors the ``adaptive_assessment.py`` / ``recommendation_engine`` style:
small, side-effect-free functions that are unit-testable in isolation and
carry NO database dependency. The service layer
(``learner_analytics_service.py``) feeds these helpers persisted, learner-scoped
rows; they turn them into bands/trends/classifications that drive the
``/me/analytics/*`` endpoints and the dashboard panels.

All thresholds are lifted verbatim from ``educational_memory_service`` /
``recommendation_engine`` (weak < 50, developing 50-84.99, mastered >= 85);
they are echoed here ONLY as the shared contract surface for the pure module
and must never diverge from the authoritative definitions.
"""

from __future__ import annotations

from collections.abc import Sequence

# Mastery bands — MUST stay aligned with educational_memory_service.
MASTERED_THRESHOLD = 85.0
WEAK_THRESHOLD = 50.0

# Trend window bounds for the /me/analytics/trend endpoint (clamped server-side).
DEFAULT_TREND_WINDOW = 30
MAX_TREND_WINDOW = 30

# Effort/trend classification noise threshold (percentage points). A movement
# within +/- this range is reported as "stable" so single-point wobble never
# produces a false improving/declining claim.
_NOISE_EPSILON = 1.0

_BAND_RANK = {"weak": 0, "developing": 1, "mastered": 2}
_TREND_TO_ARROW = {"improving": "up", "stable": "flat", "regressing": "down"}


def band(mastery: float) -> str:
    """Classify a mastery score into ``weak`` / ``developing`` / ``mastered``.

    Reuses the authoritative 50/85 thresholds from the memory service.
    """
    if mastery >= MASTERED_THRESHOLD:
        return "mastered"
    if mastery >= WEAK_THRESHOLD:
        return "developing"
    return "weak"


def classify_trend(memory_trend: str | None) -> str:
    """Map a memory record's categorical trend onto an up/flat/down arrow.

    ``improving`` -> ``up``, ``regressing`` -> ``down``, anything else
    (``stable``, unknown, ``None``) -> ``flat``. Deterministic and total.
    """
    if memory_trend:
        arrow = _TREND_TO_ARROW.get(memory_trend)
        if arrow is not None:
            return arrow
    return "flat"


def mean(values: Sequence[float]) -> float:
    """Arithmetic mean of a non-empty numeric sequence."""
    if not values:
        return 0.0
    return sum(values) / len(values)


def trend_delta(series: Sequence[float]) -> float | None:
    """Compare the recent half of a series to its earlier half.

    ``series`` must be provided oldest->newest (chronological). Returns the
    difference ``mean(later half) - mean(earlier half)``, or ``None`` when the
    series has fewer than two points (insufficient data). The midpoint is the
    integer division ``len // 2``; the later half carries the remainder so a
    3-point series compares ``[p1, p2]`` against ``[p0]``.
    """
    if len(series) < 2:
        return None
    midpoint = len(series) // 2
    earlier = series[:midpoint]
    later = series[midpoint:]
    return mean(later) - mean(earlier)


def trajectory_direction(delta: float | None) -> str:
    """Label a trend delta as ``improving``/``declining``/``stable``.

    ``None`` (insufficient data) maps to ``insufficient_data``.
    """
    if delta is None:
        return "insufficient_data"
    if delta > _NOISE_EPSILON:
        return "improving"
    if delta < -_NOISE_EPSILON:
        return "declining"
    return "stable"


def clamp_window(
    window: int | None,
    *,
    default: int = DEFAULT_TREND_WINDOW,
    maximum: int = MAX_TREND_WINDOW,
) -> int:
    """Bounds a requested aggregation window to ``[1, maximum]``.

    ``None``/non-positive values fall back to ``default``. Server-side clamping
    keeps every analytics query learner-scoped and bounded.
    """
    if window is None or window <= 0:
        return default
    return min(window, maximum)


def gain_per_attempt(mastery_delta: float | None, attempts: int) -> float | None:
    """Mastery gained per completed attempt (``efficiency``).

    Only measurable when a numeric delta exists and at least one completed
    attempt backs it; otherwise ``None`` (never a fabricated zero).
    """
    if mastery_delta is None or attempts <= 0:
        return None
    return mastery_delta / attempts


def band_rank(band_name: str) -> int:
    """Deterministic sort key: weakest concepts sort first."""
    return _BAND_RANK.get(band_name, 1)
