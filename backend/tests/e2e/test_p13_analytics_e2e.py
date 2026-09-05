"""P13 browser E2E — the learner-analytics dashboard panels.

Drives the vanilla SPA in a real browser against a seeded learner whose
history makes the analytics deterministic: 3 completed attempts at 40/65/90,
a persisted educational memory with ONE weak (35, improving) and ONE mastered
(90, stable) concept linked to the practice lesson, and one completed session.

``server_env`` runs uvicorn against the shared SQLite test DB; API/browser
calls handle user registration + the lesson, and a direct sync-sqlite seed
mirrors the integration-test data so the dashboard renders real analytics:

1. ``test_p13_dashboard_analytics_panels_render`` — dashboard must show the
   "Your Trajectory" bars (40/65/90%), the focus callout, the "Concepts at a
   Glance" rows with band chip + trend arrow + server-built Practice/Ask-tutor
   deep-links, and the "Effort vs Mastery" row ("3 attempts -> +38 mastery").
2. ``test_p13_dashboard_empty_state`` — a brand-new learner sees the documented
   empty-state copy instead of metrics she has not earned yet.
3. ``test_p13_player_dashboard_hub_link`` — ``player.html`` exposes a working
   Dashboard header link (P13-A5 hub).
"""
from __future__ import annotations

import datetime as dt
import time
import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from tests.conftest import TEST_DB_PATH
from tests.learner_progress_helpers import build_memory_json


@pytest.fixture(scope="session")
def browser_context_args():
    return {
        "viewport": {"width": 1280, "height": 900},
        "ignore_https_errors": True,
    }


@pytest.fixture(scope="session")
def browser_type_launch_args():
    return {
        "headless": True,
        "channel": "chrome",
        "args": [
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--disable-web-security",
        ],
    }


def _register_and_create_deck(page, base_url: str) -> dict[str, str]:
    """Register a learner and create a presentation + lesson they own."""
    email = f"p13_{uuid.uuid4().hex[:10]}@example.com"
    password = "P13Loop1234!"
    name = "P13 Learner"

    result = page.evaluate(
        """async ([base, email, password, name]) => {
            const regRes = await fetch(base + '/api/v1/auth/register', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ email, password, name }),
            });
            const regData = await regRes.json();
            const token = regData.tokens.access_token;
            const auth = { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token };

            const presRes = await fetch(base + '/api/v1/presentations/manual', {
                method: 'POST',
                headers: auth,
                body: JSON.stringify({ title: 'P13 Deck', topics: ['Gaussians', 'Vectors'] }),
            });
            const presData = await presRes.json();
            const presId = presData.data.id;

            const lessonRes = await fetch(base + '/api/v1/presentations/' + presId + '/lessons', {
                method: 'POST',
                headers: auth,
                body: JSON.stringify({ mode: 'slide', title: 'P13 Analytics Lesson' }),
            });
            const lessonData = await lessonRes.json();
            return { userId: regData.user.id, lessonId: lessonData.data.id, presId };
        }""",
        [base_url, email, password, name],
    )

    return {
        "email": email,
        "password": password,
        "name": name,
        "user_id": result["userId"],
        "lesson_id": result["lessonId"],
        "presentation_id": result["presId"],
    }


def _seed_p13_analytics(user_id: str, lesson_public_id: str) -> dict[str, str]:
    """Seed attempts/memory/session so the dashboard analytics are deterministic.

    Completed attempts at 40 -> 65 -> 90 (one per day), one completed session,
    and a memory where ``weak`` (35, improving) and ``strong`` (90, stable) both
    belong to the practice lesson. Both concepts share the attempt series, so
    every trend_delta = +37.5 (the UI renders \"+38 mastery\", \"13 pts/attempt\").
    """
    from app.models.concept import Concept
    from app.models.educational_memory import EducationalMemoryRecord
    from app.models.generated_lesson import GeneratedLesson
    from app.models.learning_session import LearningSession
    from app.models.quiz import Quiz
    from app.models.quiz_attempt import QuizAttempt
    from app.models.quiz_version import QuizVersion
    from app.models.score_summary import ScoreSummary

    sync_engine = create_engine(
        f"sqlite:///{TEST_DB_PATH.as_posix()}", connect_args={"timeout": 30}
    )
    weak_id = f"concept_p13_weak_{uuid.uuid4().hex[:8]}"
    strong_id = f"concept_p13_strong_{uuid.uuid4().hex[:8]}"

    with Session(sync_engine) as s:
        lesson = s.execute(
            select(GeneratedLesson).where(GeneratedLesson.public_id == lesson_public_id)
        ).scalar_one()

        quiz = Quiz(
            presentation_id=lesson.presentation_id,
            lesson_id=lesson.id,
            user_id=lesson.user_id,
            status="published",
            mode="practice",
            title="Checkpoint: Trajectory",
            question_count=1,
            max_attempts_per_user=3,
            passing_score=50.0,
            show_feedback_after=True,
            latest_version=1,
            published_version=1,
        )
        s.add(quiz)
        s.flush()
        version = QuizVersion(quiz_id=quiz.id, version=1, status="published", title="v1")
        s.add(version)
        s.flush()

        weak = Concept(
            public_id=weak_id,
            name="Gaussian Foundations",
            topic="probability",
            presentation_id=lesson.presentation_id,
            lesson_id=lesson.id,
        )
        strong = Concept(
            public_id=strong_id,
            name="Vector Spaces",
            topic="linear-algebra",
            presentation_id=lesson.presentation_id,
            lesson_id=lesson.id,
        )
        s.add_all([weak, strong])
        s.flush()

        now = dt.datetime.now(dt.UTC)
        percents = [40.0, 65.0, 90.0]
        for index, percent in enumerate(percents):
            completed_at = now - dt.timedelta(days=2 - index)
            attempt = QuizAttempt(
                quiz_id=quiz.id,
                quiz_version_id=version.id,
                user_id=lesson.user_id,
                attempt_number=index + 1,
                status="completed",
                score=percent / 100.0,
                max_score=1.0,
                percent_score=percent,
                time_spent_seconds=240 + index * 15,
                is_practice=False,
                started_at=completed_at - dt.timedelta(seconds=120),
                completed_at=completed_at,
            )
            s.add(attempt)
            s.flush()
            s.add(
                ScoreSummary(
                    attempt_id=attempt.id,
                    total_points=3,
                    earned_points=(percent / 100.0) * 3.0,
                    percent=percent,
                    correct_count=[1, 2, 3][index],
                    incorrect_count=[2, 1, 0][index],
                    partially_correct_count=0,
                    unanswered_count=0,
                )
            )

        s.add(
            LearningSession(
                user_id=lesson.user_id,
                lesson_id=lesson.id,
                status="completed",
                completion_percentage=100.0,
                total_time_seconds=600,
                current_slide_position=0,
                current_block_position=0,
                resume_version=0,
            )
        )

        memory = build_memory_json(str(lesson.user_id))
        memory["weak_concepts"] = [weak_id]
        memory["mastered_concepts"] = [strong_id]
        memory["developing_concepts"] = []
        memory["concept_records"] = {
            weak_id: {
                "concept_id": weak_id,
                "concept_name": "Gaussian Foundations",
                "first_learned_at": now.timestamp() - 3600,
                "last_reviewed_at": now.timestamp(),
                "mastery_score": 35.0,
                "review_count": 2,
                "trend": "improving",
                "confidence_score": 0.4,
            },
            strong_id: {
                "concept_id": strong_id,
                "concept_name": "Vector Spaces",
                "first_learned_at": now.timestamp() - 86400,
                "last_reviewed_at": now.timestamp() - 100,
                "mastery_score": 90.0,
                "review_count": 6,
                "trend": "stable",
                "confidence_score": 0.9,
            },
        }
        s.add(
            EducationalMemoryRecord(
                user_id=lesson.user_id,
                memory_data=memory,
            )
        )
        s.commit()

    return {
        "weak_id": weak_id,
        "strong_id": strong_id,
        "lesson_public_id": lesson_public_id,
    }


def _sign_in(page, base_url: str, email: str, password: str) -> None:
    page.goto(f"{base_url}/frontend/signin.html")
    page.wait_for_load_state("domcontentloaded")
    page.fill("#email", email)
    page.fill("#password", password)
    page.click("#submitBtn")
    page.wait_for_url("**/upload.html", timeout=20_000)
    page.wait_for_load_state("domcontentloaded")


@pytest.mark.e2e
def test_p13_dashboard_analytics_panels_render(server_env, page):
    from app.core.dependencies import get_current_user as _get_current_user
    from app.main import app as _app
    from app.services.educational_memory_service import (
        educational_memory_service as _ems,
    )

    _app.dependency_overrides.pop(_get_current_user, None)
    base = server_env["base_url"]

    owner = _register_and_create_deck(page, base)
    _ems._memories.clear()  # noqa: SLF001
    seed = _seed_p13_analytics(owner["user_id"], owner["lesson_id"])

    console_log: list[str] = []
    page.on("pageerror", lambda exc: console_log.append(f"pageerror: {exc}"))

    _sign_in(page, base, owner["email"], owner["password"])
    page.goto(f"{base}/frontend/dashboard.html")
    page.wait_for_load_state("domcontentloaded")

    # Your Trajectory: three bars at 40/65/90, oldest -> newest.
    page.wait_for_selector("#analyticsTrendBody .trend-bar", timeout=20_000)
    assert page.locator("#analyticsTrendBody .trend-bar").count() == 3, (
        f"expected 3 trajectory bars console={console_log!r}"
    )
    trend_text = page.locator("#analyticsTrendBody").inner_text()
    assert "40%" in trend_text, trend_text
    assert "65%" in trend_text, trend_text
    assert "90%" in trend_text, trend_text

    # Focus callout from /overview deep-links to the practice lesson.
    page.wait_for_selector("#analyticsFocus a.lesson-tutor", timeout=20_000)
    focus_text = page.locator("#analyticsFocus").inner_text()
    assert "Gaussian Foundations" in focus_text, focus_text
    focus_link = page.locator("#analyticsFocus a.lesson-tutor").first
    assert "player.html?lesson=" in (focus_link.get_attribute("href") or ""), focus_text

    # Concepts at a Glance: weak first with up-arrow + Practice/Ask-tutor links.
    page.wait_for_selector("#analyticsConceptsBody .concept", timeout=20_000)
    assert page.locator("#analyticsConceptsBody .concept").count() == 2, (
        f"expected 2 concept rows console={console_log!r}"
    )
    first_row = page.locator("#analyticsConceptsBody .concept").first.inner_text()
    assert "weak" in first_row, first_row
    assert "\u25b2" in first_row, f"improving concept must show the up-arrow: {first_row!r}"
    practice = page.locator("#analyticsConceptsBody .concept").first.locator(
        'a[href*="player.html?lesson="]'
    ).first
    practice.wait_for(state="visible", timeout=10_000)
    assert seed["lesson_public_id"] in (practice.get_attribute("href") or "")
    tutor = page.locator("#analyticsConceptsBody .concept").first.locator(
        'a[href*="tutor.html?concept="]'
    ).first
    assert seed["weak_id"] in (tutor.get_attribute("href") or "")
    second_row = page.locator("#analyticsConceptsBody .concept").nth(1).inner_text()
    assert "mastered" in second_row, second_row

    # Effort vs Mastery: 3 attempts -> +38 mastery, 13 pts/attempt.
    page.wait_for_selector("#analyticsEffortBody .reco", timeout=20_000)
    effort_text = page.locator("#analyticsEffortBody").inner_text()
    assert "3 attempts" in effort_text, effort_text
    assert "+38 mastery" in effort_text, effort_text
    assert "13 pts/attempt" in effort_text, effort_text

    # No page errors during the whole analytics load.
    assert not console_log, console_log


@pytest.mark.e2e
def test_p13_dashboard_empty_state(server_env, page):
    from app.core.dependencies import get_current_user as _get_current_user
    from app.main import app as _app

    _app.dependency_overrides.pop(_get_current_user, None)
    base = server_env["base_url"]

    owner = _register_and_create_deck(page, base)
    _sign_in(page, base, owner["email"], owner["password"])
    page.goto(f"{base}/frontend/dashboard.html")
    page.wait_for_load_state("domcontentloaded")

    # The panel skeleton also uses .empty, so wait on the FINAL copy (the async
    # analytics fetch must have replaced the "Loading trajectory…" text).
    page.wait_for_function(
        """() => {
            const el = document.querySelector('#analyticsTrendBody');
            return el && el.innerText.includes('No checkpoints yet');
        }""",
        timeout=20_000,
    )
    trend_text = page.locator("#analyticsTrendBody").inner_text()
    assert "No checkpoints yet" in trend_text, trend_text

    page.wait_for_function(
        """() => {
            const el = document.querySelector('#analyticsConceptsBody');
            return el && el.innerText.includes('No concepts tracked yet');
        }""",
        timeout=20_000,
    )
    concepts_text = page.locator("#analyticsConceptsBody").inner_text()
    assert "No concepts tracked yet" in concepts_text, concepts_text


@pytest.mark.e2e
def test_p13_player_dashboard_hub_link(server_env, page):
    from app.core.dependencies import get_current_user as _get_current_user
    from app.main import app as _app

    _app.dependency_overrides.pop(_get_current_user, None)
    base = server_env["base_url"]

    owner = _register_and_create_deck(page, base)
    _sign_in(page, base, owner["email"], owner["password"])

    page.goto(f"{base}/frontend/player.html?lesson={owner['lesson_id']}")
    page.wait_for_load_state("domcontentloaded")

    hub = page.locator('header a.nav-link[href*="dashboard.html"]')
    hub.wait_for(state="visible", timeout=15_000)
    hub.click()
    page.wait_for_url("**/dashboard.html", timeout=20_000)
    assert page.locator("h1").inner_text() == "Learner Dashboard"
