"""WS11: bounded in-memory runtime state cache.

The interactive runtime routers keep per-session state in memory. This cache
caps that state so long-running servers never grow without bound, and evicts
the least-recently-written entry once the cap is reached.
"""

from __future__ import annotations

from app.utils.bounded_cache import BoundedCache


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
