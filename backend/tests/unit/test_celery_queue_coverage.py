"""Worker queue coverage: every routed queue must be consumed by the worker.

A Celery worker only consumes queues named by ``-Q``. ``task_routes`` publishes
tasks to ten distinct queues, and the container worker command used to pass no
``-Q`` at all, so it consumed only ``default``. Every task routed to another
queue was published to Redis and then silently never executed -- no error, no
log line, no trace.

These tests pin both halves of the fix:
  1. the in-process guard rejects a queue list that misses a routed queue, and
  2. the ``docker-compose.yml`` worker command actually passes ``-Q`` with the
     full list, so the guard cannot pass while the container still starts a
     worker that ignores the queues.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.core.config import Settings, settings
from app.workers.celery_app import celery_app

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"


def _routed_queues() -> set[str]:
    return {
        route["queue"]
        for route in celery_app.conf.task_routes.values()
        if isinstance(route, dict) and "queue" in route
    }


def test_worker_queues_cover_every_routed_queue() -> None:
    routed = _routed_queues()
    consumed = {q.strip() for q in settings.CELERY_WORKER_QUEUES.split(",") if q.strip()}
    assert not (routed - consumed), (
        f"routed queues not consumed by the worker: {sorted(routed - consumed)}"
    )


def test_drift_guard_raises_when_a_routed_queue_is_missing(monkeypatch) -> None:
    """The guard must actually fail when the two lists disagree."""
    from app.workers import celery_app as celery_module

    monkeypatch.setattr(
        celery_module.settings,
        "CELERY_WORKER_QUEUES",
        settings.CELERY_TASK_DEFAULT_QUEUE,
    )
    with pytest.raises(RuntimeError, match="does not cover every routed queue"):
        celery_module._assert_routed_queues_are_consumed()


def test_compose_worker_command_passes_full_queue_list() -> None:
    compose = COMPOSE_FILE.read_text(encoding="utf-8")
    match = re.search(
        r"celery -A app\.workers\.celery_app worker.*?-Q "
        r"\$\{CELERY_WORKER_QUEUES:-([^}]+)\}",
        compose,
        re.DOTALL,
    )
    assert match is not None, "celery-worker command must pass -Q ${CELERY_WORKER_QUEUES}"

    compose_queues = {q.strip() for q in match.group(1).split(",") if q.strip()}
    assert compose_queues == _routed_queues(), (
        "compose default queue list is out of sync with task_routes: "
        f"compose={sorted(compose_queues)} routed={sorted(_routed_queues())}"
    )


def test_default_queue_setting_is_covered_by_worker_queues() -> None:
    consumed = {q.strip() for q in settings.CELERY_WORKER_QUEUES.split(",") if q.strip()}
    assert settings.CELERY_TASK_DEFAULT_QUEUE in consumed


def test_settings_expose_worker_queue_list() -> None:
    assert isinstance(Settings().CELERY_WORKER_QUEUES, str)
    assert "embeddings" in settings.CELERY_WORKER_QUEUES
    assert "videos" in settings.CELERY_WORKER_QUEUES
