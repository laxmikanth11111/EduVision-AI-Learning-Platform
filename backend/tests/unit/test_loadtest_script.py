from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.workers.tasks import retry_backoff  # noqa: F401  (ensure app import path works)

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "loadtest_quiz.py"
sys.path.insert(0, str(_SCRIPT.parent))

from loadtest_quiz import _build_url, _percentile, _WorkerResult, print_report  # noqa: E402


class TestLoadTestHelpers:
    def test_percentile_median(self) -> None:
        assert _percentile([1, 2, 3, 4], 0.5) == 2
        assert _percentile([1, 2, 3, 4], 0.95) == 4
        assert _percentile([], 0.5) == 0.0

    def test_build_url_session_requires_quiz(self) -> None:
        url = _build_url("http://localhost:8000", "session", "quiz_abc")
        assert url == "http://localhost:8000/api/v1/quizzes/quiz_abc/session"
        with pytest.raises(SystemExit):
            _build_url("http://localhost:8000", "session", None)

    def test_build_url_adaptive_and_health(self) -> None:
        assert "users/me/adaptive-quiz" in _build_url(
            "http://localhost:8000", "adaptive", None
        )
        assert _build_url("http://localhost:8000", "health", None).endswith("/health")

    def test_print_report_handles_no_requests(self, capsys: pytest.CaptureFixture[str]) -> None:
        print_report(_WorkerResult(), duration=1.0, endpoint="health")
        out = capsys.readouterr().out
        assert "Requests:        0" in out
        assert "errors" in out.lower() or "Errors" in out
