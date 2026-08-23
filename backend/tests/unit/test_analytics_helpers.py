from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.utils.analytics_helpers import (
    calculate_engagement_score,
    calculate_study_streak,
    fill_time_series_buckets,
    get_period_date_range,
    map_count_to_heatmap_intensity,
)


def test_get_period_date_range() -> None:
    start_7d, end_7d = get_period_date_range("7d")
    assert (end_7d - start_7d).days == 7

    start_30d, end_30d = get_period_date_range("30d")
    assert (end_30d - start_30d).days == 30

    start_1y, end_1y = get_period_date_range("1y")
    assert (end_1y - start_1y).days == 365


def test_calculate_study_streak() -> None:
    now = datetime.now(UTC)
    active_dates = [
        now - timedelta(days=2),
        now - timedelta(days=1),
        now,
    ]
    streak = calculate_study_streak(active_dates)
    assert streak >= 1

    empty_streak = calculate_study_streak([])
    assert empty_streak == 0


def test_calculate_engagement_score() -> None:
    score = calculate_engagement_score(
        lessons_completed=5,
        avg_quiz_score=85.0,
        tutor_messages_count=10,
        active_days_count=20,
    )
    assert 0 <= score <= 100
    assert score > 50


def test_map_count_to_heatmap_intensity() -> None:
    assert map_count_to_heatmap_intensity(0) == 0
    assert map_count_to_heatmap_intensity(1) == 1
    assert map_count_to_heatmap_intensity(3) == 2
    assert map_count_to_heatmap_intensity(6) == 3


def test_fill_time_series_buckets() -> None:
    start_date = datetime.now(UTC) - timedelta(days=7)
    end_date = datetime.now(UTC)
    buckets = fill_time_series_buckets(start_date, end_date, {})
    assert len(buckets) >= 7
    assert all("value" in b and "date" in b for b in buckets)
