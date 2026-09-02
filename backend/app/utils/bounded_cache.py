"""Bounded in-memory cache with optional TTL and eviction callback.

Provides a size-capped, optionally time-expiring mapping for process-local
runtime state.  When the entry count reaches *max_size* the least-recently
accessed entry is evicted.  An optional *ttl* (seconds) causes entries to
expire on read.  An optional *on_evict* callback is invoked (synchronously)
each time an entry is removed — either by explicit deletion, size eviction,
or TTL expiration during access.

Single-process internals used by FastAPI (asyncio single loop) and service
singletons; the ``threading.Lock`` is a safety net for any concurrent callers
but is not the primary concurrency strategy.
"""

from __future__ import annotations

import contextlib
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Iterator
from typing import Any, Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class BoundedCache(Generic[K, V]):
    """A size-capped mapping with optional TTL and eviction callback.

    Parameters
    ----------
    max_size:
        Maximum number of entries.  Guaranteed minimum is 1.
    ttl:
        Time-to-live in **seconds**.  ``None`` (default) means entries never
        expire on their own.  Expiration is checked lazily on access; stale
        entries are removed on the next ``get`` / ``__contains__`` /
        ``__getitem__`` call.
    on_evict:
        Optional synchronous callback ``(key, value) -> None`` invoked each
        time an entry is removed (explicit delete, size-based eviction, or
        TTL expiration).  Used by callers that need to persist dirty state
        before the entry is discarded.
    """

    def __init__(
        self,
        max_size: int = 4096,
        ttl: float | None = None,
        on_evict: Callable[[K, V], Any] | None = None,
    ) -> None:
        self._max_size = max(1, max_size)
        self._ttl = ttl
        self._on_evict = on_evict
        # value -> (value, insertion_time)
        self._data: OrderedDict[K, tuple[V, float]] = OrderedDict()
        self._lock = threading.Lock()

    # -- core operations ---------------------------------------------------

    def set(self, key: K, value: V) -> None:
        """Insert or update *key* with *value*, refreshing its access time."""
        with self._lock:
            now = time.monotonic()
            if key in self._data:
                self._data[key] = (value, now)
                self._data.move_to_end(key)
            else:
                self._data[key] = (value, now)
                self._data.move_to_end(key)
            self._evict_if_needed()

    def get(self, key: K, default: V | None = None) -> V | None:
        """Return the value for *key* (refreshing its access time) or *default*."""
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return default
            value, ts = entry
            if self._is_expired(ts):
                self._remove(key, value)
                return default
            now = time.monotonic()
            self._data[key] = (value, now)
            self._data.move_to_end(key)
            return value

    def delete(self, key: K) -> bool:
        """Remove *key* if present.  Returns ``True`` if the key existed."""
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return False
            self._remove(key, entry[0])
            return True

    def pop(self, key: K, default: V | None = None) -> V | None:
        """Remove and return *key*'s value, or *default* if absent."""
        with self._lock:
            entry = self._data.pop(key, None)
            if entry is None:
                return default
            self._fire_evict(key, entry[0])
            return entry[0]

    def clear(self) -> None:
        """Remove all entries (firing *on_evict* for each)."""
        with self._lock:
            for key, (value, _) in self._data.items():
                self._fire_evict(key, value)
            self._data.clear()

    def touch(self, key: K) -> bool:
        """Refresh the access time of *key* without changing its value.

        Returns ``True`` if the key exists and was refreshed.
        """
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return False
            value, _ = entry
            now = time.monotonic()
            self._data[key] = (value, now)
            self._data.move_to_end(key)
            return True

    # -- dict-like helpers -------------------------------------------------

    def __contains__(self, key: K) -> bool:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return False
            if self._is_expired(entry[1]):
                self._remove(key, entry[0])
                return False
            return True

    def __getitem__(self, key: K) -> V:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                raise KeyError(key)
            value, ts = entry
            if self._is_expired(ts):
                self._remove(key, value)
                raise KeyError(key)
            now = time.monotonic()
            self._data[key] = (value, now)
            self._data.move_to_end(key)
            return value

    def __setitem__(self, key: K, value: V) -> None:
        self.set(key, value)

    def __delitem__(self, key: K) -> None:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                raise KeyError(key)
            self._remove(key, entry[0])

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)

    def __iter__(self) -> Iterator[K]:
        with self._lock:
            # Snapshot keys to avoid mutation during iteration.
            return iter(list(self._data.keys()))

    def keys(self) -> list[K]:
        with self._lock:
            return list(self._data.keys())

    def values(self) -> list[V]:
        with self._lock:
            return [v for v, _ in self._data.values()]

    def items(self) -> list[tuple[K, V]]:
        with self._lock:
            return [(k, v) for k, (v, _) in self._data.items()]

    def get_value(self, key: K, default: V | None = None) -> V | None:
        """Return value **without** refreshing the access time (read-only peek)."""
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return default
            if self._is_expired(entry[1]):
                self._remove(key, entry[0])
                return default
            return entry[0]

    # -- internals ---------------------------------------------------------

    def _is_expired(self, timestamp: float) -> bool:
        if self._ttl is None:
            return False
        return (time.monotonic() - timestamp) > self._ttl

    def _remove(self, key: K, value: V) -> None:
        """Remove entry from internal data and fire eviction callback."""
        self._data.pop(key, None)
        self._fire_evict(key, value)

    def _evict_if_needed(self) -> None:
        """Evict oldest entries while over capacity (must be called under lock)."""
        while len(self._data) > self._max_size:
            key, (value, _) = self._data.popitem(last=False)
            self._fire_evict(key, value)

    def _fire_evict(self, key: K, value: V) -> None:
        """Invoke the on_evict callback if set.  Exceptions are swallowed."""
        if self._on_evict is not None:
            with contextlib.suppress(Exception):
                self._on_evict(key, value)


__all__ = ["BoundedCache"]
