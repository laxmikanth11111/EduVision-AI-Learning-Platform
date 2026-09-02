"""WS4: bounded in-memory cache with TTL, eviction callback, and dict-like ops.

Tests the BoundedCache utility for size enforcement, TTL expiration, eviction
callbacks, delete/pop/clear, touch, and iteration helpers.
"""

from __future__ import annotations

import time
from typing import Any

from app.utils.bounded_cache import BoundedCache

# ── Original LRU / size tests (preserved) ──────────────────────────────


def test_bounded_cache_evicts_lru() -> None:
    cache: BoundedCache[str, int] = BoundedCache(max_size=3)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)
    assert len(cache) == 3
    # Touch "a" so it is most-recently-used; "b" becomes LRU.
    assert cache.get("a") == 1
    cache.set("d", 4)
    assert len(cache) == 3
    assert cache.get("d") == 4
    assert cache.get("a") == 1
    assert cache.get("b") is None
    assert cache.get("c") == 3


def test_bounded_cache_never_exceeds_max() -> None:
    cache: BoundedCache[str, int] = BoundedCache(max_size=2)
    for i in range(100):
        cache.set(f"k{i}", i)
    assert len(cache) == 2
    assert cache.get("k98") == 98
    assert cache.get("k99") == 99


def test_bounded_cache_min_size_is_one() -> None:
    cache: BoundedCache[str, int] = BoundedCache(max_size=0)
    cache.set("a", 1)
    assert len(cache) == 1
    assert cache.get("a") == 1


def test_bounded_cache_contains_and_get_default() -> None:
    cache: BoundedCache[str, int] = BoundedCache(max_size=4)
    cache.set("x", 10)
    assert "x" in cache
    assert "y" not in cache
    assert cache.get("missing", 42) == 42


# ── WS4: delete / pop / clear ──────────────────────────────────────────


def test_delete_existing_key() -> None:
    cache: BoundedCache[str, int] = BoundedCache(max_size=4)
    cache.set("a", 1)
    assert cache.delete("a") is True
    assert "a" not in cache
    assert len(cache) == 0


def test_delete_missing_key() -> None:
    cache: BoundedCache[str, int] = BoundedCache(max_size=4)
    assert cache.delete("nope") is False
    assert len(cache) == 0


def test_pop_existing_key() -> None:
    cache: BoundedCache[str, int] = BoundedCache(max_size=4)
    cache.set("a", 1)
    assert cache.pop("a") == 1
    assert "a" not in cache
    assert len(cache) == 0


def test_pop_missing_key_returns_default() -> None:
    cache: BoundedCache[str, int] = BoundedCache(max_size=4)
    assert cache.pop("nope", 99) == 99
    assert len(cache) == 0


def test_clear_removes_all_entries() -> None:
    cache: BoundedCache[str, int] = BoundedCache(max_size=8)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.clear()
    assert len(cache) == 0
    assert cache.get("a") is None


# ── WS4: TTL expiration ───────────────────────────────────────────────


def test_ttl_expiration_on_get() -> None:
    cache: BoundedCache[str, int] = BoundedCache(max_size=8, ttl=0.05)
    cache.set("a", 1)
    assert cache.get("a") == 1
    time.sleep(0.1)
    assert cache.get("a") is None
    assert "a" not in cache
    assert len(cache) == 0


def test_ttl_not_expired_within_window() -> None:
    cache: BoundedCache[str, int] = BoundedCache(max_size=8, ttl=5.0)
    cache.set("a", 1)
    assert cache.get("a") == 1
    assert "a" in cache
    assert len(cache) == 1


def test_ttl_refreshed_on_get() -> None:
    cache: BoundedCache[str, int] = BoundedCache(max_size=8, ttl=0.1)
    cache.set("a", 1)
    time.sleep(0.06)
    # Access refreshes TTL
    assert cache.get("a") == 1
    time.sleep(0.06)
    # Still alive because TTL was refreshed
    assert cache.get("a") == 1


def test_ttl_expiration_on_contains() -> None:
    cache: BoundedCache[str, int] = BoundedCache(max_size=8, ttl=0.05)
    cache.set("a", 1)
    assert "a" in cache
    time.sleep(0.1)
    assert "a" not in cache


def test_no_ttl_never_expires() -> None:
    cache: BoundedCache[str, int] = BoundedCache(max_size=8, ttl=None)
    cache.set("a", 1)
    assert cache.get("a") == 1
    assert "a" in cache


# ── WS4: eviction callback ────────────────────────────────────────────


def test_on_evict_fires_on_size_eviction() -> None:
    evicted: list[tuple[str, int]] = []

    def on_evict(key: str, value: int) -> None:
        evicted.append((key, value))

    cache: BoundedCache[str, int] = BoundedCache(max_size=2, on_evict=on_evict)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)  # evicts "a"
    assert evicted == [("a", 1)]


def test_on_evict_fires_on_delete() -> None:
    evicted: list[tuple[str, int]] = []

    def on_evict(key: str, value: int) -> None:
        evicted.append((key, value))

    cache: BoundedCache[str, int] = BoundedCache(max_size=8, on_evict=on_evict)
    cache.set("a", 1)
    cache.delete("a")
    assert evicted == [("a", 1)]


def test_on_evict_fires_on_pop() -> None:
    evicted: list[tuple[str, int]] = []

    def on_evict(key: str, value: int) -> None:
        evicted.append((key, value))

    cache: BoundedCache[str, int] = BoundedCache(max_size=8, on_evict=on_evict)
    cache.set("a", 1)
    cache.pop("a")
    assert evicted == [("a", 1)]


def test_on_evict_fires_on_clear() -> None:
    evicted: list[tuple[str, int]] = []

    def on_evict(key: str, value: int) -> None:
        evicted.append((key, value))

    cache: BoundedCache[str, int] = BoundedCache(max_size=8, on_evict=on_evict)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.clear()
    assert len(evicted) == 2
    assert ("a", 1) in evicted
    assert ("b", 2) in evicted


def test_on_evict_fires_on_ttl_expiration() -> None:
    evicted: list[tuple[str, int]] = []

    def on_evict(key: str, value: int) -> None:
        evicted.append((key, value))

    cache: BoundedCache[str, int] = BoundedCache(max_size=8, ttl=0.05, on_evict=on_evict)
    cache.set("a", 1)
    time.sleep(0.1)
    cache.get("a")  # triggers expiration
    assert evicted == [("a", 1)]


def test_on_evict_exception_does_not_propagate() -> None:
    def bad_evict(key: str, value: int) -> None:
        raise RuntimeError("boom")  # noqa: TRY003

    cache: BoundedCache[str, int] = BoundedCache(max_size=2, on_evict=bad_evict)
    cache.set("a", 1)
    cache.set("b", 2)
    # This should not raise even though on_evict raises
    cache.set("c", 3)
    assert len(cache) == 2


# ── WS4: touch ────────────────────────────────────────────────────────


def test_touch_refreshes_access_time() -> None:
    cache: BoundedCache[str, int] = BoundedCache(max_size=3)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)
    # Touch "a" to make it most recently used
    assert cache.touch("a") is True
    # "b" is now LRU
    cache.set("d", 4)
    assert cache.get("a") == 1
    assert cache.get("b") is None


def test_touch_missing_key() -> None:
    cache: BoundedCache[str, int] = BoundedCache(max_size=4)
    assert cache.touch("nope") is False


# ── WS4: items / keys / values ────────────────────────────────────────


def test_keys_returns_all_keys() -> None:
    cache: BoundedCache[str, int] = BoundedCache(max_size=8)
    cache.set("a", 1)
    cache.set("b", 2)
    keys = cache.keys()
    assert set(keys) == {"a", "b"}


def test_values_returns_all_values() -> None:
    cache: BoundedCache[str, int] = BoundedCache(max_size=8)
    cache.set("a", 1)
    cache.set("b", 2)
    vals = cache.values()
    assert set(vals) == {1, 2}


def test_items_returns_key_value_pairs() -> None:
    cache: BoundedCache[str, int] = BoundedCache(max_size=8)
    cache.set("a", 1)
    cache.set("b", 2)
    items = cache.items()
    assert dict(items) == {"a": 1, "b": 2}


def test_iter_yields_keys() -> None:
    cache: BoundedCache[str, int] = BoundedCache(max_size=8)
    cache.set("x", 10)
    cache.set("y", 20)
    assert set(cache) == {"x", "y"}


# ── WS4: get_value (read-only peek) ───────────────────────────────────


def test_get_value_does_not_refresh_access_time() -> None:
    cache: BoundedCache[str, int] = BoundedCache(max_size=3)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)
    # Read-only peek on "a" should NOT refresh it
    assert cache.get_value("a") == 1
    # "a" is still LRU
    cache.set("d", 4)
    assert cache.get("a") is None
    assert cache.get("b") == 2


def test_get_value_missing_key() -> None:
    cache: BoundedCache[str, int] = BoundedCache(max_size=4)
    assert cache.get_value("nope", 42) == 42


# ── WS4: repeated insertion bounded growth ────────────────────────────


def test_repeated_insertion_stays_bounded() -> None:
    evict_count = 0

    def on_evict(key: str, value: int) -> None:
        nonlocal evict_count
        evict_count += 1

    cache: BoundedCache[str, int] = BoundedCache(max_size=5, on_evict=on_evict)
    for i in range(1000):
        cache.set(f"k{i}", i)
    assert len(cache) == 5
    assert evict_count == 995


# ── WS4: replacement updates value ────────────────────────────────────


def test_set_replaces_existing_value() -> None:
    cache: BoundedCache[str, int] = BoundedCache(max_size=4)
    cache.set("a", 1)
    cache.set("a", 2)
    assert cache.get("a") == 2
    assert len(cache) == 1


# ── WS4: TTL with eviction callback ───────────────────────────────────


def test_ttl_eviction_fires_callback() -> None:
    evicted: list[str] = []

    def on_evict(key: str, value: int) -> None:
        evicted.append(key)

    cache: BoundedCache[str, int] = BoundedCache(max_size=8, ttl=0.05, on_evict=on_evict)
    cache.set("a", 1)
    time.sleep(0.1)
    cache.get("a")
    assert evicted == ["a"]
