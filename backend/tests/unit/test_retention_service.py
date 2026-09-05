"""P14 retention/outcome pure-logic unit tests.

Exercises ``app.services.retention`` in isolation: the outcome vocabulary,
the deterministic outcome->step mapping (again->0 / hard->hold / good->+1 /
easy->+2 capped), the JSONB history merge (bounded, versioned, backward
compatible, tolerant of malformed rows), the recall signal thresholds and the
review-accuracy edge cases. No database, no AI — purely deterministic.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.services import retention
from app.services.review_scheduler import MAX_STEP


def _meta(*entries: str, **extras: dict) -> dict | None:
    """Build a v2 review_metadata from an outcome list plus extra keys."""
    metadata: dict = {"v": 2, "step": 0, "last_pressure": None}
    metadata.update(extras)
    if entries:
        metadata["history"] = [
            {"outcome": outcome, "at": f"2026-09-05T10:00:00+00:00{index}"}
            for index, outcome in enumerate(entries)
        ]
        counts = dict.fromkeys(retention.REVIEW_OUTCOMES, 0)
        for outcome in entries:
            counts[outcome] += 1
        metadata["counts"] = counts
    return metadata


NOW = datetime(2026, 9, 5, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Outcome vocabulary + validation
# ---------------------------------------------------------------------------


def test_controlled_vocabulary() -> None:
    assert set(retention.REVIEW_OUTCOMES) == {"again", "hard", "good", "easy"}
    assert retention.DEFAULT_OUTCOME == "good"


@pytest.mark.parametrize("outcome", ["again", "hard", "good", "easy"])
def test_valid_outcomes_validate(outcome: str) -> None:
    assert retention.validate_outcome(outcome) == outcome


@pytest.mark.parametrize("outcome", ["perfect", "ok", "forgot", "", "GOOD", None])
def test_invalid_outcomes_rejected(outcome: str) -> None:
    with pytest.raises(ValueError, match="invalid review outcome"):
        retention.validate_outcome(outcome)


# ---------------------------------------------------------------------------
# Deterministic adaptive spacing (C2)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("step", "outcome", "expected"),
    [
        (0, "again", 0),
        (2, "again", 0),
        (MAX_STEP, "again", 0),
        (0, "hard", 0),
        (2, "hard", 2),
        (0, "good", 1),
        (1, "good", 2),
        (MAX_STEP, "good", MAX_STEP),  # good cannot exceed the ladder
        (0, "easy", 2),
        (1, "easy", 3),
        (2, "easy", MAX_STEP),
        (MAX_STEP, "easy", MAX_STEP),  # easy capped at the max step
    ],
)
def test_outcome_next_step_mapping(step: int, outcome: str, expected: int) -> None:
    assert retention.outcome_next_step(step, outcome) == expected


@pytest.mark.parametrize("step", [0, 2, 5, 99])
def test_easy_is_bounded_by_max_step(step: int) -> None:
    assert retention.outcome_next_step(step, "easy") <= MAX_STEP


def test_negative_step_clamps_to_zero() -> None:
    assert retention.outcome_next_step(-3, "good") == 1
    assert retention.outcome_next_step(-3, "again") == 0


def test_default_good_equals_legacy_ladder_path() -> None:
    """Backwards compatibility: good must reproduce today's next_interval."""
    from app.services import review_scheduler

    for step in range(MAX_STEP + 1):
        expected_step, expected_days = review_scheduler.next_interval(step)
        assert retention.outcome_next_step(step, "good") == expected_step
        assert retention.outcome_interval_days(step, "good") == expected_days
        assert interval_days_is_valid(retention.outcome_interval_days(step, "good"))


def interval_days_is_valid(days: int) -> bool:
    return isinstance(days, int) and days > 0


@pytest.mark.parametrize("step", [0, MAX_STEP])
@pytest.mark.parametrize("outcome", ["again", "hard", "good", "easy"])
def test_interval_never_invalid_near_edges(step: int, outcome: str) -> None:
    days = retention.outcome_interval_days(step, outcome)
    assert days > 0, "intervals must never be zero/negative"
    assert days <= 14, "intervals must stay on the documented ladder"


@pytest.mark.parametrize(
    ("step", "before", "after"),
    [
        (2, "good", "easy"),
        (0, "hard", "good"),
    ],
)
def test_spacing_reactions_are_monotonic(step: int, before: str, after: str) -> None:
    """A better outcome on the same step never yields a shorter interval."""
    assert retention.outcome_interval_days(step, after) >= retention.outcome_interval_days(
        step, before
    )


def test_failure_shortens_relative_to_default() -> None:
    failing = retention.outcome_interval_days(3, "again")
    default = retention.outcome_interval_days(3, "good")
    assert failing < default, "again must meaningfully shorten the interval"


# ---------------------------------------------------------------------------
# review_metadata JSONB merge (D1-E)
# ---------------------------------------------------------------------------


def test_apply_preserves_existing_keys() -> None:
    merged = retention.apply_outcome_to_metadata(
        {"step": 1, "last_pressure": 0.4, "skipped_at": "2026-01-01T00:00:00+00:00"},
        "good",
        at=NOW,
    )
    assert merged["step"] == 1
    assert merged["last_pressure"] == 0.4
    assert merged["skipped_at"] == "2026-01-01T00:00:00+00:00"
    assert merged["v"] == retention.METADATA_VERSION
    assert merged["history"][-1]["outcome"] == "good"


def test_apply_appends_history_and_counts() -> None:
    metadata = _meta("hard", "good")
    merged = retention.apply_outcome_to_metadata(metadata, "again", at=NOW)
    assert [entry["outcome"] for entry in merged["history"]] == ["hard", "good", "again"]
    assert merged["counts"] == {"again": 1, "hard": 1, "good": 1, "easy": 0}
    assert merged["history"][-1]["at"] == NOW.isoformat()


def test_apply_caps_history_at_max() -> None:
    metadata = _meta(*(["good"] * 25))
    merged = retention.apply_outcome_to_metadata(metadata, "hard", at=NOW)
    assert len(merged["history"]) == retention.MAX_HISTORY
    assert merged["history"][-1]["outcome"] == "hard"
    assert merged["counts"]["good"] == 19
    assert merged["counts"]["hard"] == 1


def test_apply_on_null_metadata_starts_fresh_shape() -> None:
    merged = retention.apply_outcome_to_metadata(None, "easy", at=NOW)
    assert merged["v"] == 2
    assert [entry["outcome"] for entry in merged["history"]] == ["easy"]
    assert merged["counts"]["easy"] == 1


def test_apply_tolerates_malformed_metadata() -> None:
    """Non-dict or junk-shaped metadata must not raise or corrupt state."""
    for malformed in (42, ["junk"], {"history": {"not": "a list"}}, {"history": [1, None, "x"]}):
        merged = retention.apply_outcome_to_metadata(malformed, "again", at=NOW)
        assert merged["v"] == 2
        assert [entry["outcome"] for entry in merged["history"]] == ["again"]
        assert merged["counts"]["again"] == 1


def test_history_outcomes_tolerant_reads() -> None:
    assert retention.history_outcomes(_meta("good", "again")) == ["good", "again"]
    assert retention.history_outcomes(None) == []
    assert retention.history_outcomes({"history": [{"outcome": "easy"}, 5]}) == ["easy"]
    assert retention.last_outcome(_meta("good", "again")) == "again"
    assert retention.last_outcome(None) is None


def test_repeated_completion_is_bounded_and_deterministic() -> None:
    metadata = None
    outcomes = ["again", "hard", "good", "easy"] * 6  # 24 completions
    for outcome in outcomes:
        metadata = retention.apply_outcome_to_metadata(metadata, outcome, at=NOW)
    assert len(retention.history_outcomes(metadata)) == retention.MAX_HISTORY
    assert retention.history_outcomes(metadata)[-4:] == list(outcomes[-4:])
    assert sum(metadata["counts"].values()) == retention.MAX_HISTORY


# ---------------------------------------------------------------------------
# review_accuracy
# ---------------------------------------------------------------------------


def test_accuracy_empty_is_none() -> None:
    assert retention.review_accuracy([]) is None
    assert retention.review_accuracy([5, None, {"x": 1}]) is None


def test_accuracy_all_again_is_zero() -> None:
    assert retention.review_accuracy(["again", "again", "again"]) == 0.0


def test_accuracy_all_success_is_hundred() -> None:
    assert retention.review_accuracy(["good", "easy", "good"]) == 100.0


def test_accuracy_mixed_history() -> None:
    # recall = good/easy only, so 2 of 5 -> 40
    assert retention.review_accuracy(["again", "hard", "good", "easy", "hard"]) == 40.0


def test_accuracy_ignores_unknown_entries() -> None:
    # valid history is ["good", "again"], 1 of 2 recalled
    assert retention.review_accuracy(["junk", "good", "again"]) == 50.0
    assert retention.review_accuracy(["junk"]) is None


# ---------------------------------------------------------------------------
# Recall signal behaviour across recency and outcome mixes (C3)
# ---------------------------------------------------------------------------


def test_signal_never_reviewed_is_new_with_no_strength() -> None:
    sig = retention.retention_signal(mastery=30.0, days_since_review=None, is_due=False, history=[])
    assert sig == {"retained_strength": None, "status": "new"}


def test_signal_due_states_overdue() -> None:
    sig = retention.retention_signal(
        mastery=30.0, days_since_review=5.0, is_due=True, history=["good"]
    )
    assert sig["status"] == "overdue"
    assert sig["retained_strength"] is not None


def test_signal_recent_lapse_is_at_risk() -> None:
    sig = retention.retention_signal(
        mastery=60.0, days_since_review=0.0, is_due=False, history=["again"]
    )
    assert sig["status"] == "at_risk"
    assert sig["retained_strength"] == 0.0


def test_signal_all_success_is_on_track() -> None:
    sig = retention.retention_signal(
        mastery=60.0, days_since_review=0.0, is_due=False, history=["good", "good", "easy"]
    )
    assert sig["status"] == "on_track"
    assert sig["retained_strength"] >= 80.0


def test_signal_mixed_history_developing() -> None:
    sig = retention.retention_signal(
        mastery=50.0, days_since_review=0.0, is_due=False, history=["again", "hard", "good"]
    )
    assert sig["status"] in ("at_risk", "on_track")


def test_signal_time_decay_lowers_strength() -> None:
    fresh = retention.retention_signal(
        mastery=50.0, days_since_review=1.0, is_due=False, history=["good", "good"]
    )
    stale = retention.retention_signal(
        mastery=50.0, days_since_review=25.0, is_due=False, history=["good", "good"]
    )
    assert stale["retained_strength"] < fresh["retained_strength"]


def test_signal_sparse_history_needs_no_crash() -> None:
    sig = retention.retention_signal(
        mastery=None, days_since_review=2.0, is_due=False, history=["hard"]
    )
    assert sig["retained_strength"] is not None
    assert sig["status"] in ("at_risk", "on_track")


def test_signal_no_history_falls_back_to_mastery_anchor_only() -> None:
    sig = retention.retention_signal(mastery=90.0, days_since_review=0.0, is_due=False, history=[])
    assert sig["retained_strength"] == 90.0
    assert sig["status"] == "on_track"


def test_signal_old_history_bounded_strength() -> None:
    sig = retention.retention_signal(
        mastery=50.0, days_since_review=1000.0, is_due=True, history=["easy", "good"]
    )
    assert sig["status"] == "overdue"
    assert sig["retained_strength"] == 0.0


def test_signal_is_deterministic() -> None:
    kwargs = {
        "mastery": 55.0,
        "days_since_review": 3.0,
        "is_due": False,
        "history": ["hard", "good", "again"],
    }
    first = retention.retention_signal(**kwargs)
    second = retention.retention_signal(**kwargs)
    assert first == second
    assert 0.0 <= (first["retained_strength"] or 0.0) <= 100.0


def test_signal_repeated_failures_keeps_strength_low() -> None:
    sig = retention.retention_signal(
        mastery=90.0, days_since_review=0.0, is_due=False, history=["again", "again", "again"]
    )
    assert sig["retained_strength"] == 0.0
    assert sig["status"] == "at_risk"


# ---------------------------------------------------------------------------
# Bucketing helpers
# ---------------------------------------------------------------------------


def test_band_for_strength_thresholds() -> None:
    assert retention.band_for_strength(None) == "new"
    assert retention.band_for_strength(85.0) == "strong"
    assert retention.band_for_strength(60.0) == "developing"
    assert retention.band_for_strength(30.0) == "weak"


def test_summary_buckets_and_average() -> None:
    summary = retention.retention_summary(
        strengths=[90.0, 40.0, None, 70.0],
        statuses=["on_track", "at_risk", "new", "overdue"],
    )
    assert summary["retention_average"] == 66.7
    assert summary["on_track_count"] == 1
    assert summary["at_risk_count"] == 1
    assert summary["overdue_count"] == 1
    assert summary["new_count"] == 1


def test_summary_empty_is_null_average() -> None:
    summary = retention.retention_summary([], ["new", "new"])
    assert summary["retention_average"] is None
    assert summary["new_count"] == 2
    assert summary["retention_average"] is None


def test_status_sort_key_ordering() -> None:
    ordered = sorted(
        ["new", "on_track", "overdue", "at_risk", "completed"],
        key=retention.status_sort_key,
    )
    assert ordered == ["overdue", "at_risk", "on_track", "new", "completed"]
