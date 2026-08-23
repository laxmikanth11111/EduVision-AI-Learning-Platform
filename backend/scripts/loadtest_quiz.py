"""Concurrent load test for the quiz subsystem's hot read endpoints.

Targets the endpoints that production traffic pounds the hardest:

* ``GET /api/v1/quizzes/{quiz_id}/session``   (cached published-version graph)
* ``GET /api/v1/users/me/adaptive-quiz``     (adaptive candidate selection)
* ``GET /api/v1/health``                       (baseline / control)

Usage (against a running backend):

    python scripts/loadtest_quiz.py \\
        --base-url http://localhost:8000 \\
        --concurrency 50 --duration 30 \\
        --token <ACCESS_TOKEN> --quiz-id <QUIZ_PUBLIC_ID>

Runs N concurrent workers that fire requests back-to-back for ``--duration``
seconds, then prints requests/sec, latency percentiles and error rate. The
script fails fast (exit code 2) if p95 latency exceeds ``--max-p95-ms`` or the
error rate exceeds ``--max-error-rate``, so it can gate a CI deploy.

Only stdlib + httpx are required; no locust/k6 dependency.
"""

from __future__ import annotations

import argparse
import asyncio
import math
import statistics
import time
from dataclasses import dataclass, field

import httpx


@dataclass
class _WorkerResult:
    latencies_ms: list[float] = field(default_factory=list)
    errors: int = 0
    status_counts: dict[int, int] = field(default_factory=dict)


def _build_url(base_url: str, endpoint: str, quiz_id: str | None) -> str:
    if endpoint == "session":
        if not quiz_id:
            raise SystemExit("--quiz-id is required for the session endpoint")
        return f"{base_url.rstrip('/')}/api/v1/quizzes/{quiz_id}/session"
    if endpoint == "adaptive":
        return f"{base_url.rstrip('/')}/api/v1/users/me/adaptive-quiz?max_questions=10"
    if endpoint == "health":
        return f"{base_url.rstrip('/')}/api/v1/health"
    raise SystemExit(f"Unknown endpoint: {endpoint}")


def _headers(token: str | None) -> dict[str, str]:
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


async def _worker(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    stop: asyncio.Event,
    result: _WorkerResult,
) -> None:
    while not stop.is_set():
        start = time.perf_counter()
        try:
            response = await client.get(url, headers=headers)
            status = response.status_code
            result.status_counts[status] = result.status_counts.get(status, 0) + 1
            if status >= 400:
                result.errors += 1
        except httpx.HTTPError:
            result.errors += 1
            status = 0
            result.status_counts[status] = result.status_counts.get(status, 0) + 1
        result.latencies_ms.append((time.perf_counter() - start) * 1000)


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    rank = max(1, min(len(sorted_values), math.ceil(q * len(sorted_values))))
    return sorted_values[rank - 1]


async def run_load(
    *,
    base_url: str,
    endpoint: str,
    concurrency: int,
    duration: float,
    token: str | None,
    quiz_id: str | None,
) -> _WorkerResult:
    url = _build_url(base_url, endpoint, quiz_id)
    headers = _headers(token)
    stop = asyncio.Event()
    results = [_WorkerResult() for _ in range(concurrency)]

    async with httpx.AsyncClient(timeout=30.0) as client:
        workers = [
            asyncio.create_task(_worker(client, url, headers, stop, result))
            for result in results
        ]
        await asyncio.sleep(duration)
        stop.set()
        await asyncio.gather(*workers)

    merged = _WorkerResult()
    for result in results:
        merged.latencies_ms.extend(result.latencies_ms)
        merged.errors += result.errors
        for status, count in result.status_counts.items():
            merged.status_counts[status] = merged.status_counts.get(status, 0) + count
    return merged


def print_report(result: _WorkerResult, *, duration: float, endpoint: str) -> None:
    total = len(result.latencies_ms)
    elapsed = max(duration, 0.001)
    rps = total / elapsed
    error_rate = result.errors / total if total else 0.0
    print(f"\n== Load test report: {endpoint} ==")
    print(f"Requests:        {total}")
    print(f"Throughput:      {rps:.1f} req/s")
    print(f"Errors:          {result.errors} ({error_rate * 100:.2f}%)")
    if result.latencies_ms:
        print(f"p50 latency:     {_percentile(result.latencies_ms, 0.50):.1f} ms")
        print(f"p95 latency:     {_percentile(result.latencies_ms, 0.95):.1f} ms")
        print(f"p99 latency:     {_percentile(result.latencies_ms, 0.99):.1f} ms")
        print(f"mean latency:    {statistics.mean(result.latencies_ms):.1f} ms")
        print(f"max latency:     {max(result.latencies_ms):.1f} ms")
    if result.status_counts:
        codes = ", ".join(
            f"{code}:{count}" for code, count in sorted(result.status_counts.items())
        )
        print(f"Status codes:    {codes}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument(
        "--endpoint",
        choices=["session", "adaptive", "health"],
        default="session",
    )
    parser.add_argument("--concurrency", type=int, default=50)
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--token", default=None)
    parser.add_argument("--quiz-id", default=None)
    parser.add_argument("--max-p95-ms", type=float, default=500.0)
    parser.add_argument("--max-error-rate", type=float, default=0.01)
    args = parser.parse_args()

    result = asyncio.run(
        run_load(
            base_url=args.base_url,
            endpoint=args.endpoint,
            concurrency=args.concurrency,
            duration=args.duration,
            token=args.token,
            quiz_id=args.quiz_id,
        )
    )
    print_report(result, duration=args.duration, endpoint=args.endpoint)

    p95 = _percentile(result.latencies_ms, 0.95)
    error_rate = result.errors / len(result.latencies_ms) if result.latencies_ms else 1.0
    if p95 > args.max_p95_ms or error_rate > args.max_error_rate:
        raise SystemExit(
            f"Load test FAILED: p95={p95:.1f}ms (max {args.max_p95_ms}ms), "
            f"error rate={error_rate:.4f} (max {args.max_error_rate})"
        )


if __name__ == "__main__":
    main()
