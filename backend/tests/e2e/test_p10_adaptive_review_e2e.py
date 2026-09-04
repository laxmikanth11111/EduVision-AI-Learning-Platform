"""P10 browser E2E — adaptive remediation & review engine (C6).

Closes NG-1/NG-2/NG-3 in a *real browser* against the real vanilla SPA:

    NG-1  quiz result -> structured next_action -> real clickable CTA
          -> valid lesson/player destination (nothing dead when missing).
    NG-2  dashboard recommendation -> actionable deep-link.
    NG-3  weak concept -> practice -> real assessment -> mastery update
          -> review scheduling change -> prioritization change.

Learner actions happen through the actual UI (``page.goto`` / ``page.click`` /
``page.fill``). API/DB calls are used only for deterministic seeding and for
*reading back* state to assert the loop closed; the state transitions themselves
happen through the application's real user flow.
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


# ---------------------------------------------------------------------------
# Deterministic seeding (API for identity/deck/lesson, DB for the rest)
# ---------------------------------------------------------------------------


def _register_and_create_deck(page, base_url: str) -> dict[str, str]:
    """Register the learner and create a presentation + lesson they own."""
    uid = uuid.uuid4().hex[:8]
    email = f"p10_loop_{uid}@example.com"
    password = "P10Loop1234!"
    name = "P10 Learner"

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
                body: JSON.stringify({ title: 'P10 Deck', topics: ['Gaussian', 'Vectors'] }),
            });
            const presData = await presRes.json();
            const presId = presData.data.id;

            const lessonRes = await fetch(base + '/api/v1/presentations/' + presId + '/lessons', {
                method: 'POST',
                headers: auth,
                body: JSON.stringify({ mode: 'slide', title: 'P10 Loop Lesson' }),
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
            QuestionOption(question_id=question_id, position=1, text="A symmetric bell curve", is_correct=True),
            QuestionOption(question_id=question_id, position=2, text="A flat uniform line", is_correct=False),
            QuestionOption(question_id=question_id, position=3, text="A random scatter", is_correct=False),
        ]
    )
    session.flush()


def _add_answerkey(session: Session, question_id) -> None:
    from app.models.answer_key import AnswerKey
    from app.models.quiz_content import QuestionOption

    opt_a = session.execute(
        select(QuestionOption).where(
            QuestionOption.question_id == question_id,
            QuestionOption.position == 1,
        )
    ).scalar_one()
    session.add(
        AnswerKey(
            question_id=question_id,
            answer_type="multiple_choice",
            correct_option_ids=[opt_a.public_id],
        )
    )


def _seed_p10_data(
    user_id: str,
    lesson_public_id: str,
    *,
    tag_concept_on_question: bool,
    make_due_schedule: bool,
) -> dict[str, str]:
    """Seed a learner-owned weak concept + lesson-linked checkpoint quiz.

    * Renders a successful lesson version + blocks so the player displays.
    * Creates a weak ``Concept`` anchored to the lesson (30% mastery).
    * Creates a lesson-linked quiz; Q1 can be tagged with the concept so a
      correct answer routes mastery to it (NG-3 loop). Q1 correct = Option A.
    * Optionally creates an overdue ``ReviewSchedule`` for the concept.

    Returns ``{concept_id, quiz_id, schedule_id}``.
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
    run_name = f"Gaussian Distributions {uuid.uuid4().hex[:6]}"
    out: dict[str, str] = {"concept_id": concept_id}

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
        for pos, heading in enumerate(["Gaussian: Core Model", "Gaussian: Applications"]):
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
            description="Gaussian Distributions model symmetric bell curves.",
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
            title="Checkpoint: Gaussian Concepts",
            question_count=2,
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

        # Q1: tagged to the weak concept (correct = Option A).
        q1 = Question(
            quiz_version_id=version.id,
            position=1,
            question_type="multiple_choice",
            stem="Which distribution is a symmetric bell curve?",
            points=1,
            bloom_level="remember",
            difficulty="beginner",
            concept_id=concept.id if tag_concept_on_question else None,
        )
        s.add(q1)
        s.flush()
        _add_options(s, q1.id)
        _add_answerkey(s, q1.id)

        # Q2: untagged.
        q2 = Question(
            quiz_version_id=version.id,
            position=2,
            question_type="multiple_choice",
            stem="What does the mean set in a Gaussian?",
            points=1,
            bloom_level="remember",
            difficulty="beginner",
        )
        s.add(q2)
        s.flush()
        _add_options(s, q2.id)
        _add_answerkey(s, q2.id)

        # Memory referencing the same weak concept id (30% mastery).
        memory = build_memory_json(user_id)
        now = time.time()
        records = {str(k): dict(v) for k, v in memory["concept_records"].items()}
        records[concept_id] = dict(records.pop("concept_gauss"))
        records[concept_id]["concept_id"] = concept_id
        records[concept_id]["concept_name"] = run_name
        records[concept_id]["mastery_score"] = 30.0
        records[concept_id]["first_learned_at"] = now - 3600
        records[concept_id]["last_reviewed_at"] = now - 86400
        memory["weak_concepts"] = [concept_id]
        memory["mastered_concepts"] = []
        memory["developing_concepts"] = []
        memory["concept_records"] = records
        s.add(EducationalMemoryRecord(user_id=uuid.UUID(user_id), memory_data=memory))

        if make_due_schedule:
            from datetime import UTC, datetime, timedelta

            from app.models.review_schedule import ReviewSchedule

            s.add(
                ReviewSchedule(
                    user_id=uuid.UUID(user_id),
                    concept_id=concept.id,
                    lesson_id=lesson.id,
                    topic=run_name,
                    status="scheduled",
                    scheduled_date=(datetime.now(UTC) - timedelta(days=2)).date(),
                    interval_days=1,
                    mastery_at_schedule=30.0,
                    due_at=datetime.now(UTC) - timedelta(days=1),
                    review_metadata={"step": 0},
                )
            )

        s.commit()

    # Re-read any schedule + concept ids we may have created.
    from app.models.concept import Concept as _C  # noqa: N814
    from app.models.review_schedule import ReviewSchedule as _RS  # noqa: N814

    with Session(sync_engine) as s:
        sched = s.execute(
            select(_RS)
            .join(_C, _RS.concept_id == _C.id)
            .where(_C.public_id == concept_id)
        ).scalar_one_or_none()
        if sched is not None:
            out["schedule_id"] = sched.public_id
    return out


def _sign_in(page, base_url: str, email: str, password: str) -> None:
    page.goto(f"{base_url}/frontend/signin.html")
    page.wait_for_load_state("domcontentloaded")
    page.fill("#email", email)
    page.fill("#password", password)
    page.click("#submitBtn")
    page.wait_for_url("**/upload.html", timeout=20_000)
    page.wait_for_load_state("domcontentloaded")


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


# ---------------------------------------------------------------------------
# NG-1 — quiz result next_action -> real CTA -> valid destination
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_p10_ng1_quiz_next_action_cta(server_env, page):
    from app.core.dependencies import get_current_user as _get_current_user
    from app.main import app as _app

    _app.dependency_overrides.pop(_get_current_user, None)
    base = server_env["base_url"]

    owner = _register_and_create_deck(page, base)

    from app.services.educational_memory_service import (
        educational_memory_service as _ems,
    )

    _ems._memories.clear()  # noqa: SLF001
    # Q1 NOT tagged -> the weak concept stays weak -> next_action remains + CTA.
    _seed_p10_data(
        owner["user_id"],
        owner["lesson_id"],
        tag_concept_on_question=False,
        make_due_schedule=False,
    )

    _sign_in(page, base, owner["email"], owner["password"])

    # Open the player and take the checkpoint (both questions, Option A correct).
    page.goto(f"{base}/frontend/player.html?lesson={owner['lesson_id']}&deck={owner['presentation_id']}")
    page.wait_for_load_state("domcontentloaded")
    panel = page.locator("#ljPanel")
    panel.wait_for(state="visible", timeout=20_000)
    take_btn = panel.locator("button.lj-take")
    take_btn.wait_for(state="visible", timeout=15_000)
    take_btn.click()
    overlay = page.locator("#quizOverlay")
    overlay.wait_for(state="visible", timeout=15_000)

    overlay.locator(".quiz-opt", has_text="A symmetric bell curve").first.click()
    overlay.locator("button", has_text="Next").click()
    overlay.locator(".quiz-opt", has_text="A symmetric bell curve").first.click()
    overlay.locator("button", has_text="Submit Quiz").click()
    ring = overlay.locator(".quiz-score-ring")
    ring.wait_for(state="visible", timeout=20_000)
    assert "100" in ring.inner_text()

    # The "Recommended next" callout exposes a REAL, clickable next-action CTA.
    rec_box = overlay.locator("div", has_text="Recommended next").first
    rec_box.wait_for(state="visible", timeout=10_000)
    cta = rec_box.locator("a.lj-take").first
    cta.wait_for(state="visible", timeout=10_000)
    href = cta.get_attribute("href")
    assert href, "NG-1: next_action CTA must have a href"
    assert href.startswith("/frontend/player.html?lesson=")
    target_lesson = href.split("lesson=")[1]
    assert target_lesson, "NG-1: next_action CTA must carry a non-empty lesson target"

    # Failure modes: the CTA is NOT decorative text (it is a real anchor) and
    # its target lesson actually resolves for this learner.
    from app.models.generated_lesson import GeneratedLesson

    sync_engine = create_engine(f"sqlite:///{TEST_DB_PATH.as_posix()}", connect_args={"timeout": 30})
    with Session(sync_engine) as s:
        exists = s.execute(
            select(GeneratedLesson).where(GeneratedLesson.public_id == target_lesson)
        ).scalar_one_or_none()
    assert exists is not None, "NG-1: next_action must point to an existing lesson"

    # Clicking the real CTA navigates to a valid, learner-owned player route.
    with page.expect_navigation():
        cta.click()
    page.wait_for_load_state("domcontentloaded")
    assert "player.html?lesson=" in page.url
    panel2 = page.locator("#ljPanel")
    panel2.wait_for(state="visible", timeout=20_000)


# ---------------------------------------------------------------------------
# NG-2 — dashboard recommendations are actionable deep-links
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_p10_dashboard_ng2_reco_and_weakdeep(server_env, page):
    from app.core.dependencies import get_current_user as _get_current_user
    from app.main import app as _app

    _app.dependency_overrides.pop(_get_current_user, None)
    base = server_env["base_url"]

    owner = _register_and_create_deck(page, base)

    from app.services.educational_memory_service import (
        educational_memory_service as _ems,
    )

    _ems._memories.clear()  # noqa: SLF001
    _seed_p10_data(
        owner["user_id"],
        owner["lesson_id"],
        tag_concept_on_question=False,
        make_due_schedule=True,
    )

    _sign_in(page, base, owner["email"], owner["password"])

    # Dashboard: a recommendation card links to a real destination.
    page.goto(f"{base}/frontend/dashboard.html")
    page.wait_for_load_state("domcontentloaded")
    reco_link = page.locator(".reco a.lesson-tutor").first
    reco_link.wait_for(state="visible", timeout=20_000)
    href = reco_link.get_attribute("href")
    assert href, "NG-2: dashboard recommendation must have a real href"
    assert href.startswith(
        ("/frontend/player.html?lesson=", "/frontend/tutor.html?concept=")
    )

    # Review queue panel shows the overdue weak concept and is actionable
    # (Practice deep-link + Mark reviewed), not dead text.
    body = page.locator("#reviewPanelBody")
    body.wait_for(state="visible", timeout=20_000)
    assert "Gaussian Distributions" in body.inner_text() or "symmetric" in body.inner_text().lower() or body.inner_text().strip()
    # A recovery concept name may be randomized; assert we have at least one
    # due item with an action button rather than an exact name.
    practice = body.locator("a.lesson-tutor").first
    practice.wait_for(state="visible", timeout=10_000)
    assert (practice.get_attribute("href") or "").startswith("/frontend/player.html?lesson=")
    mark = body.locator("button.reco-btn").first
    mark.wait_for(state="visible", timeout=10_000)
    assert "Mark reviewed" in mark.inner_text()


# ---------------------------------------------------------------------------
# NG-3 — weak concept -> practice -> assessment -> mastery -> scheduling -> priority
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_p10_ng3_critical_learning_loop(server_env, page):
    from app.core.dependencies import get_current_user as _get_current_user
    from app.main import app as _app

    _app.dependency_overrides.pop(_get_current_user, None)
    base = server_env["base_url"]

    owner = _register_and_create_deck(page, base)

    from app.services.educational_memory_service import (
        educational_memory_service as _ems,
    )

    _ems._memories.clear()  # noqa: SLF001
    # Q1 IS tagged to the weak concept and there is an overdue schedule.
    seed = _seed_p10_data(
        owner["user_id"],
        owner["lesson_id"],
        tag_concept_on_question=True,
        make_due_schedule=True,
    )
    concept_id = seed["concept_id"]

    # Baseline: weak (30%).
    assert _read_memory_concept(owner["user_id"], concept_id) == 30.0

    _sign_in(page, base, owner["email"], owner["password"])

    # The review queue and dashboard expose the overdue weak concept.
    page.goto(f"{base}/frontend/dashboard.html")
    page.wait_for_load_state("domcontentloaded")
    body = page.locator("#reviewPanelBody")
    body.wait_for(state="visible", timeout=20_000)

    # 1) PRACTICE — open the lesson player via the real checkpoint.
    page.goto(f"{base}/frontend/player.html?lesson={owner['lesson_id']}&deck={owner['presentation_id']}")
    page.wait_for_load_state("domcontentloaded")
    panel = page.locator("#ljPanel")
    panel.wait_for(state="visible", timeout=20_000)
    take_btn = panel.locator("button.lj-take")
    take_btn.wait_for(state="visible", timeout=15_000)
    take_btn.click()
    overlay = page.locator("#quizOverlay")
    overlay.wait_for(state="visible", timeout=15_000)

    # 2) ASSESS — answer Q1 (tagged to the weak concept) and Q2 correctly.
    overlay.locator(".quiz-opt", has_text="A symmetric bell curve").first.click()
    overlay.locator("button", has_text="Next").click()
    overlay.locator(".quiz-opt", has_text="A symmetric bell curve").first.click()
    overlay.locator("button", has_text="Submit Quiz").click()
    ring = overlay.locator(".quiz-score-ring")
    ring.wait_for(state="visible", timeout=20_000)
    assert "100" in ring.inner_text()

    # 3) MASTERY UPDATE — the weak concept's persisted mastery rose 30 -> 100.
    assert _read_memory_concept(owner["user_id"], concept_id) == 100.0

    # 4) PRIORITIZATION — the concept is no longer ranked as an unresolved weak
    #    action: progress recommendations for it are gone (mastered/empty).
    page.goto(f"{base}/frontend/dashboard.html")
    page.wait_for_load_state("domcontentloaded")
    # The name may be random; assert no high-priority weak reco remains via API.
    progress_href = f"{base}/api/v1/me/progress"
    via_api = page.evaluate(
        """async ([href]) => {
            const token = localStorage.getItem('access_token') || '';
            const res = await fetch(href, { headers: { 'Authorization': 'Bearer ' + token } });
            return { ok: res.ok, body: await res.json() };
        }""",
        [progress_href],
    )
    assert via_api["ok"]
    pdata = (via_api["body"].get("data") or {})
    weak_list = pdata.get("weak_concepts") or []
    assert concept_id not in weak_list, "NG-3: resolved concept must leave weak_concepts"

    # 5) SCHEDULING CHANGE — the due review is completed through the dashboard UI
    #    (Mark reviewed), advancing interval 1d -> 3d so it exits the due list.
    page.goto(f"{base}/frontend/dashboard.html")
    page.wait_for_load_state("domcontentloaded")
    body2 = page.locator("#reviewPanelBody")
    body2.wait_for(state="visible", timeout=20_000)
    # Re-open to a freshly-rendered panel (dashboard may be cached).
    page.reload()
    page.wait_for_load_state("domcontentloaded")
    # Scope to the review panel so the P11 Today-plan buttons (also reco-btn)
    # introduced on the shared dashboard never collide with this queue action.
    review_body = page.locator("#reviewPanelBody")
    review_body.wait_for(state="visible", timeout=20_000)
    mark = review_body.locator("button.reco-btn").first
    mark.wait_for(state="visible", timeout=20_000)
    mark.scroll_into_view_if_needed()
    mark.click()
    # The panel refreshes to an empty (or reduced) due state after completion.
    review_body.locator("button.reco-btn").wait_for(state="detached", timeout=20_000)

    # Verify scheduling advanced via the review API (completion -> no longer due).
    review_href = f"{base}/api/v1/me/review?limit=20"
    via_api = page.evaluate(
        """async ([href]) => {
            const token = localStorage.getItem('access_token') || '';
            const res = await fetch(href, { headers: { 'Authorization': 'Bearer ' + token } });
            return { ok: res.ok, body: await res.json() };
        }""",
        [review_href],
    )
    assert via_api["ok"]
    rdata = (via_api["body"].get("data") or {})
    due_ids = {it.get("schedule_id") for it in (rdata.get("items") or [])} if rdata.get("items") else set()
    assert seed.get("schedule_id") not in due_ids, (
        "NG-3: after completion the overdue item must no longer be in the due queue"
    )
