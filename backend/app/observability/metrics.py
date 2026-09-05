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
HistogramBucket = float | str

# Prometheus-conventional seconds buckets for HTTP request durations.
DEFAULT_HISTOGRAM_BUCKETS: tuple[float, ...] = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
    float("inf"),
)


class MetricsRegistry:
    def __init__(self) -> None:
        self._counters: dict[str, dict[LabelKey, float]] = defaultdict(dict)
        self._gauges: dict[str, dict[LabelKey, float]] = defaultdict(dict)
        self._histograms: dict[str, dict[LabelKey, dict[HistogramBucket, float]]] = defaultdict(dict)
        self._histogram_buckets: dict[str, tuple[float, ...]] = {}
        self._help: dict[str, str] = {}
        self._lock = threading.Lock()

    def register(self, name: str, help_text: str) -> None:
        self._help[name] = help_text

    def set_histogram_buckets(self, name: str, buckets: tuple[float, ...]) -> None:
        """Override the default bucket boundaries for a histogram. Best-effort,
        only consulted at observe() time so an existing series is not mutated."""
        with self._lock:
            self._histogram_buckets[name] = tuple(sorted(buckets))

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

    def observe(self, name: str, value: float, **labels: str) -> None:
        """Record one sample in a histogram.

        Increments every ``le`` bucket whose boundary is >= ``value`` (so the
        ``+Inf`` bucket always increments) plus the ``_sum``/``_count`` series.
        """
        value = max(0.0, value)
        with self._lock:
            key = tuple(sorted(labels.items()))
            data = self._histograms[name].setdefault(key, {})
            buckets = self._histogram_buckets.get(name, DEFAULT_HISTOGRAM_BUCKETS)
            for boundary in buckets:
                if value <= boundary:
                    data[boundary] = data.get(boundary, 0.0) + 1.0
            data["_sum"] = data.get("_sum", 0.0) + value
            data["_count"] = data.get("_count", 0.0) + 1.0

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

    def _format_labels(self, labels: LabelKey, extra: tuple[tuple[str, str], ...] = ()) -> str:
        items = list(labels) + list(extra)
        return ",".join(f'{k}="{v}"' for k, v in sorted(items))

    def _render_histograms(self) -> str:
        lines: list[str] = []
        for name in sorted(self._histograms):
            help_text = self._help.get(name, "")
            lines.append(f"# HELP {name} {help_text}")
            lines.append(f"# TYPE {name} histogram")
            samples = self._histograms[name]
            for labels in sorted(samples):
                data = samples[labels]
                count = data.get("_count", 0.0)
                buckets = self._histogram_buckets.get(name, DEFAULT_HISTOGRAM_BUCKETS)
                for boundary in buckets:
                    le = "+Inf" if boundary == float("inf") else repr(boundary)
                    labels_line = self._format_labels(labels, (("le", le),))
                    value = data.get(boundary, 0.0)
                    lines.append(f"{name}_bucket{{{labels_line}}} {value:g}")
                sum_line = self._format_labels(labels)
                if sum_line:
                    lines.append(f"{name}_sum{{{sum_line}}} {data.get('_sum', 0.0):g}")
                    lines.append(f"{name}_count{{{sum_line}}} {count:g}")
                else:
                    lines.append(f"{name}_sum {data.get('_sum', 0.0):g}")
                    lines.append(f"{name}_count {count:g}")
        return "\n".join(lines)

    def render(self) -> str:
        with self._lock:
            counters = dict(self._counters)
            gauges = dict(self._gauges)
        lines = [
            self._render_series(counters, "counter"),
            self._render_series(gauges, "gauge"),
            self._render_histograms(),
        ]
        return "\n".join(line for line in lines if line)


metrics = MetricsRegistry()


def init_default_metrics() -> None:
    """Register the default metrics the codebase increments."""
    metrics.register("http_requests_total", "Total HTTP requests by method, route and status.")
    metrics.register("http_requests_duration_seconds", "HTTP request duration histogram in seconds.")
    metrics.set_histogram_buckets("http_requests_duration_seconds", DEFAULT_HISTOGRAM_BUCKETS)
    metrics.register("task_dispatch_total", "Background task enqueue attempts by task and outcome.")
    metrics.register("task_dispatch_retries_total", "Background task enqueue retries consumed by task.")
    metrics.register("worker_tasks_succeeded_total", "Celery worker task runs that succeeded, by task.")
    metrics.register("worker_tasks_failed_total", "Celery worker task runs that failed, by task.")
    metrics.register("worker_tasks_duration_seconds", "Celery worker task run duration histogram in seconds.")
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
    # ── P11 personalised plan / goals / learning path ─────────────────────────
    metrics.register("p11_plan_reads_total", "Today-plan reads, by outcome.")
    metrics.register("p11_plan_items_completed_total", "Today-plan items completed, by item type.")
    metrics.register("p11_goal_reads_total", "Learning-goal list/read calls, by outcome.")
    metrics.register("p11_goals_created_total", "Learning goals created, by goal type.")
    metrics.register("p11_goals_completed_total", "Learning goals completed, by outcome.")
    metrics.register("p11_path_reads_total", "Learning-path reads, by outcome.")
    # ── P12 adaptive assessment ───────────────────────────────────────────────
    metrics.register("p12_adaptive_starts_total", "Adaptive attempts started, by question count.")
    metrics.register("p12_adaptive_orders_total", "Adaptive question selections returned, by outcome (matched/up/down).")
    metrics.register("p12_adaptive_rejections_total", "Adaptive start requests rejected, by reason.")
    # ── P13 learner analytics ("know my trajectory") ──────────────────────────
    metrics.register("p13_analytics_views_total", "Learner-analytics endpoint reads, by endpoint and outcome.")
    metrics.register("p13_analytics_errors_total", "Learner-analytics endpoint failures, by endpoint and reason.")
    # ── P14 retention & review automation (closing the review loop) ───────────
    metrics.register("p14_review_outcomes_total", "Review completions recorded, by reported recall outcome.")
    metrics.register("p14_retention_views_total", "Learner retention-endpoint reads, by outcome.")
    metrics.register("p14_retention_errors_total", "Learner retention-endpoint failures, by reason.")



def render_metrics() -> str:
    return metrics.render()


