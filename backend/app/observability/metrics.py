"""Dependency-free in-process metrics registry (Prometheus text exposition).

Kept dependency-light on purpose: the API surface is a single
``GET /api/v1/metrics`` endpoint that renders counters/gauges in the
Prometheus text format (``# HELP`` / ``# TYPE`` / ``name{labels} value``),
which any Prometheus/OpenMetrics scraper can consume directly. Counters are
per-process and monotonic, so horizontal scale should aggregate them across
replicas rather than rely on per-instance totals.
"""

from __future__ import annotations

import threading
from collections import defaultdict

from app.core.logging import get_logger

logger = get_logger(__name__)


LabelKey = tuple[tuple[str, str], ...]


class MetricsRegistry:
    def __init__(self) -> None:
        self._counters: dict[str, dict[LabelKey, float]] = defaultdict(dict)
        self._gauges: dict[str, dict[LabelKey, float]] = defaultdict(dict)
        self._help: dict[str, str] = {}
        self._lock = threading.Lock()

    def register(self, name: str, help_text: str) -> None:
        self._help[name] = help_text

    def increment(self, name: str, value: float = 1.0, **labels: str) -> None:
        with self._lock:
            key = tuple(sorted(labels.items()))
            self._counters[name][key] = (
                self._counters[name].get(key, 0.0) + value
            )

    def set_gauge(self, name: str, value: float, **labels: str) -> None:
        with self._lock:
            key = tuple(sorted(labels.items()))
            self._gauges[name][key] = value

    def _render_series(
        self,
        series: dict[str, dict[LabelKey, float]],
        kind: str,
        suffix: str = "",
    ) -> str:
        lines: list[str] = []
        for name, samples in sorted(series.items()):
            metric_name = f"{name}{suffix}"
            help_text = self._help.get(name, "")
            lines.append(f"# HELP {metric_name} {help_text}")
            lines.append(f"# TYPE {metric_name} {kind}")
            for labels, value in sorted(samples.items()):
                if labels:
                    rendered_labels = ",".join(
                        f'{k}="{v}"' for k, v in labels
                    )
                    lines.append(f"{metric_name}{{{rendered_labels}}} {value:g}")
                else:
                    lines.append(f"{metric_name} {value:g}")
        return "\n".join(lines)

    def render(self) -> str:
        with self._lock:
            counters = dict(self._counters)
            gauges = dict(self._gauges)
        lines = [
            self._render_series(counters, "counter"),
            self._render_series(gauges, "gauge"),
        ]
        return "\n".join(line for line in lines if line)


metrics = MetricsRegistry()


def init_default_metrics() -> None:
    """Register the default metrics the codebase increments."""
    metrics.register("http_requests_total", "Total HTTP requests by method, route and status.")
    metrics.register("http_requests_duration_seconds_sum", "Sum of HTTP request durations in seconds.")
    metrics.register("http_requests_duration_seconds_count", "Count of HTTP request durations.")
    metrics.register("quiz_cache_hits_total", "Quiz read-cache hits.")
    metrics.register("quiz_cache_misses_total", "Quiz read-cache misses.")
    metrics.register("quiz_cache_errors_total", "Quiz read-cache Redis errors (fail-open).")
    metrics.register("dlq_forwarded_total", "Tasks forwarded to the dead-letter queue after retries exhausted.")
    # ── RAG embedding workers (Phase 4E.1 + 4E.2) ─────────────────────────────
    metrics.register("embedding_tasks_started_total", "Embedding worker task runs started, by task.")
    metrics.register("embedding_tasks_completed_total", "Embedding worker task runs completed, by task.")
    metrics.register("embedding_tasks_failed_total", "Embedding worker task runs failed, by task.")
    metrics.register("embedding_processing_seconds_total", "Total embedding worker wall-clock seconds, by task.")
    metrics.register("embedding_generation_jobs_total", "Embedding jobs finalized, by terminal status.")
    metrics.register("embedding_generation_batches_dispatched_total", "Embedding batches dispatched by the generation worker.")
    metrics.register("embedding_batches_processed_total", "Embedding batches processed by the batch worker.")
    metrics.register("embedding_batches_failed_total", "Embedding batches that failed processing.")
    metrics.register("embedding_retries_total", "Embedding worker retries raised, by task.")
    metrics.register("embedding_refresh_stale_total", "Stale chunks detected by the refresh worker.")
    metrics.register("embedding_refresh_embedded_total", "Stale chunks re-embedded by the refresh worker.")
    metrics.register("embedding_cleanup_orphans_total", "Orphan embeddings removed by the cleanup worker.")
    metrics.register("embedding_cleanup_obsolete_total", "Obsolete embedding versions removed by the cleanup worker.")
    metrics.register("embedding_cleanup_batches_recovered_total", "Failed batches requeued by the cleanup worker.")
    metrics.register("embedding_cleanup_jobs_expired_total", "Expired embedding jobs reclaimed by the cleanup worker.")
    metrics.register("embedding_cleanup_metadata_total", "Stale embedding metadata rows marked obsolete.")
    metrics.register("embedding_provider_usage_total", "Active embeddings per provider/model.")
    metrics.register("embedding_versions_total", "Embedding version rows per status.")
    metrics.register("embedding_storage_bytes", "Estimated storage footprint of active embedding vectors in bytes.")
    metrics.register("embedding_dimension", "Average active embedding vector dimension.")
    metrics.register("embedding_queue_backlog", "Queued embedding jobs awaiting a worker.")



def render_metrics() -> str:
    return metrics.render()


