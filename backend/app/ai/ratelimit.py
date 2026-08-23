"""In-process async rate limiter for AI provider calls.

Applies the configured ``AI_RATE_LIMIT_RPM`` as a token bucket. This is a
per-process limiter; cross-worker coordination (Redis) is a future
enhancement. A value of ``0`` disables limiting.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

_WINDOW_SECONDS = 60.0


class AsyncRateLimiter:
    def __init__(
        self,
        rpm: int = 0,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._capacity = max(1, rpm)
        self._refill_rate = rpm / _WINDOW_SECONDS if rpm > 0 else 0.0
        self._tokens = float(self._capacity)
        self._last_refill = clock()
        self._clock = clock
        self._sleep = sleep
        self._lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return self._refill_rate > 0

    async def acquire(self) -> None:
        """Block until a rate-limit slot is available (no-op when disabled)."""
        if not self.enabled:
            return

        async with self._lock:
            now = self._clock()
            elapsed = max(0.0, now - self._last_refill)
            self._tokens = min(
                self._capacity,
                self._tokens + elapsed * self._refill_rate,
            )
            self._last_refill = now

            if self._tokens >= 1:
                self._tokens -= 1
                return

            deficit = (1 - self._tokens) / self._refill_rate
            self._tokens = 0.0

        if deficit > 0:
            await self._sleep(deficit)
