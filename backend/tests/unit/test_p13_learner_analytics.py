"""P13 pure learner-analytics logic tests.

Exercises ``app.services.learner_analytics`` in isolation: banding, trend
classification (up/flat/down), the recent-vs-earlier ``trend_delta``, the
trajectory labeler, window clamping, effort efficiency and determinism. These
functions are deliberately dependency-free so the module can be verified
without a database.
"""

from __future__ import annotations

import pytest

from app.services.learner_analytics import (
    DEFAULT_TREND_WINDOW,
    MASTERED_THRESHOLD,
    MAX_TREND_WINDOW,
    WEAK_THRESHOLD,
    band,
    band_rank,
    clamp_window,
    classify_trend,
    gain_per_attempt,
    mean,
    trajectory_direction,
    trend_delta,
)

# ── banding ──────────────────────────────────────────────────────────────────

def test_band_weak_below_threshold() -> None:
    assert band(0.0) == "weak"
    assert band(30.0) == "weak"
    assert band(49.99) == "weak"


def test_band_developing_between_thresholds() -> None:
    assert band(50.0) == "developing"
    assert band(62.5) == "developing"
    assert band(84.99) == "developing"


def test_band_mastered_at_threshold() -> None:
    assert band(85.0) == "mastered"
    assert band(100.0) == "mastered"


def test_band_thresholds_match_memory_service() -> None:
    # Must stay aligned with educational_memory_service (weak<50 / 50-85 / >=85).
    assert WEAK_THRESHOLD == 50.0
    assert MASTERED_THRESHOLD == 85.0


# ── classify_trend (up/flat/down) ────────────────────────────────────────────

def test_classify_trend_known_mappings() -> None:
    assert classify_trend("improving") == "up"
    assert classify_trend("regressing") == "down"
    assert classify_trend("stable") == "flat"


def test_classify_trend_handles_unknown_and_none() -> None:
    assert classify_trend(None) == "flat"
    assert classify_trend("mystery") == "flat"


# ── trend_delta ──────────────────────────────────────────────────────────────

def test_trend_delta_improving_series_is_positive() -> None:
    series = [40.0, 55.0, 70.0, 85.0]
    assert trend_delta(series) == pytest.approx(30.0)


def test_trend_delta_declining_series_is_negative() -> None:
    series = [85.0, 70.0, 55.0, 40.0]
    assert trend_delta(series) == pytest.approx(-30.0)


def test_trend_delta_flat_series_is_zero() -> None:
    assert trend_delta([60.0, 60.0, 60.0]) == pytest.approx(0.0)


def test_trend_delta_insufficient_data_returns_none() -> None:
    assert trend_delta([]) is None
    assert trend_delta([72.0]) is None


def test_trend_delta_later_half_gets_remainder() -> None:
    # 3 points -> later half is [p1, p2], earlier is [p0].
    series = [40.0, 60.0, 62.0]
    assert trend_delta(series) == pytest.approx(21.0)  # mean([60,62]) - 40


def test_trend_delta_deterministic_same_input_same_output() -> None:
    series = [30.0, 45.0, 52.0, 61.0, 70.0]
    assert trend_delta(series) == trend_delta(list(series)) == trend_delta(tuple(series))


# ── trajectory_direction ─────────────────────────────────────────────────────

def test_trajectory_direction_classifications() -> None:
    assert trajectory_direction(5.0) == "improving"
    assert trajectory_direction(-5.0) == "declining"
    assert trajectory_direction(0.4) == "stable"
    assert trajectory_direction(None) == "insufficient_data"


def test_trajectory_direction_epsilon_boundary() -> None:
    # +/-1.0% is the noise floor; anything within it is "stable".
    assert trajectory_direction(0.999) == "stable"
    assert trajectory_direction(1.001) == "improving"
    assert trajectory_direction(-1.001) == "declining"


# ── clamp_window ─────────────────────────────────────────────────────────────

def test_clamp_window_defaults_and_bounds() -> None:
    assert clamp_window(None) == DEFAULT_TREND_WINDOW
    assert clamp_window(0) == DEFAULT_TREND_WINDOW
    assert clamp_window(-5) == DEFAULT_TREND_WINDOW
    assert clamp_window(200) == MAX_TREND_WINDOW
    assert clamp_window(30) == 30
    assert clamp_window(7) == 7


def test_clamp_window_constants_locked() -> None:
    assert DEFAULT_TREND_WINDOW == MAX_TREND_WINDOW == 30


# ── gain_per_attempt / effort ────────────────────────────────────────────────

def test_gain_per_attempt_positive() -> None:
    assert gain_per_attempt(18.0, 3) == pytest.approx(6.0)


def test_gain_per_attempt_negative_delta_still_reported() -> None:
    assert gain_per_attempt(-9.0, 3) == pytest.approx(-3.0)


def test_gain_per_attempt_missing_data_is_none() -> None:
    assert gain_per_attempt(None, 3) is None
    assert gain_per_attempt(18.0, 0) is None
    assert gain_per_attempt(None, 0) is None


def test_effort_empty_state_one_attempt_is_not_measurable() -> None:
    # A single completed attempt cannot back a mastery movement.
    assert trend_delta([64.0]) is None
    assert gain_per_attempt(trend_delta([64.0]), 1) is None


# ── ordering helpers ─────────────────────────────────────────────────────────

def test_band_rank_weakest_first() -> None:
    assert band_rank("weak") < band_rank("developing") < band_rank("mastered")
    assert band_rank("unknown") == 1


def test_mean_helpers() -> None:
    assert mean([10.0, 20.0, 30.0]) == pytest.approx(20.0)
    assert mean([]) == 0.0
