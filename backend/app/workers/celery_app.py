from __future__ import annotations

from typing import Any

from celery import Celery

from app.core.config import settings

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
