from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone


def utc_now() -> datetime:
    return datetime.now(UTC)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def seconds_from_now(seconds: int) -> datetime:
    return utc_now() + timedelta(seconds=seconds)


def minutes_from_now(minutes: int) -> datetime:
    return utc_now() + timedelta(minutes=minutes)


def hours_from_now(hours: int) -> datetime:
    return utc_now() + timedelta(hours=hours)


def days_from_now(days: int) -> datetime:
    return utc_now() + timedelta(days=days)


def is_expired(dt: datetime, tz: timezone | None = None) -> bool:
    return to_utc(dt) < utc_now() if tz is None else dt < datetime.now(tz)


def format_timestamp(dt: datetime, fmt: str = "%Y-%m-%dT%H:%M:%SZ") -> str:
    return to_utc(dt).strftime(fmt)


def human_readable_duration(seconds: float) -> str:
    days, remainder = divmod(int(seconds), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs or not parts:
        parts.append(f"{secs}s")
    return " ".join(parts)
