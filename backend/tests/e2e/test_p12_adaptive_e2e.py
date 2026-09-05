"""P12 browser E2E — adaptive assessment inside the real quiz player.

Drives the vanilla SPA in a real browser against a lesson-linked 3-question
checkpoint where every question is tagged to ONE concept whose persisted
mastery is 60 (developing band). That makes the adaptive start deterministic:
target difficulty = intermediate, so question 1 is the intermediate stem even
though it sits at position 2 in the canonical order.

Then the in-attempt divergence is proven through the actual player flow:

    Scenario A  answer correct -> /next returns the advanced question
                (stepping up) and the ADAPTIVE badge rationale updates to the
                "Stepping up after a correct answer." copy.
    Scenario B  answer wrong    -> /next returns the beginner question
                (returning to an easier level) and the badge rationale becomes
                the "Returning to an easier level..." copy.

Learner actions happen through the real UI (``page.goto`` / ``page.click``);
API/DB calls are used only for deterministic seeding and for reading state
back (seed mastery for the developing band, argue linkage).
"""
from __future__ import annotations

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


STEM_BEGINNER = "BEGINNER: Which statement about mean-centering a Gaussian is correct?"
STEM_INTERMEDIATE = "INTERMEDIATE: Which statement best explains the central-limit intuition?"
STEM_ADVANCED = "ADVANCED: Which statement flags a confidence-interval common pitfall?"


def _register_and_create_deck(page, base_url: str) -> dict[str, str]:
    """Register the learner and create a presentation + lesson they own."""
    uid = uuid.uuid4().hex[:8]
    email = f"p12_loop_{uid}@example.com"
    password = "P12Loop1234!"
    name = "P12 Learner"

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
                body: JSON.stringify({ title: 'P12 Deck', topics: ['Gaussian', 'Vectors'] }),
            });
            const presData = await presRes.json();
            const presId = presData.data.id;

            const lessonRes = await fetch(base + '/api/v1/presentations/' + presId + '/lessons', {
                method: 'POST',
                headers: auth,
                body: JSON.stringify({ mode: 'slide', title: 'P12 Loop Lesson' }),
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


def _add_options(session: Session, question_id) -> None:
    from app.models.quiz_content import QuestionOption

    session.add_all(
        [
            QuestionOption(question_id=question_id, position=1, text="Right", is_correct=True),
            QuestionOption(question_id=question_id, position=2, text="Wrong", is_correct=False),
        ]
    )
    session.flush()


def _add_answerkey(session: Session, question_id, right_public_id) -> None:
    from app.models.answer_key import AnswerKey

    session.add(
        AnswerKey(
            question_id=question_id,
            answer_type="multiple_choice",
            correct_option_ids=[right_public_id],
        )
    )


def _seed_p12_quiz(user_id: str, lesson_public_id: str) -> dict[str, str]:
    """Seed a lesson-linked 3-question quiz, all tagged to one concept.

    The three questions differ ONLY in difficulty (beginner/intermediate/
    advanced) and share a single concept whose seeded mastery is 60.0 — the
    developing band — so a fresh adaptive attempt must open with the
    intermediate question regardless of canonical position (2).
    """
    from app.models.answer_key import AnswerKey
    from app.models.concept import Concept
    from app.models.educational_memory import EducationalMemoryRecord
    from app.models.generated_block import GeneratedBlock
    from app.models.generated_lesson import GeneratedLesson
    from app.models.generated_lesson_version import GeneratedLessonVersion
    from app.models.quiz import Quiz
    from app.models.quiz_content import Question, QuestionOption
    from app.models.quiz_version import QuizVersion

    sync_engine = create_engine(f"sqlite:///{TEST_DB_PATH.as_posix()}", connect_args={"timeout": 30})
    concept_id = f"concept_{uuid.uuid4().hex[:12]}"
    run_name = f"Adaptive Band {uuid.uuid4().hex[:6]}"
    out: dict[str, str] = {
        "concept_id": concept_id,
        "stem_beginner": STEM_BEGINNER,
        "stem_intermediate": STEM_INTERMEDIATE,
        "stem_advanced": STEM_ADVANCED,
    }

    questions: list[tuple[int, str, str]] = [
        (1, STEM_BEGINNER, "beginner"),
        (2, STEM_INTERMEDIATE, "intermediate"),
        (3, STEM_ADVANCED, "advanced"),
    ]

    with Session(sync_engine) as s:
        lesson = s.execute(
            select(GeneratedLesson).where(GeneratedLesson.public_id == lesson_public_id)
        ).scalar_one()

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
        for pos, heading in enumerate(["Adaptive: Core Model", "Adaptive: Applications"]):
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

        concept = Concept(
            public_id=concept_id,
            name=run_name,
            description="A single concept assessed across three difficulties.",
            presentation_id=lesson.presentation_id,
            lesson_id=lesson.id,
            difficulty_level="intermediate",
        )
        s.add(concept)
        s.flush()

        quiz = Quiz(
            presentation_id=lesson.presentation_id,
            lesson_id=lesson.id,
            user_id=lesson.user_id,
            status="published",
            mode="practice",
            title="Checkpoint: Adaptive Band",
            question_count=3,
            max_attempts_per_user=3,
            passing_score=50.0,
            show_feedback_after=True,
            latest_version=1,
            published_version=1,
        )
        s.add(quiz)
        s.flush()
        out["quiz_id"] = quiz.public_id

        version = QuizVersion(quiz_id=quiz.id, version=1, status="published", title="v1")
        s.add(version)
        s.flush()

        for position, stem, difficulty in questions:
            q = Question(
                quiz_version_id=version.id,
                position=position,
                question_type="multiple_choice",
                stem=stem,
                points=1,
                bloom_level="remember",
                difficulty=difficulty,
                concept_id=concept.id,
            )
            s.add(q)
            s.flush()
            _add_options(s, q.id)
            right = s.execute(
                select(QuestionOption).where(
                    QuestionOption.question_id == q.id,
                    QuestionOption.position == 1,
                )
            ).scalar_one()
            _add_answerkey(s, q.id, right.public_id)

        # Memory for the concept at 60.0 -> developing band -> intermediate target.
        memory = build_memory_json(user_id)
        now = time.time()
        records = {str(k): dict(v) for k, v in memory["concept_records"].items()}
        records[concept_id] = dict(records.pop("concept_gauss"))
        records[concept_id]["concept_id"] = concept_id
        records[concept_id]["concept_name"] = run_name
        records[concept_id]["mastery_score"] = 60.0
        records[concept_id]["first_learned_at"] = now - 3600
        records[concept_id]["last_reviewed_at"] = now - 7200
        memory["weak_concepts"] = []
        memory["developing_concepts"] = [concept_id]
        memory["mastered_concepts"] = []
        memory["concept_records"] = records
        s.add(EducationalMemoryRecord(user_id=uuid.UUID(user_id), memory_data=memory))

        s.commit()

    return out


def _read_memory_concept(user_id: str, concept_id: str) -> float | None:
    """Read back the persisted mastery for a concept (verification only)."""
    from app.models.educational_memory import EducationalMemoryRecord

    sync_engine = create_engine(f"sqlite:///{TEST_DB_PATH.as_posix()}", connect_args={"timeout": 30})
    with Session(sync_engine) as s:
        rec = s.execute(
            select(EducationalMemoryRecord).where(
                EducationalMemoryRecord.user_id == uuid.UUID(user_id)
            )
        ).scalar_one_or_none()
        if rec is None:
            return None
        concept_records = (rec.memory_data or {}).get("concept_records", {})
        entry = concept_records.get(concept_id)
        return float(entry["mastery_score"]) if entry and entry.get("mastery_score") is not None else None


def _sign_in(page, base_url: str, email: str, password: str) -> None:
    page.goto(f"{base_url}/frontend/signin.html")
    page.wait_for_load_state("domcontentloaded")
    page.fill("#email", email)
    page.fill("#password", password)
    page.click("#submitBtn")
    page.wait_for_url("**/upload.html", timeout=20_000)
    page.wait_for_load_state("domcontentloaded")


def _open_quiz(page, base_url: str, owner: dict[str, str]) -> None:
    page.goto(
        f"{base_url}/frontend/player.html?lesson={owner['lesson_id']}&deck={owner['presentation_id']}"
    )
    page.wait_for_load_state("domcontentloaded")
    panel = page.locator("#ljPanel")
    panel.wait_for(state="visible", timeout=20_000)
    take_btn = panel.locator("button.lj-take")
    take_btn.wait_for(state="visible", timeout=15_000)
    take_btn.click()
    overlay = page.locator("#quizOverlay")
    overlay.wait_for(state="visible", timeout=15_000)


def _wait_for_stem(page, expected: str, console_log: list[str], timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if page.locator(".quiz-qstem").inner_text().strip() == expected:
                return
        except Exception:
            pass
        time.sleep(0.4)
    raise AssertionError(
        f"expected stem never appeared: {expected!r} "
        f"actual={page.locator('.quiz-qstem').inner_text()!r} console={console_log!r}"
    )


@pytest.mark.e2e
def test_p12_adaptive_browser_correct_steps_up(server_env, page):
    from app.core.dependencies import get_current_user as _get_current_user
    from app.main import app as _app

    _app.dependency_overrides.pop(_get_current_user, None)
    base = server_env["base_url"]

    owner = _register_and_create_deck(page, base)

    from app.services.educational_memory_service import (
        educational_memory_service as _ems,
    )

    _ems._memories.clear()  # noqa: SLF001
    seed = _seed_p12_quiz(owner["user_id"], owner["lesson_id"])
    assert _read_memory_concept(owner["user_id"], seed["concept_id"]) == 60.0

    console_log: list[str] = []
    page.on("pageerror", lambda exc: console_log.append(f"pageerror: {exc}"))

    _sign_in(page, base, owner["email"], owner["password"])
    _open_quiz(page, base, owner)

    # Adaptive start: developing band (60) -> intermediate target, even though
    # the intermediate question is at canonical position 2.
    assert page.locator(".quiz-qstem").inner_text().strip() == seed["stem_intermediate"]
    quiz_sub = page.locator(".quiz-sub").inner_text()
    assert "ADAPTIVE" in quiz_sub, "adaptive delivery must surface the ADAPTIVE badge"

    # Scenario A: answer correctly -> /next steps up to advanced.
    page.locator(".quiz-opt", has_text="Right").first.click()
    page.locator('.quiz-foot button', has_text="Next").first.click()
    _wait_for_stem(page, seed["stem_advanced"], console_log)

    rationale_span = page.locator("#quizOverlay .quiz-sub span[title]").first
    rationale_span.wait_for(state="visible", timeout=5_000)
    title = rationale_span.get_attribute("title") or ""
    assert "Stepping up after a correct answer." in title, (
        f"after a correct answer the rationale must step up; got {title!r} "
        f"console={console_log!r}"
    )


@pytest.mark.e2e
def test_p12_adaptive_browser_incorrect_steps_down(server_env, page):
    from app.core.dependencies import get_current_user as _get_current_user
    from app.main import app as _app

    _app.dependency_overrides.pop(_get_current_user, None)
    base = server_env["base_url"]

    owner = _register_and_create_deck(page, base)

    from app.services.educational_memory_service import (
        educational_memory_service as _ems,
    )

    _ems._memories.clear()  # noqa: SLF001
    seed = _seed_p12_quiz(owner["user_id"], owner["lesson_id"])
    assert _read_memory_concept(owner["user_id"], seed["concept_id"]) == 60.0

    console_log: list[str] = []
    page.on("pageerror", lambda exc: console_log.append(f"pageerror: {exc}"))

    _sign_in(page, base, owner["email"], owner["password"])
    _open_quiz(page, base, owner)

    assert page.locator(".quiz-qstem").inner_text().strip() == seed["stem_intermediate"]

    # Scenario B: answer wrong -> /next returns to an easier (beginner) level.
    page.locator(".quiz-opt", has_text="Wrong").first.click()
    page.locator('.quiz-foot button', has_text="Next").first.click()
    _wait_for_stem(page, seed["stem_beginner"], console_log)

    rationale_span = page.locator("#quizOverlay .quiz-sub span[title]").first
    rationale_span.wait_for(state="visible", timeout=5_000)
    title = rationale_span.get_attribute("title") or ""
    assert "Returning to an easier level" in title, (
        f"after an incorrect answer the rationale must step down; got {title!r} "
        f"console={console_log!r}"
    )
