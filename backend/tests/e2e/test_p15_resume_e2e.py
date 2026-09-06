"""P15 browser E2E — persistent lesson resume & learner continuity.

Drives the vanilla SPA in a real browser against a seeded learner + a "succeeded"
2-topic lesson version (4 slides), then closes the resume loop exactly as a real
learner would:

1. ``test_p15_resume_journey_and_refresh`` — start the lesson, advance to a
   mid-deck slide (auto server sync), leave, reopen ``player.html?lesson=..``
   and assert the exact slide is restored; the same position survives a
   ``page.reload`` (server session, not localStorage).
2. ``test_p15_dashboard_resume_deep_link`` — the dashboard lesson-progress row
   advertises "Resume from slide N"; clicking it cold-loads the player at N, and
   an explicit ``?slide=`` override still wins over the server position.
3. ``test_p15_resume_is_learner_scoped`` — user B starting their own fresh deck
   opens at slide 1/4 regardless of A's stored position, and A's position is
   untouched after B's visit (cross-user writes 404-equalize).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from tests.conftest import TEST_DB_PATH

SLIDES_TOTAL = 4


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
    email = f"p15_{tag}_{uuid.uuid4().hex[:8]}@example.com"
    password = "P15Loop1234!"
    name = "P15 Learner"

    result = page.evaluate(
        """async ([base, email, password, name]) => {
            const regRes = await fetch(base + '/api/v1/auth/register', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password, name }),
            });
            const regData = await regRes.json();
            const token = regData.tokens.access_token;
            const auth = { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token };

            const presRes = await fetch(base + '/api/v1/presentations/manual', {
                method: 'POST',
                headers: auth,
                body: JSON.stringify({ title: 'P15 Deck', topics: ['Resume T1', 'Resume T2'] }),
            });
            const presData = await presRes.json();
            const presId = presData.data.id;

            const lessonRes = await fetch(base + '/api/v1/presentations/' + presId + '/lessons', {
                method: 'POST',
                headers: auth,
                body: JSON.stringify({ mode: 'slide', title: 'P15 Resume Lesson' }),
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


def _seed_p15_content(user_id: str, lesson_public_id: str) -> None:
    """Mark the lesson ready with a succeeded 2-topic version (4 slides)."""
    from app.models.generated_block import GeneratedBlock
    from app.models.generated_lesson import GeneratedLesson
    from app.models.generated_lesson_version import GeneratedLessonVersion

    sync_engine = create_engine(
        f"sqlite:///{TEST_DB_PATH.as_posix()}", connect_args={"timeout": 30}
    )
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
        for pos, heading in enumerate(["Resume: First Topic", "Resume: Second Topic"]):
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
        s.commit()


def _sign_in(page, base_url: str, email: str, password: str) -> None:
    page.goto(f"{base_url}/frontend/signin.html")
    page.wait_for_load_state("domcontentloaded")
    page.fill("#email", email)
    page.fill("#password", password)
    page.click("#submitBtn")
    page.wait_for_url("**/upload.html", timeout=20_000)
    page.wait_for_load_state("domcontentloaded")


def _open_player_and_wait(page, base_url: str, lesson_id: str) -> None:
    page.goto(f"{base_url}/frontend/player.html?lesson={lesson_id}")
    page.wait_for_load_state("domcontentloaded")
    counter = page.locator("#counter")
    counter.wait_for(state="visible", timeout=20_000)
    try:
        page.wait_for_function(
            """() => {
            const el = document.querySelector('#counter');
            return el && /\\/ 4/.test(el.innerText);
        }""",
            timeout=20_000,
        )
    except Exception:
        state = page.locator("#stateWrap").inner_text()
        raise AssertionError(
            f"player never rendered 4 slides; url={page.url} "
            f"stateWrap={state!r} frame={page.inner_text('body')[:400]!r}"
        )


def _current_slide(page) -> int:
    """Read the player counter ``<b>N</b> / total`` as a 0-based slide index."""
    text = page.locator("#counter").inner_text().strip()
    number = int(text.split("/")[0].strip())
    return number - 1


def _api_get(page, base_url: str, path: str) -> dict:
    return page.evaluate(
        """async ([base, path]) => {
            const token = localStorage.getItem('access_token') || '';
            const res = await fetch(base + '/api/v1' + path, {
                headers: { 'Authorization': 'Bearer ' + token },
            });
            let body = null;
            try { body = await res.json(); } catch (e) {}
            return { ok: res.ok, status: res.status, body };
        }""",
        [base_url, path],
    )


def _wait_for_progress_resume(page, base_url: str, expected_slide: int) -> None:
    import time as _time

    deadline = _time.monotonic() + 20
    last_body = None
    while _time.monotonic() < deadline:
        resp = _api_get(page, base_url, "/me/progress")
        last_body = resp.get("body") if resp else None
        if resp and resp.get("ok"):
            items = ((last_body or {}).get("data") or {}).get("lesson_progress") or []
            if any(int(it.get("resume_slide") or 0) == expected_slide for it in items):
                return
        _time.sleep(0.3)
    raise AssertionError(
        f"resume_slide {expected_slide} never persisted; last progress body={last_body!r}"
    )


@pytest.mark.e2e
def test_p15_resume_journey_and_refresh(server_env, page):
    from app.core.dependencies import get_current_user as _get_current_user
    from app.main import app as _app
    from app.services.educational_memory_service import educational_memory_service as _ems

    _app.dependency_overrides.pop(_get_current_user, None)
    base = server_env["base_url"]

    owner = _register_and_create_deck(page, base, "journey")
    _ems._memories.clear()  # noqa: SLF001
    _seed_p15_content(owner["user_id"], owner["lesson_id"])

    console_log: list[str] = []
    page.on("pageerror", lambda exc: console_log.append(f"pageerror: {exc}"))

    _sign_in(page, base, owner["email"], owner["password"])
    _open_player_and_wait(page, base, owner["lesson_id"])

    # Fresh session: slide 1 of 4.
    assert _current_slide(page) == 0, "a new lesson must open at slide 1"

    # Advance to a mid-deck slide (index 2 -> counter 3/4). The navigation sync
    # debounces a real /position write — wait until the server confirms it so the
    # "navigate away" step below is deterministic.
    page.locator("#nextBtn").click()
    page.locator("#nextBtn").click()
    assert _current_slide(page) == 2
    _wait_for_progress_resume(page, base, 2)

    # Leave the lesson entirely.
    page.goto(f"{base}/frontend/upload.html")
    page.wait_for_load_state("domcontentloaded")

    # REOPEN without any query args -> player must restore slide 3/4.
    _open_player_and_wait(page, base, owner["lesson_id"])
    assert _current_slide(page) == 2, "reopening the lesson must restore the saved slide"

    # Refresh persistence: reload keeps the same slide (server session).
    page.reload()
    page.wait_for_load_state("domcontentloaded")
    page.locator("#counter").wait_for(state="visible", timeout=20_000)
    page.wait_for_function(
        """() => {
            const el = document.querySelector('#counter');
            return el && el.innerText.includes('/ 4');
        }""",
        timeout=20_000,
    )
    assert _current_slide(page) == 2, "reload must retain the persisted slide"

    assert not console_log, console_log


@pytest.mark.e2e
def test_p15_dashboard_resume_deep_link(server_env, page):
    from app.core.dependencies import get_current_user as _get_current_user
    from app.main import app as _app
    from app.services.educational_memory_service import educational_memory_service as _ems

    _app.dependency_overrides.pop(_get_current_user, None)
    base = server_env["base_url"]

    owner = _register_and_create_deck(page, base, "deeplink")
    _ems._memories.clear()  # noqa: SLF001
    _seed_p15_content(owner["user_id"], owner["lesson_id"])

    console_log: list[str] = []
    page.on("pageerror", lambda exc: console_log.append(f"pageerror: {exc}"))

    _sign_in(page, base, owner["email"], owner["password"])
    _open_player_and_wait(page, base, owner["lesson_id"])
    page.locator("#nextBtn").click()
    page.locator("#nextBtn").click()
    assert _current_slide(page) == 2
    _wait_for_progress_resume(page, base, 2)

    # Dashboard advertises the resume deep-link on the lesson-progress row.
    page.goto(f"{base}/frontend/dashboard.html")
    page.wait_for_load_state("domcontentloaded")
    progress = _api_get(page, base, "/me/progress")
    assert progress["ok"], progress
    items = (progress["body"].get("data") or {}).get("lesson_progress") or []
    assert items, "the started lesson must appear in lesson progress"
    item = items[0]
    assert item["lesson_id"] == owner["lesson_id"]
    assert item["resume_slide"] == 2
    assert item["resume_link"].endswith(f"lesson={owner['lesson_id']}&slide=2"), item["resume_link"]

    # Cold-load deep-link: open the dashboard resume URL and land on slide 3/4.
    _open_player_and_wait(page, base, owner["lesson_id"])
    page.goto(f"{base}{item['resume_link']}")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_function(
        """() => {
            const el = document.querySelector('#counter');
            return el && el.innerText.includes('/ 4');
        }""",
        timeout=20_000,
    )
    assert _current_slide(page) == 2, "the resume deep-link must open at the saved slide"

    # An explicit ?slide= override still beats the server position.
    _open_player_and_wait(page, base, owner["lesson_id"])
    page.goto(f"{base}/frontend/player.html?lesson={owner['lesson_id']}&slide=0")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_function(
        """() => {
            const el = document.querySelector('#counter');
            return el && el.innerText.includes('/ 4');
        }""",
        timeout=20_000,
    )
    assert _current_slide(page) == 0, "?slide=0 must override the server resume position"

    assert not console_log, console_log


@pytest.mark.e2e
def test_p15_resume_is_learner_scoped(server_env, page):
    from app.core.dependencies import get_current_user as _get_current_user
    from app.main import app as _app
    from app.services.educational_memory_service import educational_memory_service as _ems

    _app.dependency_overrides.pop(_get_current_user, None)
    base = server_env["base_url"]

    # Create BOTH decks before any sign-in: register never writes an auth cookie,
    # so without a prior login the browser sends no cookie and the Authorization
    # header alone determines ownership -> each deck lands under its own user.
    owner_a = _register_and_create_deck(page, base, "scopea")
    _ems._memories.clear()  # noqa: SLF001
    _seed_p15_content(owner_a["user_id"], owner_a["lesson_id"])
    owner_b = _register_and_create_deck(page, base, "scopeb")
    _seed_p15_content(owner_b["user_id"], owner_b["lesson_id"])

    # A advances A's deck to slide 3/4 and confirms it persisted.
    _sign_in(page, base, owner_a["email"], owner_a["password"])
    _open_player_and_wait(page, base, owner_a["lesson_id"])
    page.locator("#nextBtn").click()
    page.locator("#nextBtn").click()
    assert _current_slide(page) == 2
    _wait_for_progress_resume(page, base, 2)

    # Learner B signs in with their OWN deck; because sessions are learner-scoped,
    # B starts at slide 1 with zero stored position.
    _sign_in(page, base, owner_b["email"], owner_b["password"])
    _open_player_and_wait(page, base, owner_b["lesson_id"])
    assert _current_slide(page) == 0, "learner B must start at slide 1 of their own deck"

    # B's presence changes nothing for A: A's stored resume is still slide 3/4.
    b_progress = _api_get(page, base, "/me/progress")
    assert b_progress["ok"]
    b_items = (b_progress["body"].get("data") or {}).get("lesson_progress") or []
    b_slides = [
        it.get("resume_slide") for it in b_items if it.get("lesson_id") == owner_b["lesson_id"]
    ]
    assert b_slides == [0], b_items

    _sign_in(page, base, owner_a["email"], owner_a["password"])
    a_progress = _api_get(page, base, "/me/progress")
    assert a_progress["ok"]
    a_items = (a_progress["body"].get("data") or {}).get("lesson_progress") or []
    a_entry = next((it for it in a_items if it.get("lesson_id") == owner_a["lesson_id"]), None)
    assert a_entry is not None, a_items
    assert a_entry["resume_slide"] == 2, "A's resume position must survive B's visit"
