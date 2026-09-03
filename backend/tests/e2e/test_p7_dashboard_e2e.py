"""P7 browser E2E — learner progress dashboard (C5).

Drives the real vanilla SPA dashboard through the browser:

    sign in → open dashboard → summary stats render
    → next-best-action recommendations appear
    → weak / mastered concepts listed
    → recent checkpoint attempt + performance trend render
    → lesson progress entry is shown and navigates back to the player

Learner actions happen through the actual UI (``page.goto`` / ``page.click``).
API/DB calls are used only for deterministic test-data seeding. The completed
lesson session, quiz attempt and educational-memory (weak + mastered concepts)
are seeded directly into the shared test database, so the aggregate endpoint
returns real, learner-scoped data — no mocked 200s, no AI.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from tests.learner_progress_helpers import build_memory_json


@pytest.fixture(scope="session")
def browser_context_args():
    return {
        "viewport": {"width": 1280, "height": 800},
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


def _seed_dashboard_data(lesson_public_id: str, user_id: str) -> None:
    """Seed a completed session, quiz attempt and mastery into the test DB.

    Synchronous SQLAlchemy over the shared SQLite test file (``asyncio.run``
    fails under ``asyncio_mode = "auto"``). The rows are learner-scoped to the
    given ``user_id`` and are read by the running server over the same SQLite
    file, so the aggregate endpoint returns real, learner-scoped data.
    """
    from app.models.educational_memory import EducationalMemoryRecord
    from app.models.generated_block import GeneratedBlock
    from app.models.generated_lesson import GeneratedLesson
    from app.models.generated_lesson_version import GeneratedLessonVersion
    from app.models.learning_session import LearningSession
    from app.models.quiz import Quiz
    from app.models.quiz_attempt import QuizAttempt
    from app.models.quiz_version import QuizVersion
    from tests.conftest import TEST_DB_PATH

    sync_engine = create_engine(
        f"sqlite:///{TEST_DB_PATH.as_posix()}",
        connect_args={"timeout": 30},
    )
    with Session(sync_engine) as s:
        lesson = s.execute(
            select(GeneratedLesson).where(
                GeneratedLesson.public_id == lesson_public_id
            )
        ).scalar_one()

        # Make the lesson renderable (version + blocks) and "ready".
        lv = GeneratedLessonVersion(
            lesson_id=lesson.id,
            version=1,
            status="succeeded",
            title=lesson.title,
            language="en",
            difficulty="beginner",
        )
        s.add(lv)
        s.flush()
        for pos, heading in enumerate(
            ["Alpha: Core Foundations", "Beta: Applications"]
        ):
            s.add(
                GeneratedBlock(
                    lesson_version_id=lv.id,
                    block_type="paragraph",
                    position=pos,
                    heading=heading,
                    content=f"Body for {heading}.",
                )
            )
        lesson.status = "ready"
        lesson.latest_version = 1
        s.flush()

        # A completed learning session → lesson progress on the dashboard.
        s.add(
            LearningSession(
                user_id=uuid.UUID(user_id),
                lesson_id=lesson.id,
                status="completed",
                completion_percentage=100.0,
                total_time_seconds=600,
                current_slide_position=0,
                current_block_position=0,
                resume_version=0,
            )
        )
        s.flush()

        # A published quiz + one completed attempt (85% → passed vs 50% pass).
        quiz = Quiz(
            presentation_id=lesson.presentation_id,
            lesson_id=lesson.id,
            user_id=uuid.UUID(user_id),
            status="published",
            mode="practice",
            title="P7 Dashboard Checkpoint",
            question_count=2,
            max_attempts_per_user=3,
            passing_score=50.0,
            show_feedback_after=True,
            latest_version=1,
            published_version=1,
        )
        s.add(quiz)
        s.flush()
        version = QuizVersion(
            quiz_id=quiz.id, version=1, status="published", title="v1"
        )
        s.add(version)
        s.flush()
        s.add(
            QuizAttempt(
                quiz_id=quiz.id,
                quiz_version_id=version.id,
                user_id=uuid.UUID(user_id),
                attempt_number=1,
                status="completed",
                score=0.85,
                max_score=1.0,
                percent_score=85.0,
                time_spent_seconds=300,
                is_practice=False,
            )
        )
        s.flush()

        # Mastery: one weak + one mastered concept → recommendations, weak and
        # strong concept lists.
        s.add(
            EducationalMemoryRecord(
                user_id=uuid.UUID(user_id),
                memory_data=build_memory_json(user_id),
            )
        )
        s.commit()


def _register_and_create_deck(page, base_url: str) -> dict[str, str]:
    """Register the learner and create a presentation + lesson they own."""
    uid = uuid.uuid4().hex[:8]
    email = f"p7_dash_{uid}@example.com"
    password = "DashPass1234!"
    name = "P7 Dashboard Learner"

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
                body: JSON.stringify({ title: 'P7 Dashboard Deck', topics: ['Alpha', 'Beta'] }),
            });
            const presData = await presRes.json();
            const presId = presData.data.id;

            const lessonRes = await fetch(base + '/api/v1/presentations/' + presId + '/lessons', {
                method: 'POST',
                headers: auth,
                body: JSON.stringify({ mode: 'slide', title: 'P7 Dashboard Lesson' }),
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


def _sign_in(page, base_url: str, email: str, password: str) -> None:
    page.goto(f"{base_url}/frontend/signin.html")
    page.wait_for_load_state("domcontentloaded")
    page.fill("#email", email)
    page.fill("#password", password)
    page.click("#submitBtn")
    page.wait_for_url("**/upload.html", timeout=20_000)
    page.wait_for_load_state("domcontentloaded")


@pytest.mark.e2e
def test_learner_dashboard_e2e(server_env, page):
    # Use real JWT auth for real, learner-scoped dashboard aggregation. The
    # root conftest's autouse ``_override_get_current_user`` would otherwise
    # resolve the authenticated user to the shared TEST_USER_ID, defeating the
    # cross-lesson/multi-user isolation the dashboard is meant to demonstrate.
    from app.core.dependencies import get_current_user as _get_current_user
    from app.main import app as _app

    _app.dependency_overrides.pop(_get_current_user, None)

    base = server_env["base_url"]
    learner = _register_and_create_deck(page, base)
    _seed_dashboard_data(learner["lesson_id"], learner["user_id"])

    # Ensure mastery reads the DB-seeded memory, not a stale in-memory value.
    from app.services.educational_memory_service import (
        educational_memory_service as _ems,
    )

    _ems._memories.clear()  # noqa: SLF001

    # STEP 1 — sign in through the real form.
    page.goto(f"{base}/frontend/signin.html")
    page.wait_for_load_state("domcontentloaded")
    page.fill("#email", learner["email"])
    page.fill("#password", learner["password"])
    page.click("#submitBtn")
    page.wait_for_url("**/upload.html", timeout=20_000)
    page.wait_for_load_state("domcontentloaded")

    # STEP 2 — open the learner dashboard.
    page.goto(f"{base}/frontend/dashboard.html")
    page.wait_for_load_state("domcontentloaded")

    content = page.locator("#content")
    content.wait_for(state="visible", timeout=20_000)

    # STEP 3 — summary stat for checkpoints taken = 1 (attempts_total).
    page.wait_for_selector(".stat", timeout=20_000)
    stats = content.locator(".stat")
    stat_texts = []
    for i in range(stats.count()):
        el = stats.nth(i)
        stat_texts.append((el.locator(".stat-label").inner_text(), el.locator(".stat-value").inner_text()))
    assert any(
        label.lower() == "checkpoints taken" and value.strip() == "1"
        for label, value in stat_texts
    ), f"Checkpoints Taken stat missing: {stat_texts}"

    # STEP 4 — recommendation summary callout appears (weak concept present).
    reco_sum = content.locator(".reco-summary")
    reco_sum.wait_for(state="visible", timeout=15_000)
    assert "needing review" in reco_sum.inner_text().lower()

    # STEP 5 — at least one prioritized next action renders.
    reco = content.locator(".reco").first
    reco.wait_for(state="visible", timeout=15_000)
    assert reco.locator(".reco-title").inner_text().strip()

    # STEP 6 — weak + mastered concept chips are listed.
    weak_concept = content.locator(".concept:has(.chip.weak)").first
    weak_concept.wait_for(state="visible", timeout=15_000)
    assert "Gaussian Distributions" in weak_concept.locator(".concept-name").inner_text()
    mastered_concept = content.locator(".concept:has(.chip.mastered)").first
    mastered_concept.wait_for(state="visible", timeout=15_000)

    # STEP 7 — recent checkpoint attempt renders.
    attempt = content.locator(".attempt").first
    attempt.wait_for(state="visible", timeout=15_000)
    assert "P7 Dashboard Checkpoint" in attempt.inner_text()
    assert "85%" in attempt.inner_text()

    # STEP 8 — trend renders at least one bar.
    content.locator(".trend").wait_for(state="visible", timeout=15_000)
    assert content.locator(".trend-col").count() >= 1

    # STEP 9 — lesson progress entry is visible and navigates to the player.
    lesson_row = content.locator(".lesson", has_text="P7 Dashboard Lesson").first
    lesson_row.wait_for(state="visible", timeout=15_000)
    assert "100%" in lesson_row.inner_text()
    lesson_row.click()
    page.wait_for_url("**/frontend/player.html?lesson=*", timeout=20_000)
    page.wait_for_load_state("domcontentloaded")
