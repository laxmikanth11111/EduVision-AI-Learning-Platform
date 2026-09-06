from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.workers import video_tasks as video_tasks_module
from app.workers.tasks import TaskWithDLQ

_user_id = uuid.uuid4()


def _task_run(task: MagicMock, user_id: str, public_id: str) -> object:
    return video_tasks_module.video_render_task.run.__func__(task, user_id, public_id)


class TestVideoRenderTask:
    def test_success_returns_public_id(self) -> None:
        task = MagicMock()
        with patch(
            "app.workers.video_tasks._render_project_async",
            AsyncMock(return_value="vproj_abc"),
        ):
            result = _task_run(task, str(_user_id), "vproj_abc")
        assert result == "vproj_abc"

    def test_task_name_and_retry_config(self) -> None:
        task = video_tasks_module.video_render_task
        assert task.name == "eduvision.videos.render_project"
        assert task.max_retries == 0
        assert task.acks_late is True
        bound = task._get_current_object()
        assert issubclass(type(bound), TaskWithDLQ)

    def test_celery_include_and_route(self) -> None:
        from app.workers.celery_app import celery_app

        assert "app.workers.video_tasks" in celery_app.conf.include
        routes = celery_app.conf.task_routes
        assert "eduvision.videos.*" in routes
        assert routes["eduvision.videos.*"] == {"queue": "videos"}
