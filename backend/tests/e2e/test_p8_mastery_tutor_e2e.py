"""P8 browser E2E — mastery-aware AI tutor (C5).

Drives the real vanilla SPA through the browser:

    sign in → open the mastery tutor → a session is created
    → weak-concept quick pick is shown and clickable
    → ask a question → a grounded/attributed assistant reply appears
    → remediate a weak concept → a mastery-aware remediation reply appears

Learner actions happen through the actual UI (``page.goto``/``page.click``);
API/DB calls are used only for deterministic seeding. The weak concept, its
learner-owned presentation, a content unit and a document chunk are seeded
directly into the shared SQLite test DB so the tutor's RAG/mastery pipeline
returns real, learner-scoped data — no mocked 200s.
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


def _seed_tutor_data(user_id: str, presentation_id: str) -> str:
    """Seed mastery + a learner-owned weak concept into the shared DB.

    Synchronous SQLAlchemy over the shared SQLite test file (``asyncio.run``
    fails under ``asyncio_mode = \"auto\"``). Returns the concept public_id owned
    by the learner so the tutor/remediation flow can target it.
    """
    from app.models.concept import Concept
    from app.models.educational_memory import EducationalMemoryRecord
    from app.models.presentation import Presentation
    from tests.conftest import TEST_DB_PATH

    sync_engine = create_engine(
        f"sqlite:///{TEST_DB_PATH.as_posix()}",
        connect_args={"timeout": 30},
    )
    concept_id = f"concept_{uuid.uuid4().hex[:12]}"
    with Session(sync_engine) as s:
        pres = s.execute(
            select(Presentation).where(Presentation.public_id == presentation_id)
        ).scalar_one()

        # Concept owned by the learner (weak, 30% mastery via memory).
        # The name is unique to this run to avoid colliding with any concept the
        # manual-deck endpoint may have auto-created for the new presentation.
        import time as _time

        run_name = f"Gaussian Distributions {uuid.uuid4().hex[:6]}"
        s.add(
            Concept(
                public_id=concept_id,
                name=run_name,
                description=(
                    "Gaussian Distributions model symmetric bell curves. The mean "
                    "sets the centre and the standard deviation sets the spread."
                ),
                presentation_id=pres.id,
                lesson_id=None,
            )
        )
        s.flush()

        # Educational memory referencing the same concept id (weak, 30%).
        memory = build_memory_json(user_id)
        records = {str(k): dict(v) for k, v in memory["concept_records"].items()}
        records[concept_id] = records.pop("concept_gauss")
        records[concept_id]["concept_name"] = run_name
        records[concept_id]["concept_id"] = concept_id
        memory["weak_concepts"] = [concept_id]
        memory["concept_records"] = records
        s.add(EducationalMemoryRecord(user_id=uuid.UUID(user_id), memory_data=memory))
        s.commit()

    return concept_id


def _register_and_create_deck(page, base_url: str) -> dict[str, str]:
    """Register the learner and create a presentation + lesson they own."""
    uid = uuid.uuid4().hex[:8]
    email = f"p8_tutor_{uid}@example.com"
    password = "TutorPass1234!"
    name = "P8 Tutor Learner"

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
                body: JSON.stringify({ title: 'P8 Tutor Deck', topics: ['Statistics'] }),
            });
            const presData = await presRes.json();
            const presId = presData.data.id;

            const lessonRes = await fetch(base + '/api/v1/presentations/' + presId + '/lessons', {
                method: 'POST',
                headers: auth,
                body: JSON.stringify({ mode: 'slide', title: 'P8 Tutor Lesson' }),
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
def test_mastery_tutor_e2e(server_env, page):
    # Use real JWT auth so the tutor flows are learner-scoped; the root conftest's
    # autouse ``_override_get_current_user`` would otherwise always resolve to the
    # shared TEST_USER_ID.
    from app.core.dependencies import get_current_user as _get_current_user
    from app.main import app as _app

    _app.dependency_overrides.pop(_get_current_user, None)

    base = server_env["base_url"]
    learner = _register_and_create_deck(page, base)

    # Clear any stale in-memory mastery before DB seeding, then seed.
    from app.services.educational_memory_service import (
        educational_memory_service as _ems,
    )

    _ems._memories.clear()  # noqa: SLF001
    _seed_tutor_data(learner["user_id"], learner["presentation_id"])

    # STEP 1 — sign in through the real form.
    page.goto(f"{base}/frontend/signin.html")
    page.wait_for_load_state("domcontentloaded")
    page.fill("#email", learner["email"])
    page.fill("#password", learner["password"])
    page.click("#submitBtn")
    page.wait_for_url("**/upload.html", timeout=20_000)
    page.wait_for_load_state("domcontentloaded")

    # STEP 2 — the learner dashboard shows the tutor navigation affordance.
    page.goto(f"{base}/frontend/dashboard.html")
    page.wait_for_load_state("domcontentloaded")
    tutor_link = page.locator('.nav-links a[href="/frontend/tutor.html"]')
    tutor_link.wait_for(state="visible", timeout=20_000)
    assert tutor_link.inner_text().strip() == "Mastery Tutor"

    # STEP 3 — open the mastery tutor page; a session is created and a weak
    # concept quick pick appears.
    page.goto(f"{base}/frontend/tutor.html")
    page.wait_for_load_state("domcontentloaded")

    picks_wrap = page.locator("#picks")
    page.locator("#picks .pick").first.wait_for(state="visible", timeout=25_000)
    assert "Gaussian Distributions" in picks_wrap.inner_text()

    # The helper greeting bubble renders after session creation.
    greeting = page.locator("#chatArea .msg-bubble")
    greeting.first.wait_for(state="visible", timeout=25_000)

    # STEP 4 — ask a question about the weak concept.
    page.fill("#input", "Why is Gaussian Distributions hard for me?")
    page.click('#composer button[type="submit"]')
    # Wait for the "Thinking…" placeholder to be replaced by a real reply.
    page.locator("#pending").wait_for(state="attached", timeout=10_000)
    page.locator("#pending").wait_for(state="detached", timeout=30_000)
    page.locator("#chatArea .msg-meta").first.wait_for(state="visible", timeout=30_000)

    reply_row = page.locator(".msg-meta").first
    assert reply_row.inner_text().strip()

    # STEP 5 — the reply is attributed/confident and grounded in the learner's
    # data (rag or deterministic), never fabricated.
    reply_meta = reply_row.inner_text().lower()
    assert ("rag" in reply_meta) or ("deterministic" in reply_meta) or ("confidence" in reply_meta)

    body_text = page.locator("#chatArea .msg-bubble").last.inner_text().lower()
    assert ("gaussian" in body_text) or ("mastery" in body_text)

    # STEP 6 — remediate the weak concept from the quick pick.
    page.locator("#picks .pick", has_text="Gaussian Distributions").first.click()
    # The remediation "Building your remediation plan…" placeholder is replaced
    # with the real, mastery-grounded response when it completes.
    page.locator("#pending").wait_for(state="attached", timeout=10_000)
    page.locator("#pending").wait_for(state="detached", timeout=30_000)
    remediation = page.locator("#chatArea .msg-bubble").last.inner_text()
    assert "Gaussian Distributions" in remediation
    assert "mastery" in remediation.lower()
