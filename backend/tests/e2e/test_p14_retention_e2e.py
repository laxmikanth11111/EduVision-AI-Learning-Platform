"""P14 browser E2E — self-reported recall outcomes & the retention surface.

Drives the vanilla SPA in a real browser against a seeded learner with ONE
weak/developing concept, an overdue review schedule and a persisted memory
(mirroring the P10/P13 deterministic-seed pattern), then closes the loop:

1. ``test_p14_good_default_and_on_track`` — the review queue renders the P14
   outcome buttons ("Mark reviewed" FIRST for the good/legacy default, then
   Again/Hard/Easy); clicking "Mark reviewed" advances the interval out of the
   due window; a dashboard refresh shows the concept as ``on_track`` with a
   truthful 100% recall chip (retention persists across reloads).
2. ``test_p14_again_lapses_and_shows_at_risk`` — clicking "Again" resets the
   ladder (tightest interval, no longer immediately due) and the retention
   panel marks the concept ``at_risk`` with 0% recall — the opposite outcome
   drives the opposite signal.
3. ``test_p14_retention_is_learner_scoped`` — a brand-new learner sees the
   documented empty state and (via API) an empty retention surface; running
   user A's review completion with user B's token returns 404 with no write.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta

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


def _register_and_create_deck(page, base_url: str, tag: str) -> dict[str, str]:
    """Register a learner and create a presentation + lesson they own."""
    email = f"p14_{tag}_{uuid.uuid4().hex[:8]}@example.com"
    password = "P14Loop1234!"
    name = "P14 Learner"

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
                body: JSON.stringify({ title: 'P14 Deck', topics: ['Recursion', 'Graphs'] }),
            });
            const presData = await presRes.json();
            const presId = presData.data.id;

            const lessonRes = await fetch(base + '/api/v1/presentations/' + presId + '/lessons', {
                method: 'POST',
                headers: auth,
                body: JSON.stringify({ mode: 'slide', title: 'P14 Outcome Lesson' }),
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


def _seed_p14_review(
    user_id: str,
    lesson_public_id: str,
    *,
    mastery: float = 40.0,
) -> dict[str, str]:
    """Seed one weak concept + memory record + an overdue step-0 schedule.

    The concept is anchored to the learner's lesson so the retention/deep-link
    resolution has real rows, and the schedule's public id is explicit so tests
    can drive cross-user completion scenarios without a re-read.
    """
    from app.models.concept import Concept
    from app.models.educational_memory import EducationalMemoryRecord
    from app.models.generated_lesson import GeneratedLesson
    from app.models.review_schedule import ReviewSchedule

    sync_engine = create_engine(
        f"sqlite:///{TEST_DB_PATH.as_posix()}", connect_args={"timeout": 30}
    )
    concept_id = f"concept_p14_{uuid.uuid4().hex[:12]}"
    schedule_id = f"rev_p14_{uuid.uuid4().hex[:12]}"
    run_name = f"Tail Recursion {uuid.uuid4().hex[:6]}"
    now = time.time()

    with Session(sync_engine) as s:
        lesson = s.execute(
            select(GeneratedLesson).where(GeneratedLesson.public_id == lesson_public_id)
        ).scalar_one()

        concept = Concept(
            public_id=concept_id,
            name=run_name,
            description="Tail recursion can be transformed into iteration.",
            presentation_id=lesson.presentation_id,
            lesson_id=lesson.id,
            difficulty_level="intermediate",
        )
        s.add(concept)
        s.flush()

        memory = build_memory_json(user_id)
        records = {str(k): dict(v) for k, v in memory["concept_records"].items()}
        records[concept_id] = dict(records.pop("concept_gauss"))
        records[concept_id]["concept_id"] = concept_id
        records[concept_id]["concept_name"] = run_name
        records[concept_id]["mastery_score"] = mastery
        records[concept_id]["first_learned_at"] = now - 3 * 86400
        records[concept_id]["last_reviewed_at"] = now - 2 * 86400
        memory["weak_concepts"] = [concept_id] if mastery < 50.0 else [concept_id]
        memory["mastered_concepts"] = []
        memory["developing_concepts"] = []
        memory["concept_records"] = records
        s.add(EducationalMemoryRecord(user_id=uuid.UUID(user_id), memory_data=memory))

        s.add(
            ReviewSchedule(
                user_id=uuid.UUID(user_id),
                concept_id=concept.id,
                lesson_id=lesson.id,
                topic=run_name,
                status="scheduled",
                scheduled_date=(datetime.now(UTC) - timedelta(days=2)).date(),
                interval_days=1,
                mastery_at_schedule=mastery,
                due_at=datetime.now(UTC) - timedelta(hours=1),
                review_metadata={"step": 0},
                public_id=schedule_id,
            )
        )
        s.commit()

    return {
        "concept_id": concept_id,
        "schedule_id": schedule_id,
        "concept_name": run_name,
    }


def _sign_in(page, base_url: str, email: str, password: str) -> None:
    page.goto(f"{base_url}/frontend/signin.html")
    page.wait_for_load_state("domcontentloaded")
    page.fill("#email", email)
    page.fill("#password", password)
    page.click("#submitBtn")
    page.wait_for_url("**/upload.html", timeout=20_000)
    page.wait_for_load_state("domcontentloaded")


def _api_get(page, base_url: str, path: str) -> dict:
    return page.evaluate(
        """async ([base, path]) => {
            const token = localStorage.getItem('access_token') || '';
            const res = await fetch(base + '/api/v1' + path, { headers: { 'Authorization': 'Bearer ' + token } });
            let body = null;
            try { body = await res.json(); } catch (e) {}
            return { ok: res.ok, status: res.status, body };
        }""",
        [base_url, path],
    )


def _api_complete(page, base_url: str, schedule_id: str, outcome: str) -> dict:
    return page.evaluate(
        """async ([base, scheduleId, outcome]) => {
            const token = localStorage.getItem('access_token') || '';
            const res = await fetch(base + '/api/v1/me/review/' + scheduleId + '/complete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
                body: JSON.stringify({ outcome }),
            });
            let body = null;
            try { body = await res.json(); } catch (e) {}
            return { ok: res.ok, status: res.status, body };
        }""",
        [base_url, schedule_id, outcome],
    )


@pytest.mark.e2e
def test_p14_good_default_and_on_track(server_env, page):
    from app.core.dependencies import get_current_user as _get_current_user
    from app.main import app as _app
    from app.services.educational_memory_service import educational_memory_service as _ems

    _app.dependency_overrides.pop(_get_current_user, None)
    base = server_env["base_url"]

    owner = _register_and_create_deck(page, base, "good")
    _ems._memories.clear()  # noqa: SLF001
    seed = _seed_p14_review(owner["user_id"], owner["lesson_id"])

    console_log: list[str] = []
    page.on("pageerror", lambda exc: console_log.append(f"pageerror: {exc}"))

    _sign_in(page, base, owner["email"], owner["password"])
    page.goto(f"{base}/frontend/dashboard.html")
    page.wait_for_load_state("domcontentloaded")

    # The due review renders the P14 outcome buttons: "Mark reviewed" (good,
    # the legacy default) FIRST, then Again/Hard/Easy.
    body = page.locator("#reviewPanelBody")
    body.wait_for(state="visible", timeout=20_000)
    buttons = body.locator("button.reco-btn")
    buttons.first.wait_for(state="visible", timeout=20_000)
    labels = buttons.all_inner_texts()
    assert labels[0] == "Mark reviewed", labels
    assert [lbl for lbl in labels[1:] if lbl] == ["Again", "Hard", "Easy"], labels

    # CLOSE THE LOOP — click "Mark reviewed" (good/legacy default).
    buttons.first.click()
    page.wait_for_function(
        """() => {
            const el = document.querySelector('#reviewPanelBody');
            return el && el.innerText.includes('Nothing due for review');
        }""",
        timeout=20_000,
    )
    empty_text = body.inner_text()
    assert "Nothing due for review" in empty_text, empty_text

    # SPACING — completion advanced the interval out of the due window.
    review = _api_get(page, base, "/me/review?limit=20")
    assert review["ok"]
    assert (review["body"].get("data") or {}).get("items") == []

    # RETENTION — the fresh good review is NOT stuck/due: on_track, 100% recall,
    # an honest ~85% retained strength, correct through a dashboard refresh.
    retention = _api_get(page, base, "/me/analytics/retention")
    assert retention["ok"]
    rdata = retention["body"].get("data") or {}
    signals = rdata.get("concepts") or []
    mine = next((c for c in signals if c["concept_public_id"] == seed["concept_id"]), None)
    assert mine is not None, signals
    assert mine["status"] == "on_track"
    assert mine["review_accuracy"] == 100.0
    assert mine["retained_strength"] == pytest.approx(85.0, abs=0.1)

    page.reload()
    page.wait_for_load_state("domcontentloaded")
    retention_body = page.locator("#retentionBody")
    retention_body.wait_for(state="visible", timeout=20_000)
    page.wait_for_function(
        """() => {
            const el = document.querySelector('#retentionBody');
            return el && (el.innerText.includes('on_track') || el.innerText.includes('on track'));
        }""",
        timeout=20_000,
    )
    retention_text = retention_body.inner_text()
    assert seed["concept_name"] in retention_text, retention_text
    assert "on_track" in retention_text, retention_text
    assert "100% recalled" in retention_text, retention_text
    assert "85%" in retention_text, retention_text

    assert not console_log, console_log


@pytest.mark.e2e
def test_p14_again_lapses_and_shows_at_risk(server_env, page):
    from app.core.dependencies import get_current_user as _get_current_user
    from app.main import app as _app
    from app.services.educational_memory_service import educational_memory_service as _ems

    _app.dependency_overrides.pop(_get_current_user, None)
    base = server_env["base_url"]

    owner = _register_and_create_deck(page, base, "again")
    _ems._memories.clear()  # noqa: SLF001
    seed = _seed_p14_review(owner["user_id"], owner["lesson_id"])

    _sign_in(page, base, owner["email"], owner["password"])
    page.goto(f"{base}/frontend/dashboard.html")
    page.wait_for_load_state("domcontentloaded")

    body = page.locator("#reviewPanelBody")
    body.wait_for(state="visible", timeout=20_000)
    buttons = body.locator("button.reco-btn")
    buttons.first.wait_for(state="visible", timeout=20_000)
    labels = buttons.all_inner_texts()
    assert labels[0] == "Mark reviewed", labels
    assert "Again" in labels, labels
    assert "Easy" in labels, labels

    # LAPSE — report the concept as forgotten through the "Again" button.
    buttons.nth(1).click()
    page.wait_for_function(
        """() => {
            const el = document.querySelector('#reviewPanelBody');
            return el && el.innerText.includes('Nothing due for review');
        }""",
        timeout=20_000,
    )

    # The ladder resets to the tightest interval: no longer immediately due.
    review = _api_get(page, base, "/me/review?limit=20")
    assert review["ok"]
    assert (review["body"].get("data") or {}).get("items") == []

    # The retention signal flips to the opposite state: at_risk, 0% recall.
    retention = _api_get(page, base, "/me/analytics/retention")
    assert retention["ok"]
    signals = (retention["body"].get("data") or {}).get("concepts", [])
    signal = next((c for c in signals if c["concept_public_id"] == seed["concept_id"]), None)
    assert signal is not None, signals
    assert signal["status"] == "at_risk"
    assert signal["review_accuracy"] == 0.0
    assert signal["retained_strength"] == 0.0

    # Persists across a dashboard refresh.
    page.reload()
    page.wait_for_load_state("domcontentloaded")
    retention_body = page.locator("#retentionBody")
    retention_body.wait_for(state="visible", timeout=20_000)
    page.wait_for_function(
        """() => {
            const el = document.querySelector('#retentionBody');
            return el && el.innerText.includes('at_risk');
        }""",
        timeout=20_000,
    )
    retention_text = retention_body.inner_text()
    assert "at_risk" in retention_text, retention_text
    assert "0% recalled" in retention_text, retention_text


@pytest.mark.e2e
def test_p14_retention_is_learner_scoped(server_env, page):
    from app.core.dependencies import get_current_user as _get_current_user
    from app.main import app as _app
    from app.services.educational_memory_service import educational_memory_service as _ems

    _app.dependency_overrides.pop(_get_current_user, None)
    base = server_env["base_url"]

    owner_a = _register_and_create_deck(page, base, "scopea")
    _ems._memories.clear()  # noqa: SLF001
    seed = _seed_p14_review(owner_a["user_id"], owner_a["lesson_id"])
    _sign_in(page, base, owner_a["email"], owner_a["password"])

    # Learner A's dashboard shows her own scheduled concept in the queue.
    page.goto(f"{base}/frontend/dashboard.html")
    page.wait_for_load_state("domcontentloaded")
    body = page.locator("#reviewPanelBody")
    body.wait_for(state="visible", timeout=20_000)
    body.locator("button.reco-btn").first.wait_for(state="visible", timeout=20_000)
    assert "Mark reviewed" in body.locator("button.reco-btn").first.inner_text()

    # Learner B registers; her surface must be empty and she must never see or
    # touch learner A's schedule.
    owner_b = _register_and_create_deck(page, base, "scopeb")
    _sign_in(page, base, owner_b["email"], owner_b["password"])
    page.goto(f"{base}/frontend/dashboard.html")
    page.wait_for_load_state("domcontentloaded")

    page.wait_for_function(
        """() => {
            const el = document.querySelector('#retentionBody');
            return el && el.innerText.includes('No retention signals yet');
        }""",
        timeout=20_000,
    )
    retention_text = page.locator("#retentionBody").inner_text()
    assert "No retention signals yet" in retention_text, retention_text
    queue_text = page.locator("#reviewPanelBody").inner_text()
    assert "Nothing due for review" in queue_text, queue_text

    isolated = _api_get(page, base, "/me/analytics/retention")
    assert isolated["ok"]
    assert (isolated["body"].get("data") or {}).get("concepts") == []

    # Cross-user completion 404s and must NOT write (interval stays 1d).
    attempt = _api_complete(page, base, seed["schedule_id"], "easy")
    assert attempt["status"] == 404, attempt
    still = _api_get(page, base, "/me/review?limit=20")
    assert (still["body"].get("data") or {}).get("total") == 0
