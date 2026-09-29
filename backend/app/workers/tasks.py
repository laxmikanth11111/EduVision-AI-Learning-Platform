from __future__ import annotations

import asyncio
import html
import smtplib
import time
import uuid
from collections.abc import Callable, Coroutine
from email.mime.text import MIMEText
from typing import Any, TypeVar

from celery import Task

from app.core.config import settings
from app.core.logging import get_logger
from app.database.unit_of_work import UnitOfWork
from app.observability.metrics import metrics
from app.workers.celery_app import celery_app

logger = get_logger(__name__)

DLQ_QUEUE = "dead_letter"

_R = TypeVar("_R")


def retry_backoff(task: Task, base_seconds: int = 60, cap_seconds: int = 600) -> int:
    # task.request is untyped (celery ships no stubs), so coerce explicitly.
    retries = int(getattr(task.request, "retries", 0) or 0)
    return int(min(base_seconds * (2**retries), cap_seconds))


class TaskWithDLQ(Task):  # type: ignore[misc]  # celery ships no type stubs
    abstract = True

    def on_failure(
        self,
        exc: Any,
        task_id: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any] | None,
        einfo: Any,
    ) -> None:
        super().on_failure(exc, task_id, args, kwargs, einfo)
        if not settings.CELERY_TASK_DLQ_ENABLED:
            return
        try:
            retries_exhausted = self.request.retries >= (self.max_retries or 0)
        except Exception:
            retries_exhausted = True
        if not retries_exhausted:
            return
        try:
            celery_app.send_task(
                "eduvision.dlq.record",
                kwargs={
                    "task_name": self.name,
                    "task_id": task_id,
                    "error": str(exc),
                    "args": list(args) if args else [],
                    "kwargs": kwargs or {},
                },
                queue=DLQ_QUEUE,
            )
            metrics.increment("dlq_forwarded_total", task_name=str(self.name))
        except Exception:
            pass


def _run_async(coro: Coroutine[Any, Any, _R]) -> _R:
    async def _wrapper() -> _R:
        try:
            return await coro
        finally:
            try:
                from app.database.session import engine
                await engine.dispose()
            except Exception:
                pass

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(lambda: asyncio.run(_wrapper()))
            return future.result()
    else:
        return asyncio.run(_wrapper())


def safe_dispatch(
    task: Any,
    *args: Any,
    on_failure: Callable[[Exception], None] | None = None,
    **kwargs: Any,
) -> None:
    """Enqueue a task with bounded retry against a flaky broker.

    A single broker ``delay()`` that raises (e.g. Redis briefly unreachable)
    would silently lose a job. This retries the enqueue up to
    ``CELERY_DISPATCH_RETRY_ATTEMPTS`` times with capped exponential backoff,
    then runs the optional ``on_failure`` hook. When ``CELERY_TASK_DLQ_ENABLED``
    and enough retries have been consumed, the task is forwarded to the
    dead-letter queue as ``eduvision.dlq.record`` so no job vanishes.
    """
    attempts = max(1, settings.CELERY_DISPATCH_RETRY_ATTEMPTS)
    base_delay = settings.CELERY_DISPATCH_RETRY_DELAY
    max_delay = settings.CELERY_DISPATCH_RETRY_MAX_DELAY
    task_name = str(getattr(task, "name", str(task)))

    for attempt in range(attempts):
        try:
            task.delay(*args, **kwargs)
            metrics.increment("task_dispatch_total", task_name=task_name, outcome="enqueued")
            return
        except Exception as exc:
            last_exc = exc
            metrics.increment("task_dispatch_total", task_name=task_name, outcome="failed")
            metrics.increment("task_dispatch_retries_total", task_name=task_name)
            if attempt + 1 < attempts:
                backoff = min(base_delay * (2**attempt), max_delay)
                time.sleep(backoff)

    logger.error(
        "task_dispatch_failed",
        task_name=task_name,
        error=str(last_exc),
    )
    if settings.CELERY_TASK_DLQ_ENABLED:
        _forward_to_dlq(task_name, last_exc, args, kwargs)
    if on_failure:
        try:
            on_failure(last_exc)
        except Exception as cb_exc:
            logger.error("task_dispatch_on_failure_failed", error=str(cb_exc))


def _forward_to_dlq(
    task_name: str,
    exc: Exception,
    args: Any,
    kwargs: dict[str, Any] | None,
) -> None:
    task_id = f"{task_name}:{uuid.uuid4().hex[:12]}"
    try:
        celery_app.send_task(
            "eduvision.dlq.record",
            kwargs={
                "task_name": task_name,
                "task_id": task_id,
                "error": str(exc),
                "args": list(args) if args else [],
                "kwargs": kwargs or {},
            },
            queue=DLQ_QUEUE,
        )
        metrics.increment("dlq_forwarded_total", task_name=task_name)
    except Exception:
        logger.error("task_dispatch_dlq_forward_failed", task_name=task_name)


@celery_app.task(  # type: ignore[untyped-decorator]
    name="eduvision.dlq.record",
    max_retries=0,
    acks_late=True,
)
def record_dlq_failure(
    task_name: str,
    task_id: str,
    error: str,
    args: list[Any] | None = None,
    kwargs: dict[str, Any] | None = None,
) -> None:
    logger.error(
        "dlq_task_received",
        task_name=task_name,
        task_id=task_id,
        error=error,
        args=args or [],
        kwargs=kwargs or {},
    )


def _escape_html(value: str) -> str:
    return html.escape(value, quote=True)


def _send_email(to: str, subject: str, html_body: str) -> None:
    if not settings.SMTP_HOST:
        logger.warning("smtp_not_configured", to=to, subject=subject)
        return

    msg = MIMEText(html_body, "html")
    msg["Subject"] = subject
    msg["From"] = f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM_ADDRESS}>"
    msg["To"] = to

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            if settings.SMTP_USE_TLS:
                server.starttls()
            if settings.SMTP_USER and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)
        logger.info("email_sent", to=to, subject=subject)
    except Exception as e:
        logger.error("email_send_failed", to=to, subject=subject, error=str(e))
        raise


# ── Presentation maintenance tasks ───────────────────────────────────────────


async def _generate_thumbnail_async(public_id: str) -> str:
    from app.services.presentation_service import PresentationService

    async with UnitOfWork() as uow:
        return await PresentationService(uow).generate_thumbnail(public_id)


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    name="eduvision.presentations.generate_thumbnail",
    max_retries=settings.CELERY_TASK_MAX_RETRIES,
    default_retry_delay=settings.CELERY_TASK_RETRY_DELAY,
    acks_late=True,
)
def generate_thumbnail_task(self: Any, public_id: str) -> str:
    logger.info("thumbnail_task_started", presentation_id=public_id)
    try:
        key = asyncio.run(_generate_thumbnail_async(public_id))
        logger.info("thumbnail_task_completed", presentation_id=public_id, key=key)
        return key
    except Exception as e:
        logger.exception("thumbnail_task_failed", presentation_id=public_id)
        raise self.retry(exc=e) from e


async def _start_source_ingestion_async(public_id: str) -> str:
    from app.services.presentation_service import PresentationService

    async with UnitOfWork() as uow:
        return await PresentationService(uow).start_source_ingestion(public_id)


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    name="eduvision.presentations.process_source_ingestion",
    max_retries=settings.CELERY_TASK_MAX_RETRIES,
    default_retry_delay=settings.CELERY_TASK_RETRY_DELAY,
    acks_late=True,
)
def process_source_ingestion_task(self: Any, public_id: str) -> str:
    logger.info("source_ingestion_task_started", presentation_id=public_id)
    try:
        result = _run_async(_start_source_ingestion_async(public_id))
        logger.info("source_ingestion_task_completed", presentation_id=public_id)
        return result
    except Exception as e:
        logger.exception("source_ingestion_task_failed", presentation_id=public_id)
        raise self.retry(exc=e) from e


async def _aggregate_analytics_async() -> int:
    from app.services.presentation_analytics_service import PresentationAnalyticsService

    async with UnitOfWork() as uow:
        return await PresentationAnalyticsService(uow).recompute_aggregates()


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    name="eduvision.presentations.aggregate_analytics",
    max_retries=settings.CELERY_TASK_MAX_RETRIES,
    default_retry_delay=settings.CELERY_TASK_RETRY_DELAY,
    acks_late=True,
)
def aggregate_analytics_task(self: Any) -> int:
    logger.info("analytics_aggregation_started")
    try:
        updated = _run_async(_aggregate_analytics_async())
        logger.info("analytics_aggregation_completed", updated=updated)
        return updated
    except Exception as e:
        logger.exception("analytics_aggregation_failed")
        raise self.retry(exc=e) from e


async def _cleanup_drafts_async(max_age_days: int) -> int:
    from app.services.presentation_service import PresentationService

    async with UnitOfWork() as uow:
        return await PresentationService(uow).cleanup_draft_presentations(max_age_days=max_age_days)


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    name="eduvision.presentations.cleanup_drafts",
    max_retries=settings.CELERY_TASK_MAX_RETRIES,
    default_retry_delay=settings.CELERY_TASK_RETRY_DELAY,
    acks_late=True,
)
def cleanup_draft_presentations_task(self: Any, max_age_days: int = 30) -> int:
    try:
        count = asyncio.run(_cleanup_drafts_async(max_age_days))
        logger.info("draft_cleanup_completed", count=count)
        return count
    except Exception as e:
        logger.exception("draft_cleanup_failed")
        raise self.retry(exc=e) from e


async def _cleanup_archived_async(retention_days: int) -> int:
    from app.services.presentation_service import PresentationService

    async with UnitOfWork() as uow:
        return await PresentationService(uow).cleanup_archived_presentations(
            retention_days=retention_days
        )


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    name="eduvision.presentations.cleanup_archived",
    max_retries=settings.CELERY_TASK_MAX_RETRIES,
    default_retry_delay=settings.CELERY_TASK_RETRY_DELAY,
    acks_late=True,
)
def cleanup_archived_presentations_task(self: Any, retention_days: int = 30) -> int:
    try:
        count = asyncio.run(_cleanup_archived_async(retention_days))
        logger.info("archive_cleanup_completed", count=count)
        return count
    except Exception as e:
        logger.exception("archive_cleanup_failed")
        raise self.retry(exc=e) from e


async def _cleanup_soft_deleted_async(retention_days: int) -> int:
    from app.services.presentation_service import PresentationService

    async with UnitOfWork() as uow:
        return await PresentationService(uow).cleanup_soft_deleted_presentations(
            retention_days=retention_days
        )


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    name="eduvision.presentations.cleanup_soft_deleted",
    max_retries=settings.CELERY_TASK_MAX_RETRIES,
    default_retry_delay=settings.CELERY_TASK_RETRY_DELAY,
    acks_late=True,
)
def cleanup_soft_deleted_presentations_task(self: Any, retention_days: int = 30) -> int:
    try:
        count = asyncio.run(_cleanup_soft_deleted_async(retention_days))
        logger.info("soft_deleted_cleanup_completed", count=count)
        return count
    except Exception as e:
        logger.exception("soft_deleted_cleanup_failed")
        raise self.retry(exc=e) from e


# ── Lesson generation tasks ──────────────────────────────────────────────────


async def _generate_lesson_async(lesson_public_id: str) -> str:
    from app.services.lesson_generation_service import LessonGenerationService

    async with UnitOfWork() as uow:
        await LessonGenerationService(uow).run_generation(lesson_public_id)
    return lesson_public_id


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    base=TaskWithDLQ,
    name="eduvision.lessons.generate",
    max_retries=max(0, settings.AI_LESSON_MAX_ATTEMPTS - 1),
    default_retry_delay=settings.CELERY_TASK_RETRY_DELAY,
    acks_late=True,
)
def lesson_generation_task(self: Any, lesson_public_id: str) -> str:
    logger.info("lesson_generation_task_started", lesson_id=lesson_public_id)
    try:
        result = _run_async(_generate_lesson_async(lesson_public_id))
        logger.info("lesson_generation_task_completed", lesson_id=lesson_public_id)
        if settings.RAG_INDEXING_ENABLED:
            from app.workers.rag_tasks import rag_indexing_task
            safe_dispatch(rag_indexing_task, "lesson", lesson_public_id)
        return result
    except Exception as e:
        logger.exception("lesson_generation_task_failed", lesson_id=lesson_public_id)
        raise self.retry(exc=e, countdown=retry_backoff(self)) from e


# ── Export tasks ──────────────────────────────────────────────────────────────


async def _export_generation_async(job_public_id: str) -> None:
    from app.services.export_service import ExportService
    async with UnitOfWork() as uow:
        service = ExportService(uow=uow)
        await service.process_export_job(job_public_id)


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    base=TaskWithDLQ,
    name="eduvision.exports.generate",
    max_retries=3,
    default_retry_delay=settings.CELERY_TASK_RETRY_DELAY,
    acks_late=True,
)
def export_generation_task(self: Any, job_public_id: str) -> None:
    logger.info("export_generation_task_started", job_id=job_public_id)
    try:
        _run_async(_export_generation_async(job_public_id))
        logger.info("export_generation_task_completed", job_id=job_public_id)
    except Exception as e:
        logger.exception("export_generation_task_failed", job_id=job_public_id)
        raise self.retry(exc=e, countdown=retry_backoff(self)) from e
