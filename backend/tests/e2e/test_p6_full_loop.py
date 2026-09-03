"""P6 browser E2E — complete interactive assessment learner loop (C5).

Drives the real vanilla SPA player through the full closed loop:

    sign in → open lesson → learner journey panel shows checkpoint
    → click "Take Checkpoint" → quiz overlay renders questions/options
    → select answers → navigate questions → submit
    → result (score + pass/fail) → mastery refresh in the panel
    → next action reflects new state → leave & reopen → resume

All learner actions happen through the actual browser UI
(``page.goto`` / ``page.click`` / ``page.fill``). API/DB calls are used
only for deterministic test-data seeding and supplemental assertions.

The lesson-linked quiz is seeded directly into the shared test database
(no external AI, no mocked 200s) so the checkpoint returns a real quiz.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Playwright launch config (same as existing P5 E2E)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Deterministic test setup (API for user/deck/lesson, DB for lesson quiz)
# ---------------------------------------------------------------------------


def _seed_lesson_quiz(lesson_public_id: str) -> None:
    """Create a deterministic lesson-linked quiz in the shared test DB.

    The quiz is bound to the given GeneratedLesson via ``lesson_id`` and its
    parent presentation, so ``/player/checkpoint`` exposes it without any AI
    generation. Two multiple-choice questions, each correct at option B.
    """
    from app.models.answer_key import AnswerKey
    from app.models.generated_block import GeneratedBlock
    from app.models.generated_lesson import GeneratedLesson
    from app.models.generated_lesson_version import GeneratedLessonVersion
    from app.models.quiz import Quiz
    from app.models.quiz_content import Question, QuestionOption
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

        # Successful lesson version + blocks so the player renders slides and
        # the learner journey panel (no AI generation is ever invoked).
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

        quiz = Quiz(
            presentation_id=lesson.presentation_id,
            lesson_id=lesson.id,
            user_id=lesson.user_id,
            status="published",
            mode="practice",
            title="Checkpoint: Core Concepts",
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

        for i, stem in enumerate(
            ["What is 2 + 2?", "Which planet is third from the Sun?"], start=1
        ):
            q = Question(
                quiz_version_id=version.id,
                position=i,
                question_type="multiple_choice",
                stem=stem,
                points=1,
                bloom_level="remember",
                difficulty="beginner",
            )
            s.add(q)
            s.flush()
            opt_a = QuestionOption(
                question_id=q.id, position=1, text="Option A", is_correct=False
            )
            opt_b = QuestionOption(
                question_id=q.id, position=2, text="Option B", is_correct=True
            )
            opt_c = QuestionOption(
                question_id=q.id, position=3, text="Option C", is_correct=False
            )
            s.add_all([opt_a, opt_b, opt_c])
            s.flush()
            s.add(
                AnswerKey(
                    question_id=q.id,
                    answer_type="multiple_choice",
                    correct_option_ids=[opt_b.public_id],
                )
            )

        s.commit()


def _create_owner_lesson(page, base_url: str) -> dict[str, str]:
    """Register the learner and create a presentation + lesson they own."""
    uid = uuid.uuid4().hex[:8]
    email = f"p6_loop_{uid}@example.com"
    password = "LoopPass1234!"
    name = "P6 Learner"

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
                body: JSON.stringify({ title: 'P6 Loop Deck', topics: ['Alpha', 'Beta'] }),
            });
            const presData = await presRes.json();
            const presId = presData.data.id;

            const lessonRes = await fetch(base + '/api/v1/presentations/' + presId + '/lessons', {
                method: 'POST',
                headers: auth,
                body: JSON.stringify({ mode: 'slide', title: 'P6 Loop Lesson' }),
            });
            const lessonData = await lessonRes.json();
            return { lessonId: lessonData.data.id, presId: presId };
        }""",
        [base_url, email, password, name],
    )

    return {
        "email": email,
        "password": password,
        "name": name,
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


# ---------------------------------------------------------------------------
# Full learner loop
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_full_learner_loop(server_env, page):
    base = server_env["base_url"]
    owner = _create_owner_lesson(page, base)
    _seed_lesson_quiz(owner["lesson_id"])

    # STEP 1 — sign in through the real form.
    page.goto(f"{base}/frontend/signin.html")
    page.wait_for_load_state("domcontentloaded")
    page.fill("#email", owner["email"])
    page.fill("#password", owner["password"])
    page.click("#submitBtn")
    page.wait_for_url("**/upload.html", timeout=20_000)
    page.wait_for_load_state("domcontentloaded")

    # STEP 2 — open the player lesson.
    page.goto(
        f"{base}/frontend/player.html?lesson={owner['lesson_id']}&deck={owner['presentation_id']}"
    )
    page.wait_for_load_state("domcontentloaded")

    # STEP 3/4 — learner journey panel appears with a Take Checkpoint button.
    panel = page.locator("#ljPanel")
    panel.wait_for(state="visible", timeout=20_000)
    assert "learner progress" in panel.inner_text().lower()
    assert "Assessment" in panel.inner_text()

    take_btn = panel.locator("button.lj-take")
    take_btn.wait_for(state="visible", timeout=15_000)
    assert "Checkpoint" in take_btn.inner_text()

    # STEP 5 — open the quiz overlay; wait for the first question to render.
    take_btn.click()
    overlay = page.locator("#quizOverlay")
    overlay.wait_for(state="visible", timeout=15_000)
    qstem = overlay.locator(".quiz-qstem")
    qstem.filter(has_text="What is 2 + 2?").wait_for(state="visible", timeout=20_000)

    # Question 1 renders with options.
    q1_opts = overlay.locator(".quiz-opt")
    assert q1_opts.count() >= 2

    # STEP 6 — select the correct answer (option B) for Q1.
    q1_opt_b = overlay.locator(".quiz-opt", has_text="Option B").first
    q1_opt_b.click()

    # STEP 7 — navigate forward to Q2; answer persists.
    overlay.locator("button", has_text="Next").click()
    qstem.filter(has_text="Which planet is third from the Sun?").wait_for(
        state="visible", timeout=10_000
    )
    q2_opt_b = overlay.locator(".quiz-opt", has_text="Option B").first
    q2_opt_b.click()

    # STEP 7b — navigate back to Q1, verify the selection persisted, return.
    overlay.locator("button", has_text="Previous").click()
    qstem.filter(has_text="What is 2 + 2?").wait_for(state="visible", timeout=10_000)
    selected = overlay.locator(".quiz-opt.selected")
    assert selected.count() >= 1
    overlay.locator("button", has_text="Next").click()

    # STEP 8 — submit the quiz.
    overlay.locator("button", has_text="Submit Quiz").click()

    # STEP 9 — result display: 100% and passed.
    ring = overlay.locator(".quiz-score-ring")
    ring.wait_for(state="visible", timeout=20_000)
    assert "100" in ring.inner_text()
    assert "Checkpoint passed" in overlay.inner_text()

    # STEP 10/11 — close results and confirm the panel refreshed (passed +
    # next action tied to learner state).
    overlay.locator("button", has_text="Back to Lesson").click()
    overlay.wait_for(state="hidden", timeout=10_000)
    panel_text = panel.inner_text()
    assert "Checkpoint passed" in panel_text
    assert "Next up" in panel_text

    # STEP 12 — leave and reopen; progress + completed attempt persist.
    page.goto(f"{base}/frontend/upload.html")
    page.wait_for_load_state("domcontentloaded")
    page.goto(
        f"{base}/frontend/player.html?lesson={owner['lesson_id']}&deck={owner['presentation_id']}"
    )
    page.wait_for_load_state("domcontentloaded")
    panel2 = page.locator("#ljPanel")
    panel2.wait_for(state="visible", timeout=20_000)
    assert "Checkpoint passed" in panel2.inner_text()
