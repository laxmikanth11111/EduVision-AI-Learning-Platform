from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.workers import tasks as tasks_module


def _task_run(task: MagicMock, job_public_id: str) -> object:
    return tasks_module.export_generation_task.run.__func__(task, job_public_id)


class TestExportGenerationTask:
    def test_success_runs_async_export_to_completion(self) -> None:
        task = MagicMock()
        with patch(
            "app.workers.tasks._export_generation_async",
            AsyncMock(return_value=None),
        ) as export:
            result = _task_run(task, "job_abc")
        assert result is None
        assert export.await_args.args == ("job_abc",)
        task.retry.assert_not_called()

    def test_failure_triggers_retry(self) -> None:
        task = MagicMock()
        boom = RuntimeError("export boom")
        task.retry.side_effect = boom
        with patch(
            "app.workers.tasks._export_generation_async",
            AsyncMock(side_effect=boom),
        ), pytest.raises(RuntimeError):
            _task_run(task, "job_abc")
        task.retry.assert_called_once()

    def test_task_name_and_retry_config(self) -> None:
        task = tasks_module.export_generation_task
        assert task.name == "eduvision.exports.generate"
        assert task.max_retries == 3
        assert task.acks_late is True
