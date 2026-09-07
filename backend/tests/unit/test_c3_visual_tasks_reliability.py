"""C3.5 - C3 task queue-lifecycle reliability tests.

Verifies the C3 generate-visuals task is routed to the ``default`` queue that
the canonical worker consumes, configures Celery-level retries (``max_retries``,
``acks_late``), inherits the shared dead-letter behavior (``TaskWithDLQ`` / ``safe_dispatch``),
and never swallows unexpected exceptions (so Celery's retry machinery can act).
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.workers import c3_visual_tasks as c3_module
from app.workers.celery_app import celery_app
from app.workers.tasks import TaskWithDLQ, safe_dispatch


def _run(real_task: Any, task: MagicMock, *args: object, **kwargs: object) -> object:
    return real_task.run.__func__(task, *args, **kwargs)


class TestC3TaskConfiguration:
    def test_task_name_and_config(self) -> None:
        task = c3_module.c3_generate_visuals_task
        assert task.name == "eduvision.c3.generate_visuals"
        assert task.max_retries == 2
        assert task.default_retry_delay == 60
        assert task.acks_late is True
        assert TaskWithDLQ in task.__class__.__mro__

    def test_task_has_no_hardcoded_queue(self) -> None:
        # Routing is by task name via task_routes so the canonical worker
        # (which consumes only "default") can pick the task up.
        task = c3_module.c3_generate_visuals_task
        assert getattr(task, "queue", None) is None

    def test_task_is_included_in_celery_app(self) -> None:
        assert "app.workers.c3_visual_tasks" in celery_app.conf.include


class TestC3TaskRouting:
    def test_task_routes_to_default_queue(self) -> None:
        assert celery_app.conf.task_routes["eduvision.c3.*"] == {"queue": "default"}

    def test_amqp_router_resolves_c3_task_to_default(self) -> None:
        route = celery_app.amqp.router.route(
            {}, "eduvision.c3.generate_visuals", args=["pres_x", str(uuid.uuid4())], kwargs={}
        )
        assert route is not None
        assert route["queue"].name == "default"


class TestC3TaskFailureHandling:
    def test_unexpected_failure_propagates_for_celery_retry(self) -> None:
        """An infra exception must bubble out of the task so Celery retries it,
        rather than being swallowed and losing the job."""
        task = MagicMock()
        boom = RuntimeError("db connection lost")
        with (
            patch(
                "app.workers.c3_visual_tasks._generate_visuals_async",
                AsyncMock(side_effect=boom),
            ),
            pytest.raises(RuntimeError),
        ):
            _run(
                c3_module.c3_generate_visuals_task,
                task,
                "pres_x",
                str(uuid.uuid4()),
            )
        task.retry.assert_not_called()

    def test_clean_hard_failures_return_result_without_retry(self) -> None:
        """Deterministic business failures return a structured result so the
        task succeeds from Celery's point of view (no spurious retry/DLQ)."""
        task = MagicMock()
        with patch(
            "app.workers.c3_visual_tasks._generate_visuals_async",
            AsyncMock(return_value={"success": False, "error": "Presentation not found"}),
        ):
            result = _run(
                c3_module.c3_generate_visuals_task,
                task,
                "pres_missing",
                str(uuid.uuid4()),
            )
        assert result == {"success": False, "error": "Presentation not found"}
        task.retry.assert_not_called()


class TestC3Dispatch:
    def test_dispatch_enqueues_c3_task(self) -> None:
        uid = str(uuid.uuid4())
        with patch.object(
            c3_module.c3_generate_visuals_task, "delay", return_value=MagicMock()
        ) as delay:
            safe_dispatch(c3_module.c3_generate_visuals_task, "pres_x", uid)
        delay.assert_called_once_with("pres_x", uid)

    def test_dispatch_records_c3_task_name_in_dlq(self) -> None:
        task = MagicMock(delay=MagicMock(side_effect=ConnectionError("down")))
        task.name = c3_module.c3_generate_visuals_task.name
        with (
            patch(
                "app.workers.tasks.settings.CELERY_DISPATCH_RETRY_ATTEMPTS",
                1,
            ),
            patch(
                "app.workers.tasks.settings.CELERY_TASK_DLQ_ENABLED",
                True,
            ),
            patch(
                "app.workers.tasks.celery_app.send_task",
                return_value=MagicMock(),
            ) as send_task,
        ):
            safe_dispatch(task, "pres_x")
        send_task.assert_called_once()
        kwargs = send_task.call_args.kwargs
        assert kwargs["queue"] == "dead_letter"
        assert kwargs["kwargs"]["task_name"] == "eduvision.c3.generate_visuals"
        assert kwargs["kwargs"]["args"] == ["pres_x"]
