from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.workers import rag_tasks as rag_module
from app.workers.celery_app import celery_app
from app.workers.tasks import TaskWithDLQ, safe_dispatch


def _run(real_task: Any, task: MagicMock, *args: object, **kwargs: object) -> object:
    return real_task.run.__func__(task, *args, **kwargs)


class TestEmbeddingGenerationTask:
    def test_success_returns_result(self) -> None:
        task = MagicMock()
        with patch(
            "app.workers.rag_tasks._embedding_generation_async",
            AsyncMock(return_value={"status": "processing", "batches_dispatched": 2}),
        ):
            result = _run(rag_module.embedding_generation_task, task, "ejob_abc")
        assert result == {"status": "processing", "batches_dispatched": 2}
        task.retry.assert_not_called()

    def test_passes_job_public_id(self) -> None:
        task = MagicMock()
        with patch(
            "app.workers.rag_tasks._embedding_generation_async",
            AsyncMock(return_value={"status": "completed"}),
        ) as gen:
            _run(rag_module.embedding_generation_task, task, "ejob_abc")
        assert gen.await_args.args == ("ejob_abc",)

    def test_failure_triggers_retry(self) -> None:
        task = MagicMock()
        boom = RuntimeError("boom")
        task.retry.side_effect = boom
        with (
            patch(
                "app.workers.rag_tasks._embedding_generation_async",
                AsyncMock(side_effect=boom),
            ),
            pytest.raises(RuntimeError),
        ):
            _run(rag_module.embedding_generation_task, task, "ejob_abc")
        task.retry.assert_called_once()


class TestEmbeddingBatchTask:
    def test_success_returns_result(self) -> None:
        task = MagicMock()
        with patch(
            "app.workers.rag_tasks._embedding_batch_async",
            AsyncMock(return_value={"status": "processed", "processed": 3}),
        ):
            result = _run(
                rag_module.embedding_batch_task, task, "ejob_abc", "ebat_abc"
            )
        assert result == {"status": "processed", "processed": 3}
        task.retry.assert_not_called()

    def test_passes_both_public_ids(self) -> None:
        task = MagicMock()
        with patch(
            "app.workers.rag_tasks._embedding_batch_async",
            AsyncMock(return_value={"status": "processed"}),
        ) as batch:
            _run(rag_module.embedding_batch_task, task, "ejob_abc", "ebat_abc")
        assert batch.await_args.args == ("ejob_abc", "ebat_abc")

    def test_failure_triggers_retry(self) -> None:
        task = MagicMock()
        boom = RuntimeError("boom")
        task.retry.side_effect = boom
        with (
            patch(
                "app.workers.rag_tasks._embedding_batch_async",
                AsyncMock(side_effect=boom),
            ),
            pytest.raises(RuntimeError),
        ):
            _run(rag_module.embedding_batch_task, task, "ejob_abc", "ebat_abc")
        task.retry.assert_called_once()


class TestEmbeddingRefreshTask:
    def test_success_returns_index_count(self) -> None:
        task = MagicMock()
        with patch(
            "app.workers.rag_tasks._embedding_refresh_async",
            AsyncMock(return_value=2),
        ):
            result = _run(rag_module.embedding_refresh_task, task)
        assert result == 2
        task.retry.assert_not_called()

    def test_defaults_limit_to_none(self) -> None:
        task = MagicMock()
        with patch(
            "app.workers.rag_tasks._embedding_refresh_async",
            AsyncMock(return_value=0),
        ) as refresh:
            _run(rag_module.embedding_refresh_task, task)
        assert refresh.await_args.args == (None,)

    def test_passes_limit(self) -> None:
        task = MagicMock()
        with patch(
            "app.workers.rag_tasks._embedding_refresh_async",
            AsyncMock(return_value=1),
        ) as refresh:
            _run(rag_module.embedding_refresh_task, task, 50)
        assert refresh.await_args.args == (50,)

    def test_failure_triggers_retry(self) -> None:
        task = MagicMock()
        boom = RuntimeError("boom")
        task.retry.side_effect = boom
        with (
            patch(
                "app.workers.rag_tasks._embedding_refresh_async",
                AsyncMock(side_effect=boom),
            ),
            pytest.raises(RuntimeError),
        ):
            _run(rag_module.embedding_refresh_task, task)
        task.retry.assert_called_once()


class TestEmbeddingCleanupTask:
    def test_success_returns_report(self) -> None:
        task = MagicMock()
        with patch(
            "app.workers.rag_tasks._embedding_cleanup_async",
            AsyncMock(return_value={"orphan_embeddings": 1}),
        ):
            result = _run(rag_module.embedding_cleanup_task, task)
        assert result == {"orphan_embeddings": 1}
        task.retry.assert_not_called()

    def test_failure_triggers_retry(self) -> None:
        task = MagicMock()
        boom = RuntimeError("boom")
        task.retry.side_effect = boom
        with (
            patch(
                "app.workers.rag_tasks._embedding_cleanup_async",
                AsyncMock(side_effect=boom),
            ),
            pytest.raises(RuntimeError),
        ):
            _run(rag_module.embedding_cleanup_task, task)
        task.retry.assert_called_once()


class TestEmbeddingStatisticsTask:
    def test_success_returns_index_count(self) -> None:
        task = MagicMock()
        with patch(
            "app.workers.rag_tasks._embedding_statistics_async",
            AsyncMock(return_value=3),
        ):
            result = _run(rag_module.embedding_statistics_task, task)
        assert result == 3
        task.retry.assert_not_called()

    def test_failure_triggers_retry(self) -> None:
        task = MagicMock()
        boom = RuntimeError("boom")
        task.retry.side_effect = boom
        with (
            patch(
                "app.workers.rag_tasks._embedding_statistics_async",
                AsyncMock(side_effect=boom),
            ),
            pytest.raises(RuntimeError),
        ):
            _run(rag_module.embedding_statistics_task, task)
        task.retry.assert_called_once()


class TestEmbeddingTaskConfiguration:
    def test_generation_task_name_and_config(self) -> None:
        task = rag_module.embedding_generation_task
        assert task.name == "eduvision.embedding.generate"
        assert task.max_retries == 2
        assert task.acks_late is True
        assert TaskWithDLQ in task.__class__.__mro__

    def test_batch_task_name_and_config(self) -> None:
        task = rag_module.embedding_batch_task
        assert task.name == "eduvision.embedding.batch"
        assert task.max_retries == 2
        assert task.acks_late is True
        assert TaskWithDLQ in task.__class__.__mro__

    def test_refresh_task_name_and_config(self) -> None:
        task = rag_module.embedding_refresh_task
        assert task.name == "eduvision.embedding.refresh"
        assert task.max_retries == 2
        assert task.acks_late is True
        assert TaskWithDLQ in task.__class__.__mro__

    def test_cleanup_task_name_and_config(self) -> None:
        task = rag_module.embedding_cleanup_task
        assert task.name == "eduvision.embedding.cleanup"
        assert task.max_retries == 2
        assert task.acks_late is True
        assert TaskWithDLQ in task.__class__.__mro__

    def test_statistics_task_name_and_config(self) -> None:
        task = rag_module.embedding_statistics_task
        assert task.name == "eduvision.embedding.statistics"
        assert task.max_retries == 2
        assert task.acks_late is True
        assert TaskWithDLQ in task.__class__.__mro__

    def test_tasks_are_included_in_celery_app(self) -> None:
        assert "app.workers.rag_tasks" in celery_app.conf.include

    def test_generation_routes_to_dedicated_queues(self) -> None:
        routes = celery_app.conf.task_routes
        assert routes["eduvision.embedding.generate"] == {"queue": "embeddings"}
        assert routes["eduvision.embedding.batch"] == {"queue": "embedding_batch"}

    def test_maintenance_tasks_route_to_analytics(self) -> None:
        routes = celery_app.conf.task_routes
        assert routes["eduvision.embedding.refresh"] == {"queue": "analytics"}
        assert routes["eduvision.embedding.cleanup"] == {"queue": "analytics"}
        assert routes["eduvision.embedding.statistics"] == {"queue": "analytics"}

    def test_beat_schedules_registered(self) -> None:
        beat = celery_app.conf.beat_schedule
        assert beat["embedding-refresh"]["task"] == "eduvision.embedding.refresh"
        assert beat["embedding-refresh"]["schedule"] == 900.0
        assert beat["embedding-cleanup"]["task"] == "eduvision.embedding.cleanup"
        assert beat["embedding-cleanup"]["schedule"] == 3600.0
        assert beat["embedding-statistics"]["task"] == "eduvision.embedding.statistics"
        assert beat["embedding-statistics"]["schedule"] == 86400.0


class TestSafeDispatch:
    def test_dispatch_calls_delay(self) -> None:
        task = MagicMock()
        safe_dispatch(task, "a", "b")
        task.delay.assert_called_once_with("a", "b")

    def test_dispatch_retries_then_swallows_broker_errors(self) -> None:
        task = MagicMock()
        task.delay.side_effect = ConnectionError("broker down")
        with patch(
            "app.workers.tasks.settings.CELERY_DISPATCH_RETRY_ATTEMPTS",
            3,
        ), patch(
            "app.workers.tasks.settings.CELERY_DISPATCH_RETRY_DELAY",
            0.0,
        ):
            result = safe_dispatch(task, "a")
        assert result is None
        assert task.delay.call_count == 3

    def test_dispatch_recovers_after_transient_failure(self) -> None:
        task = MagicMock()
        task.delay.side_effect = [ConnectionError("flaky"), MagicMock()]
        with patch(
            "app.workers.tasks.settings.CELERY_DISPATCH_RETRY_ATTEMPTS",
            3,
        ), patch(
            "app.workers.tasks.settings.CELERY_DISPATCH_RETRY_DELAY",
            0.0,
        ):
            safe_dispatch(task, "a")
        assert task.delay.call_count == 2

    def test_dispatch_forwards_to_dlq_after_exhaustion(self) -> None:
        task = MagicMock(delay=MagicMock(side_effect=ConnectionError("down")))
        task.name = "eduvision.test"
        with patch(
            "app.workers.tasks.settings.CELERY_DISPATCH_RETRY_ATTEMPTS",
            1,
        ), patch(
            "app.workers.tasks.settings.CELERY_TASK_DLQ_ENABLED",
            True,
        ), patch(
            "app.workers.tasks.celery_app.send_task",
            return_value=MagicMock(),
        ) as send_task:
            safe_dispatch(task, "a", flag=True)
        send_task.assert_called_once()
        kwargs = send_task.call_args.kwargs
        assert kwargs["queue"] == "dead_letter"
        assert kwargs["kwargs"]["task_name"] == "eduvision.test"
        assert kwargs["kwargs"]["args"] == ["a"]

    def test_dispatch_no_dlq_when_disabled(self) -> None:
        task = MagicMock(delay=MagicMock(side_effect=RuntimeError("boom")))
        task.name = "eduvision.test"
        with patch(
            "app.workers.tasks.settings.CELERY_DISPATCH_RETRY_ATTEMPTS",
            1,
        ), patch(
            "app.workers.tasks.settings.CELERY_TASK_DLQ_ENABLED",
            False,
        ), patch(
            "app.workers.tasks.celery_app.send_task",
            return_value=MagicMock(),
        ) as send_task:
            safe_dispatch(task, "a")
        send_task.assert_not_called()

    def test_dispatch_runs_on_failure_callback(self) -> None:
        task = MagicMock(delay=MagicMock(side_effect=RuntimeError("boom")))
        task.name = "eduvision.test"
        on_failure = MagicMock()
        with patch(
            "app.workers.tasks.settings.CELERY_DISPATCH_RETRY_ATTEMPTS",
            1,
        ), patch(
            "app.workers.tasks.settings.CELERY_DISPATCH_RETRY_DELAY",
            0.0,
        ):
            safe_dispatch(task, "a", on_failure=on_failure)
        on_failure.assert_called_once()
