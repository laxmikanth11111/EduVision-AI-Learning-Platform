from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import structlog
import structlog.contextvars

from app.middleware.request_id import get_current_request_id, request_id_context
from app.observability.metrics import MetricsRegistry
from app.workers import celery_app as worker_module

_CORRELATION_HEADER = "X-Request-ID"


def _sender(name: str, task_id: str = "task-1") -> MagicMock:
    sender = MagicMock()
    sender.name = name
    sender.request = MagicMock(id=task_id)
    return sender


class TestBeforeTaskPublish:
    def test_adds_request_id_to_headers_from_context(self) -> None:
        token = request_id_context.set("req-abc")
        try:
            headers: dict[str, Any] = {}
            worker_module._on_before_task_publish(headers=headers)
            assert headers[_CORRELATION_HEADER] == "req-abc"
        finally:
            request_id_context.reset(token)

    def test_does_not_overwrite_existing_header(self) -> None:
        headers: dict[str, Any] = {_CORRELATION_HEADER: "keep-me"}
        worker_module._on_before_task_publish(headers=headers)
        assert headers[_CORRELATION_HEADER] == "keep-me"

    def test_noop_without_request_context(self) -> None:
        headers: dict[str, Any] = {}
        worker_module._on_before_task_publish(headers=headers)
        assert headers == {}

    def test_noop_without_headers(self) -> None:
        worker_module._on_before_task_publish(headers=None)


class TestTaskPrerunPostrun:
    def test_correlation_header_binds_contextvars_and_cleans_up(self) -> None:
        task = MagicMock(request=MagicMock(headers={_CORRELATION_HEADER: "corr-1"}))
        worker_module._on_task_prerun(task_id="t1", task=task)
        assert "t1" in worker_module._task_started_at
        assert "t1" in worker_module._task_context_tokens
        assert get_current_request_id() == ""  # caller's context untouched

        worker_module._on_task_postrun(task_id="t1")
        assert "t1" not in worker_module._task_started_at
        assert "t1" not in worker_module._task_context_tokens

    def test_no_header_leaves_contextvars_untouched(self) -> None:
        task = MagicMock(request=MagicMock(headers={}))
        worker_module._on_task_prerun(task_id="t2", task=task)
        assert "t2" in worker_module._task_started_at
        assert "t2" not in worker_module._task_context_tokens
        worker_module._on_task_postrun(task_id="t2")
        assert "t2" not in worker_module._task_started_at


class TestTaskSignalMetrics:
    def _with_clean_registry(self, monkeypatch: Any) -> MetricsRegistry:
        registry = MetricsRegistry()
        monkeypatch.setattr(worker_module, "metrics", registry)
        return registry

    def test_success_records_metric_and_duration(self, monkeypatch: Any) -> None:
        registry = self._with_clean_registry(monkeypatch)
        task = MagicMock(request=MagicMock(headers={}))
        worker_module._on_task_prerun(task_id="tid-s", task=task)
        worker_module._on_task_success(sender=_sender("eduvision.demo.run", "tid-s"))
        rendered = registry.render()
        assert 'worker_tasks_succeeded_total{task_name="eduvision.demo.run"} 1' in rendered
        assert 'task_name="eduvision.demo.run"' in rendered
        assert "_sum" in rendered
        assert "worker_tasks_duration_seconds_count" in rendered
        assert "tid-s" not in worker_module._task_started_at

    def test_failure_records_metric_and_duration(self, monkeypatch: Any) -> None:
        registry = self._with_clean_registry(monkeypatch)
        task = MagicMock(request=MagicMock(headers={}))
        worker_module._on_task_prerun(task_id="tid-f", task=task)
        worker_module._on_task_failure(sender=_sender("eduvision.demo.boom", "tid-f"))
        rendered = registry.render()
        assert 'worker_tasks_failed_total{task_name="eduvision.demo.boom"} 1' in rendered
        assert "worker_tasks_duration_seconds_sum" in rendered
        assert "tid-f" not in worker_module._task_started_at

    def test_success_without_prerun_records_count_only(self, monkeypatch: Any) -> None:
        registry = self._with_clean_registry(monkeypatch)
        worker_module._on_task_success(sender=_sender("eduvision.demo.fast"))
        rendered = registry.render()
        assert 'worker_tasks_succeeded_total{task_name="eduvision.demo.fast"} 1' in rendered
        assert "worker_tasks_duration_seconds_sum" not in rendered
