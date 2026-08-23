from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.workers import tasks as tasks_module


def _task_run(task: MagicMock, lesson_public_id: str) -> object:
    return tasks_module.lesson_generation_task.run.__func__(task, lesson_public_id)


class TestLessonGenerationTask:
    def test_success_returns_lesson_id(self) -> None:
        task = MagicMock()
        with patch(
            "app.workers.tasks._generate_lesson_async",
            AsyncMock(return_value="lesson_abc"),
        ):
            result = _task_run(task, "lesson_abc")
        assert result == "lesson_abc"
        task.retry.assert_not_called()

    def test_failure_triggers_retry(self) -> None:
        task = MagicMock()
        boom = RuntimeError("boom")
        task.retry.side_effect = boom
        with patch(
            "app.workers.tasks._generate_lesson_async",
            AsyncMock(side_effect=boom),
        ), pytest.raises(RuntimeError):
            _task_run(task, "lesson_abc")
        task.retry.assert_called_once()

    def test_task_name_and_retry_config(self) -> None:
        task = tasks_module.lesson_generation_task
        assert task.name == "eduvision.lessons.generate"
        assert task.max_retries == max(
            0, tasks_module.settings.AI_LESSON_MAX_ATTEMPTS - 1
        )
        assert task.acks_late is True
