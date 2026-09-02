from __future__ import annotations

import threading
import time
from collections.abc import Mapping
from contextvars import Token
from typing import Any

import structlog
from celery import Celery
from celery.signals import (
    before_task_publish,
    task_failure,
    task_postrun,
    task_prerun,
    task_success,
)

from app.core.config import settings
from app.middleware.request_id import get_current_request_id
from app.observability.metrics import metrics

celery_app = Celery(
    "eduvision",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.workers.tasks", "app.workers.rag_tasks"],
)

celery_app.conf.update(
    task_serializer=settings.CELERY_TASK_SERIALIZER,
    result_serializer=settings.CELERY_RESULT_SERIALIZER,
    accept_content=settings.CELERY_ACCEPT_CONTENT,
    task_always_eager=settings.CELERY_TASK_ALWAYS_EAGER,
    task_eager_propagates=settings.CELERY_TASK_EAGER_PROPAGATES,
    task_ignore_result=True,
    worker_concurrency=settings.CELERY_WORKER_CONCURRENCY,
    task_track_started=True,
    task_time_limit=3600,
    task_soft_time_limit=3000,
    task_store_errors_even_if_ignored=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    result_expires=86400,
    task_default_queue=settings.CELERY_TASK_DEFAULT_QUEUE,
    task_default_exchange="eduvision.tasks",
    task_default_routing_key="eduvision.default",
    broker_connection_retry_on_startup=False,
    broker_connection_max_retries=1,
    task_routes={
        "eduvision.ai.*": {"queue": "ai"},
        "eduvision.upload.*": {"queue": "uploads"},
        "eduvision.notification.*": {"queue": "notifications"},
        "eduvision.email.*": {"queue": "email"},
        # RAG embedding pipeline
        "eduvision.rag.index": {"queue": "embeddings"},
        "eduvision.embedding.generate": {"queue": "embeddings"},
        "eduvision.embedding.batch": {"queue": "embedding_batch"},
        "eduvision.embedding.refresh": {"queue": "analytics"},
        "eduvision.embedding.cleanup": {"queue": "analytics"},
        "eduvision.embedding.statistics": {"queue": "analytics"},
        # Dead-letter inspection stream.
        "eduvision.dlq.record": {"queue": "dead_letter"},
    },
    worker_hijack_root_logger=False,
    worker_log_format="%(message)s",
    worker_task_log_format="%(message)s",
    beat_schedule={
        "health-check": {
            "task": "eduvision.health_check",
            "schedule": 300.0,
        },
        "aggregate-analytics-hourly": {
            "task": "eduvision.presentations.aggregate_analytics",
            "schedule": 3600.0,
        },
        "cleanup-drafts-daily": {
            "task": "eduvision.presentations.cleanup_drafts",
            "schedule": 86400.0,
            "kwargs": {"max_age_days": 30},
        },
        "cleanup-archived-daily": {
            "task": "eduvision.presentations.cleanup_archived",
            "schedule": 86400.0,
            "kwargs": {"retention_days": 30},
        },
        "cleanup-soft-deleted-daily": {
            "task": "eduvision.presentations.cleanup_soft_deleted",
            "schedule": 86400.0,
            "kwargs": {"retention_days": 30},
        },
        # RAG embedding pipeline maintenance
        "embedding-refresh": {
            "task": "eduvision.embedding.refresh",
            "schedule": float(settings.EMBEDDING_REFRESH_INTERVAL),
        },
        "embedding-cleanup": {
            "task": "eduvision.embedding.cleanup",
            "schedule": float(settings.EMBEDDING_CLEANUP_INTERVAL),
        },
        "embedding-statistics": {
            "task": "eduvision.embedding.statistics",
            "schedule": 86400.0,
        },
    },
)


@celery_app.task(
    bind=True,
    name="eduvision.health_check",
    max_retries=settings.CELERY_TASK_MAX_RETRIES,
    default_retry_delay=settings.CELERY_TASK_RETRY_DELAY,
    acks_late=True,
)
def health_check_task(self: Any) -> dict[str, Any]:
    return {"status": "ok", "worker": "celery", "queues": list(celery_app.conf.task_routes.keys())}


# ── Worker observability (correlation + task-run metrics) ────────────────────

_CORRELATION_HEADER = "X-Request-ID"
_task_started_at: dict[str, float] = {}
_task_context_tokens: dict[str, Mapping[str, Token[Any]]] = {}
_task_state_lock = threading.Lock()


def _on_before_task_publish(headers: dict[str, Any] | None = None, **kwargs: Any) -> None:
    """Bubble the API request ID into the broker message so a worker can
    correlate its logs with the originating HTTP request."""
    if headers is None:
        return
    request_id = get_current_request_id()
    if request_id and not headers.get(_CORRELATION_HEADER):
        headers[_CORRELATION_HEADER] = request_id


def _on_task_prerun(task_id: str = "", **kwargs: Any) -> None:
    task = kwargs.get("task")
    found = None
    if task is not None:
        req = getattr(task, "request", None)
        if req is not None:
            found = getattr(req, "headers", {}).get(_CORRELATION_HEADER) or None
    if found:
        # Bind only the correlation key; the API-side contextvar is restored
        # by reset_contextvars(**tokens) at postrun so an eager/in-process run
        # never leaks the worker binding into the caller's context.
        tokens = structlog.contextvars.bind_contextvars(request_id=found)
        with _task_state_lock:
            _task_context_tokens[str(task_id)] = tokens
    with _task_state_lock:
        _task_started_at[str(task_id)] = time.monotonic()


def _task_duration(task_id: str) -> float | None:
    with _task_state_lock:
        started = _task_started_at.pop(str(task_id), None)
    if started is None:
        return None
    return time.monotonic() - started


def _on_task_postrun(task_id: str = "", **kwargs: Any) -> None:
    with _task_state_lock:
        _task_started_at.pop(str(task_id), None)
        tokens = _task_context_tokens.pop(str(task_id), None)
    if tokens:
        structlog.contextvars.reset_contextvars(**tokens)


def _task_run_id(sender: Any) -> str:
    request = getattr(sender, "request", None)
    if request is not None:
        task_id = getattr(request, "id", None)
        if task_id is not None:
            return str(task_id)
    return str(getattr(sender, "name", sender))


def _task_name(sender: Any) -> str:
    return str(getattr(sender, "name", sender))


def _on_task_success(sender: Any = None, **kwargs: Any) -> None:
    duration = _task_duration(_task_run_id(sender))
    metrics.increment("worker_tasks_succeeded_total", task_name=_task_name(sender))
    if duration is not None:
        metrics.observe("worker_tasks_duration_seconds", duration, task_name=_task_name(sender))


def _on_task_failure(sender: Any = None, **kwargs: Any) -> None:
    duration = _task_duration(_task_run_id(sender))
    metrics.increment("worker_tasks_failed_total", task_name=_task_name(sender))
    if duration is not None:
        metrics.observe("worker_tasks_duration_seconds", duration, task_name=_task_name(sender))


before_task_publish.connect(_on_before_task_publish)
task_prerun.connect(_on_task_prerun)
task_postrun.connect(_on_task_postrun)
task_success.connect(_on_task_success)
task_failure.connect(_on_task_failure)
