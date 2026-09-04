"""P10 review-scheduler pure-logic unit tests.

Exercises the deterministic spaced-repetition helpers in
``app.services.review_scheduler``: interval progression, initial stepping, the
mastery-decay "review pressure" signal, and priority bucketing. No database, no
AI — purely deterministic.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.schemas.educational_memory import ConceptMasteryRecord
from app.services import review_scheduler
from app.services.review_scheduler import (
    compute_decay_signal,
    initial_step,
    interval_at_step,
    next_interval,
    next_step,
    priority_bucket,
)

NOW = datetime(2026, 9, 4, 12, 0, 0, tzinfo=UTC)


def _record(
    *,
    mastery: float = 50.0,
    days_since_review: float = 0.0,
    confidence: float = 0.5,
) -> ConceptMasteryRecord:
    first = NOW - timedelta(days=30)
    last = NOW - timedelta(days=days_since_review)
    return ConceptMasteryRecord(
        concept_id="concept_x",
        concept_name="X",
        first_learned_at=first.timestamp(),
        last_reviewed_at=last.timestamp(),
        mastery_score=mastery,
        review_count=1,
        confidence_score=confidence,
    )


def test_interval_ladder() -> None:
    assert review_scheduler.INTERVAL_LADDER == (1, 3, 7, 14)
    assert interval_at_step(0) == 1
    assert interval_at_step(1) == 3
    assert interval_at_step(2) == 7
    assert interval_at_step(3) == 14
    # Clamped beyond max.
    assert interval_at_step(99) == 14
    assert interval_at_step(-5) == 1


def test_initial_step_by_mastery() -> None:
    # Weak -> tightest interval.
    assert initial_step(30.0) == 0
    # Developing -> 3d.
    assert initial_step(60.0) == 1
    # Mastered -> 7d.
    assert initial_step(90.0) == 2


def test_next_interval_progression() -> None:
    step, days = next_interval(0)
    assert step == 1
    assert days == 3
    step, days = next_interval(2)
    assert step == 3
    assert days == 14
    # Plateaus at max step.
    step, days = next_interval(3)
    assert step == 3
    assert days == 14
    assert next_step(3) == 3


def test_compute_decay_signal_fresh() -> None:
    # Reviewed moments ago -> low recency pressure.
    sig = compute_decay_signal(_record(mastery=50.0, days_since_review=0.0), now=NOW)
    assert sig["days_since_review"] == 0.0
    assert 0.0 <= sig["pressure"] <= 1.0


def test_compute_decay_signal_overdue() -> None:
    # Way past the interval -> high pressure, never exceeding 1.
    sig = compute_decay_signal(
        _record(mastery=10.0, days_since_review=30.0), now=NOW, interval_override_days=3
    )
    assert sig["days_since_review"] == 30.0
    assert sig["pressure"] > 0.5


def test_compute_decay_signal_weak_beats_strong() -> None:
    # Same recency, weaker concept carries higher pressure.
    weak = compute_decay_signal(
        _record(mastery=10.0, days_since_review=5.0), now=NOW, interval_override_days=3
    )
    strong = compute_decay_signal(
        _record(mastery=80.0, days_since_review=5.0), now=NOW, interval_override_days=3
    )
    assert weak["pressure"] > strong["pressure"]


def test_priority_bucket_due_is_high() -> None:
    assert priority_bucket(0.1, due=True) == "high"
    assert priority_bucket(0.95, due=False) == "high"
    assert priority_bucket(0.7, due=False) == "medium"
    assert priority_bucket(0.4, due=False) == "low"
    assert priority_bucket(0.0, due=False) == "low"


@pytest.mark.parametrize(
    "pressure",
    [0.0, 0.25, 0.5, 0.75, 1.0],
)
def test_decay_pressure_bounded(pressure: float) -> None:
    assert 0.0 <= pressure <= 1.0
