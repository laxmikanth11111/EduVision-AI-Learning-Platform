from __future__ import annotations

from app.ai.ratelimit import AsyncRateLimiter


class _FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class _RecorderSleep:
    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.calls.append(delay)


class TestAsyncRateLimiter:
    async def test_disabled_when_rpm_zero(self) -> None:
        limiter = AsyncRateLimiter(rpm=0)
        assert limiter.enabled is False
        await limiter.acquire()

    async def test_initial_tokens_allow_first_acquire(self) -> None:
        limiter = AsyncRateLimiter(rpm=1)
        assert limiter.enabled is True
        await limiter.acquire()

    async def test_exhaustion_blocks_until_refill(self) -> None:
        clock = _FakeClock()
        sleep = _RecorderSleep()
        limiter = AsyncRateLimiter(rpm=1, clock=clock, sleep=sleep)

        await limiter.acquire()
        await limiter.acquire()
        assert sleep.calls == [60.0]

        clock.now = 60.0
        await limiter.acquire()
        assert len(sleep.calls) == 1

    async def test_constant_rate_does_not_block(self) -> None:
        clock = _FakeClock()
        sleep = _RecorderSleep()
        limiter = AsyncRateLimiter(rpm=60, clock=clock, sleep=sleep)

        for _ in range(60):
            await limiter.acquire()
        assert sleep.calls == []
