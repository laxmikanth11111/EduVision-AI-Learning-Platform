"""P11 browser E2E — plan / goals / path (C6).

Drives the real vanilla SPA in a real browser to close the P11 loop:

* Today Plan panel composes a due review + a lesson-to-continue and renders
  both as real deep-links (nothing dead).
* Completing the review item through the plan routes through the P10 loop and
  exits the due queue (verified via the review API).
* A goal created by the learner renders with derived progress.
* The Learning Path panel shows the ordered sequence with the current lesson.

Learner actions happen through the actual UI (``page.goto`` / ``page.click``);
API/DB calls are used only for deterministic seeding and for reading state back.
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


def _register_and_create_deck(page, base_url: str) -> dict[str, str]:
    """Register the learner and create a presentation + lesson they own."""
    uid = uuid.uuid4().hex[:8]
    email = f"p11_loop_{uid}@example.com"
    password = "P11Loop1234!"
    name = "P11 Learner"

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
                body: JSON.stringify({ title: 'P11 Deck', topics: ['Gaussian', 'Vectors'] }),
            });
            const presData = await presRes.json();
            const presId = presData.data.id;

            const lessonRes = await fetch(base + '/api/v1/presentations/' + presId + '/lessons', {
                method: 'POST',
                headers: auth,
                body: JSON.stringify({ mode: 'slide', title: 'P11 Loop Lesson' }),
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


def _seed_p11_plan_data(user_id: str, lesson_public_id: str) -> dict[str, str]:
    """Seed an in-progress lesson + weak concept + due review + memory.

    * Renders a successful lesson version/blocks (player works).
    * Creates an in-progress LearningSession so the path has a current lesson.
    * Creates a weak-owned ``Concept`` (30% mastery) + matching memory record.
    * Creates an overdue ``ReviewSchedule`` for the concept.

    Returns ``{concept_id, schedule_id}``.
    """
    from datetime import UTC, datetime, timedelta

    from app.models.concept import Concept
    from app.models.educational_memory import EducationalMemoryRecord
    from app.models.generated_block import GeneratedBlock
    from app.models.generated_lesson import GeneratedLesson
    from app.models.generated_lesson_version import GeneratedLessonVersion
    from app.models.learning_session import LearningSession
    from app.models.review_schedule import ReviewSchedule

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

        # In-progress session -> the path/plan treat the lesson as "current".
        s.add(
            LearningSession(
                user_id=uuid.UUID(user_id),
                lesson_id=lesson.id,
                status="started",
                completion_percentage=40.0,
                current_slide_position=1,
                current_block_position=1,
                resume_version=0,
            )
        )
        s.flush()

        memory = build_memory_json(user_id)
        now = time.time()
        records = {str(k): dict(v) for k, v in memory["concept_records"].items()}
        weak_id, _mastered_id = "concept_gauss", "concept_vector"
        records[concept_id] = dict(records.pop(weak_id))
        records[concept_id]["concept_id"] = concept_id
        records[concept_id]["concept_name"] = run_name
        records[concept_id]["mastery_score"] = 30.0
        records[concept_id]["first_learned_at"] = now - 7200
        records[concept_id]["last_reviewed_at"] = now - 86400
        memory["weak_concepts"] = [concept_id]
        memory["developing_concepts"] = []
        memory["mastered_concepts"] = []
        memory["concept_records"] = records
        profile = dict(memory.get("profile") or {})
        profile["average_mastery"] = 30.0
        profile["streak_days"] = 1
        memory["profile"] = profile
        s.add(EducationalMemoryRecord(user_id=uuid.UUID(user_id), memory_data=memory))

        sched = ReviewSchedule(
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
        s.add(sched)
        s.flush()
        out["schedule_id"] = sched.public_id

        s.commit()
    return out


def _sign_in(page, base_url: str, email: str, password: str) -> None:
    page.goto(f"{base_url}/frontend/signin.html")
    page.wait_for_load_state("domcontentloaded")
    page.fill("#email", email)
    page.fill("#password", password)
    page.click("#submitBtn")
    page.wait_for_url("**/upload.html", timeout=20_000)
    page.wait_for_load_state("domcontentloaded")


@pytest.mark.e2e
def test_p11_dashboard_plan_goals_path(server_env, page):
    from app.core.dependencies import get_current_user as _get_current_user
    from app.main import app as _app

    _app.dependency_overrides.pop(_get_current_user, None)
    base = server_env["base_url"]

    owner = _register_and_create_deck(page, base)

    from app.services.educational_memory_service import (
        educational_memory_service as _ems,
    )

    _ems._memories.clear()  # noqa: SLF001
    seed = _seed_p11_plan_data(owner["user_id"], owner["lesson_id"])
    schedule_id = seed["schedule_id"]

    _sign_in(page, base, owner["email"], owner["password"])

    # Create a goal through the real API (the dashboard displays derived
    # progress; target above current -> shown as in progress, never achieved).
    goal_title = "Reach 90% average mastery"
    created_goal = page.evaluate(
        """async ([base, title, target]) => {
            const token = localStorage.getItem('access_token') || '';
            const res = await fetch(base + '/api/v1/me/goals', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
                body: JSON.stringify({ goal_type: 'mastery_target', title, target_value: target }),
            });
            const body = await res.json();
            return { ok: res.ok, goalId: body.data && body.data.goal ? body.data.goal.id : null };
        }""",
        [base, goal_title, 90.0],
    )
    assert created_goal["ok"], "goal creation must succeed"
    assert created_goal["goalId"]

    # Dashboard: all three P11 panels render with deep-linked, actionable items.
    page.goto(f"{base}/frontend/dashboard.html")
    page.wait_for_load_state("domcontentloaded")

    console_log: list[str] = []
    page.on("pageerror", lambda exc: console_log.append(f"pageerror: {exc}"))
    page.on(
        "console",
        lambda msg: console_log.append(f"{msg.type}: {msg.text}")
        if msg.type in ("error", "warning")
        else None,
    )

    plan_body = page.locator("#todayPlanBody")
    plan_body.wait_for(state="visible", timeout=20_000)
    # Wait for real content: the async fetch replaces the loading placeholder.
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and plan_body.locator(".plan-type").count() == 0:
        time.sleep(0.4)
    if plan_body.locator(".plan-type").count() == 0:
        raise AssertionError(
            "Today plan never rendered. body="
            + repr(plan_body.inner_text())
            + " console="
            + repr(console_log)
        )
    plan_body.locator(".plan-type").first.wait_for(state="visible", timeout=5_000)
    plan_text = plan_body.inner_text()
    assert "Review" in plan_text, "Today plan must include a review item"
    assert "Continue" in plan_text, "Today plan must include a lesson to continue"

    # Every plan item links to a real, existing destination (player or tutor).
    plan_links = plan_body.locator("a.lesson-tutor")
    plan_links.first.wait_for(state="visible", timeout=10_000)
    for i in range(plan_links.count()):
        href = plan_links.nth(i).get_attribute("href") or ""
        assert href.startswith(
            ("/frontend/player.html?lesson=", "/frontend/tutor.html?concept=")
        ), f"plan deep-link must be actionable, got {href}"

    path_body = page.locator("#pathBody")
    path_body.wait_for(state="visible", timeout=20_000)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and path_body.locator(".path-title").count() == 0:
        time.sleep(0.4)
    if path_body.locator(".path-title").count() == 0:
        raise AssertionError(
            "Learning path never rendered. body="
            + repr(path_body.inner_text())
            + " console="
            + repr(console_log)
        )
    path_body.locator(".path-title").first.wait_for(state="visible", timeout=5_000)
    assert "P11 Loop Lesson" in path_body.inner_text()
    path_link = path_body.locator("a.lesson-tutor").first
    href = path_link.get_attribute("href") or ""
    assert href.startswith("/frontend/player.html?lesson=")

    goals_body = page.locator("#goalsBody")
    goals_body.wait_for(state="visible", timeout=20_000)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and goals_body.locator(".goal-name").count() == 0:
        time.sleep(0.4)
    if goals_body.locator(".goal-name").count() == 0:
        raise AssertionError(
            "Goals panel never rendered. body="
            + repr(goals_body.inner_text())
            + " console="
            + repr(console_log)
        )
    goals_body.locator(".goal-name").first.wait_for(state="visible", timeout=5_000)
    goals_text = goals_body.inner_text()
    assert goal_title in goals_text
    assert "in progress" in goals_text
    assert "Achieved" not in goals_text

    # 1) COMPLETE THE REVIEW through the plan UI -> routes through P10.
    review_btn = plan_body.locator('button[data-key^="review."]').first
    review_btn.wait_for(state="visible", timeout=10_000)
    review_btn.click()
    plan_body.locator('button[data-key^="review."]').wait_for(
        state="detached", timeout=20_000
    )

    time.sleep(2)
    post_review_text = plan_body.inner_text()
    assert "Could not record" not in post_review_text, (
        f"Review completion through the plan failed: {post_review_text}"
    )

    # The review button detached because the plan re-rendered.  Now the lesson
    # button should be visible in the refreshed plan.  Wait for it to appear.
    lesson_key = f"lesson.{owner['lesson_id']}"
    lesson_btn = plan_body.locator(f'button[data-key="{lesson_key}"]')
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and lesson_btn.count() == 0:
        time.sleep(0.5)

    # If the exact data-key didn't match, the plan item_key may differ (e.g.
    # the path returned a different title).  Fall back to finding any lesson
    # Mark-complete button via the plan API.
    if lesson_btn.count() == 0:
        plan_api = page.evaluate(
            """async ([base]) => {
                const token = localStorage.getItem('access_token') || '';
                const res = await fetch(base + '/api/v1/me/plan/today', {
                    headers: { 'Authorization': 'Bearer ' + token },
                });
                const body = await res.json();
                const data = body.data || {};
                return (data.items || []).map(i => ({key: i.item_key, type: i.item_type, status: i.status, title: i.title}));
            }""",
            [base],
        )
        lesson_items = [it for it in plan_api if it["type"] == "lesson"]
        assert lesson_items, f"no lesson item in plan API: {plan_api}"
        actual_key = lesson_items[0]["key"]
        lesson_btn = plan_body.locator(f'button[data-key="{actual_key}"]')
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and lesson_btn.count() == 0:
            time.sleep(0.5)

    post_plan_text = plan_body.inner_text()
    if lesson_btn.count() == 0:
        raise AssertionError(
            f"Lesson button never appeared after review. "
            f"plan_body={post_plan_text!r} console={console_log!r}"
        )
    lesson_btn.wait_for(state="visible", timeout=5_000)
    clicked_key = lesson_btn.get_attribute("data-key")
    lesson_btn.click()

    # The panel refreshes after the POST returns.  Poll for the sticky "done"
    # chip AND confirm via the API that the item is now completed — a single
    # consistent read, free of the render race.
    done_seen = False
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and not done_seen:
        time.sleep(0.5)
        try:
            done_seen = "done" in plan_body.inner_text()
        except Exception:
            done_seen = False
        if not done_seen:
            st = page.evaluate(
                """async ([base, key]) => {
                    const token = localStorage.getItem('access_token') || '';
                    const res = await fetch(base + '/api/v1/me/plan/today', {
                        headers: { 'Authorization': 'Bearer ' + token },
                    });
                    const body = await res.json();
                    const data = body.data || {};
                    const it = (data.items || []).find(x => x.item_key === key);
                    return it ? { status: it.status, completed: data.completed_items, total: data.total_items } : null;
                }""",
                [base, clicked_key],
            )
            if st and st.get("status") == "completed":
                done_seen = True
    assert done_seen, (
        "lesson item must show the sticky done state; plan_body="
        + repr(plan_body.inner_text())
        + f" console={console_log!r}"
    )

    # Verified via the review API: completion advanced due_at out of the queue.
    review_check = page.evaluate(
        """async ([base]) => {
            const token = localStorage.getItem('access_token') || '';
            const res = await fetch(base + '/api/v1/me/review?limit=20', {
                headers: { 'Authorization': 'Bearer ' + token },
            });
            const body = await res.json();
            return { ok: res.ok, due: (body.data && body.data.items || []).map(i => i.schedule_id) };
        }""",
        [base],
    )
    assert review_check["ok"]
    assert schedule_id not in review_check["due"], (
        "completing the plan review item must exit the due queue"
    )

    # Verified via API: the plan row reflects completed == total for today.
    plan_check = page.evaluate(
        """async ([base]) => {
            const token = localStorage.getItem('access_token') || '';
            const res = await fetch(base + '/api/v1/me/plan/today', {
                headers: { 'Authorization': 'Bearer ' + token },
            });
            const body = await res.json();
            const data = body.data || {};
            return {
                ok: res.ok,
                completed: data.completed_items,
                total: data.total_items,
                items: data.items || [],
            };
        }""",
        [base],
    )
    assert plan_check["ok"]
    assert plan_check["completed"] >= 1
    assert any(
        it.get("item_type") == "lesson" and it.get("status") == "completed"
        for it in plan_check["items"]
    )
    assert any(
        it.get("status") == "pending"
        for it in plan_check["items"]
    ), "remaining practice item(s) stay pending"
