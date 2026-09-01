"""Bounded in-memory cache for runtime routers.

The interactive runtime sync endpoints keep per-session state in process
memory. Without a bound that map grows without limit as sessions accumulate,
so this provides a size-capped mapping that evicts the least-recently-written
entry once the cap is reached. Single-process internals are used by the FastAPI
runtime synchronization handlers (asyncio single loop), so plain dict semantics
with LRU-style eviction are sufficient here.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class BoundedCache(Generic[K, V]):
    """A size-capped mapping that evicts the least-recently-written entry."""

    def __init__(self, max_size: int = 4096) -> None:
        self._max_size = max(1, max_size)
        self._data: OrderedDict[K, V] = OrderedDict()
        self._lock = threading.Lock()

    def set(self, key: K, value: V) -> None:
        with self._lock:
            self._data[key] = value
            self._data.move_to_end(key)
            while len(self._data) > self._max_size:
                self._data.popitem(last=False)

    def get(self, key: K, default: V | None = None) -> V | None:
        with self._lock:
            if key not in self._data:
                return default
            self._data.move_to_end(key)
            return self._data[key]

    def __contains__(self, key: K) -> bool:
        with self._lock:
            return key in self._data

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)


__all__ = ["BoundedCache"]
