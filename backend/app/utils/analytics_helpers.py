from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any


def get_period_date_range(period: str = "30d") -> tuple[datetime, datetime]:
    """Returns (start_date, end_date) UTC datetimes for a given period string (e.g. '7d', '30d', '90d', '1y')."""
    end_date = datetime.now(UTC)
    p = period.lower()

    if p == "7d":
        days = 7
    elif p == "90d":
        days = 90
    elif p == "1y" or p == "365d":
        days = 365
    else:
        days = 30  # Default 30 days

    start_date = end_date - timedelta(days=days)
    return start_date, end_date


def calculate_study_streak(active_dates: list[datetime]) -> int:
    """Calculates consecutive active daily streak counting backwards from today."""
    if not active_dates:
        return 0

    unique_days = sorted({d.date() for d in active_dates}, reverse=True)
    today = datetime.now(UTC).date()
    yesterday = today - timedelta(days=1)

    if unique_days[0] not in (today, yesterday):
        return 0

    streak = 1
    current = unique_days[0]

    for next_day in unique_days[1:]:
        if current - next_day == timedelta(days=1):
            streak += 1
            current = next_day
        elif current == next_day:
            continue
        else:
            break

    return streak


def calculate_engagement_score(
    lessons_completed: int,
    avg_quiz_score: float,
    tutor_messages_count: int,
    active_days_count: int,
) -> float:
    """Computes a composite engagement score out of 100 based on learner activity."""
    score = 0.0

    # Lesson completion weight (max 30 points)
    score += min(30.0, lessons_completed * 5.0)

    # Quiz score weight (max 40 points)
    score += (avg_quiz_score / 100.0) * 40.0

    # AI Tutor interaction weight (max 15 points)
    score += min(15.0, tutor_messages_count * 1.5)

    # Active days consistency weight (max 15 points)
    score += min(15.0, active_days_count * 2.0)

    return round(min(100.0, max(0.0, score)), 1)


def fill_time_series_buckets(
    start_date: datetime,
    end_date: datetime,
    raw_data: dict[str, float],
    default_value: float = 0.0,
) -> list[dict[str, Any]]:
    """Fills missing daily buckets between start_date and end_date for smooth chart rendering."""
    result: list[dict[str, Any]] = []
    current = start_date.date()
    end = end_date.date()

    while current <= end:
        date_str = current.strftime("%Y-%m-%d")
        val = raw_data.get(date_str, default_value)
        result.append({
            "date": date_str,
            "label": current.strftime("%b %d"),
            "value": round(val, 2),
        })
        current += timedelta(days=1)

    return result


def map_count_to_heatmap_intensity(count: int) -> int:
    """Maps event count to GitHub-style heatmap contribution intensity (0 to 4)."""
    if count <= 0:
        return 0
    elif count <= 2:
        return 1
    elif count <= 5:
        return 2
    elif count <= 10:
        return 3
    else:
        return 4
