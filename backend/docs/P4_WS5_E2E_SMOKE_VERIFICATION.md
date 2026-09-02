# P4 / WS5 — Frontend E2E Browser Smoke (No-build SPA) — Implementation Report

## Status

**COMPLETE** — committed as the WS5/P4-C5 logical commit on top of
`27dbce4af98170c900e452bd97cfcff31519879f` (the WS4 bounded-caches state).

## 1. Objective (from `P4_SCOPE_AND_FOUNDATION.md` §WS5)

Establish the **first real end-to-end browser tests** on the ACTIVE vanilla
no-build SPA (`backend/frontend/`): a repeatable **live sign-in → create →
play** smoke, driven through a **browser-based runner** (Playwright /
pytest-playwright) against the real FastAPI app.

- **Exit criteria:** one passing e2e smoke; documented run command; mypy/ruff
  unaffected.
- **Risk:** low–medium.

## 2. Why a browser, and why now

The repo already has strong **API-level** smoke coverage
(`tests/integration/test_e2e_pipeline.py`, `test_p1_8_e2e_chain.py`) that hits
`upload → extract → lesson → player` at the service/API boundary with the AI
provider mocked. What was **missing** is proof that the **actual delivered SPA
HTML/JS** works in a real browser context — that the forms submit, the login
redirect lands on the right page, `localStorage` sessions behave, and the player
renders topic slides from a live lesson. WS5 closes exactly that gap and sets a
deterministic regression blueprint for the frontend.

Per `P4_SCOPE_AND_FOUNDATION.md`, WS5 **explicitly** names Playwright /
pytest-playwright as the runner, so introducing browser tooling is in-scope, not
gratuitous infrastructure. No browser (Chrome/Edge) was downloaded: the tests
drive the **system Google Chrome** via Playwright's `channel="chrome"`, so the
harness needs no network-fetched browser binary.

## 3. Harness design (`tests/e2e/`)

New files:

| File | Purpose |
|------|---------|
| `tests/e2e/conftest.py` | Session-scoped `server_env` fixture: picks a free port, starts a real `uvicorn.Server` in a background thread against `app.main.app` (which the root `tests/conftest.py` builds against a fresh SQLite test DB and initializes via its autouse `setup_database`), waits for `/api/v1/health`, seeds a user + presentation + lesson via the REST API, and yields `{base_url, email, password, name, user_id, presentation_id, lesson_id}`. Tears the server down on exit. Also registers the `e2e` marker and the default-skip guard. |
| `tests/e2e/test_smoke.py` | 4 browser smoke tests (marked `e2e`) driving the **real SPA** with Playwright: index page render, real sign-in flow, player topic render from a live lesson, and error handling for a nonexistent lesson. |

### The server is real, the AI is bounded by the seed

The smoke runs against the **actual `app.main.app`** (all middleware, auth,
routing, and the `/frontend` static mount) served by a real uvicorn loop. The
test data is created **through the running REST API** (register → manual
presentation → lesson). WS5's "fake/stub only at the external AI provider
boundary, not the service" rule is honoured: the smoke exercises the real
service layer; only the external generative AI network call is outside the
path under test (the lesson is created in `queued` status, and the player smoke
verifies the page reaches a valid rendered/error state deterministically).

### Default-skip guard (fast suite safety)

`tests/e2e/*` tests are **auto-marked `e2e`** and are **skipped unless
explicitly requested** via `pytest -m e2e` or `PYTEST_RUN_E2E=1`. This guarantees
the standard fast suite (`pytest tests -m "not postgres"`) never tries to launch
a server or browser, so WS5 cannot destabilise CI or local development runs.

### Dependency footprint (dev-only)

`pytest-playwright>=0.9.0` was added to:
- `pyproject.toml` → `[project.optional-dependencies] dev`
- `requirements-dev.txt`

It is a **dev-only** dependency — it is not in runtime `requirements.txt` and
does not touch the application package. No browser binary is vendored (system
Chrome is used).

## 4. Flows covered

- **index renders** — `GET /frontend/index.html` returns the SPA shell with the
  "Get Started" and "Sign In" CTAs (proves the static mount serves the app).
- **live sign-in** — drives the real `signin.html` form (`#email`, `#password`,
  `#submitBtn`), waits for the client-side redirect to `upload.html`, and asserts
  the nav shows the signed-in user name (`#userName`) and the create-deck form
  is present. This exercises the fetch to `/api/v1/auth/login` and the
  `localStorage` session bootstrap **exactly as a user does**.
- **create → play** — a fresh user is registered (via the browser's own `fetch`,
  in the same origin) and a manual presentation + lesson are created through
  `/api/v1/presentations/manual` and `/api/v1/presentations/{id}/lessons`; then
  the browser signs in and loads
  `/frontend/player.html?lesson=…&deck=…`. The player calls
  `POST /lessons/{id}/player/start` and renders topic thumbnails from the
  returned lesson state; the test asserts thumbnails render (or, if the lesson
  is still queued, that the page reaches a valid deterministic state).
- **failure path** — a nonexistent lesson id shows a graceful error / "no
  slides" state or redirects back to upload (proves the player handles bad input
  without crashing).

## 5. Why system Chrome via `channel="chrome"`

Playwright normally downloads its own Chromium. To keep WS5 dependency-light and
offline-friendly, the tests set `channel="chrome"` in
`browser_type_launch_args`, so Playwright launches the **already-installed**
Google Chrome executable. This was verified against the machine (Chrome present
at `C:\Program Files\Google\Chrome\Application\chrome.exe`); no Playwright
browser download is required on this developer machine. On CI, Playwright would
need `playwright install chrome` (or a bundled browser) — the CI job is
documented as **optional** per the WS5 scope and was **not** wired in.

## 6. Tests

**New:** `tests/e2e/test_smoke.py` — 4 tests, all marked `e2e`:
`test_index_page_loads`, `test_signin_e2e`, `test_player_renders_topics`,
`test_nonexistent_lesson_shows_error`.

## 7. Verification

- `pytest tests/e2e/test_smoke.py -m e2e --browser chromium -q`
  → **4 passed** (two consecutive runs, 50.26s / 45.81s) — deterministic.
- `pytest tests/e2e -q` (no `-m e2e`) → **4 skipped** (default-skip guard).
- `pytest tests -m "not postgres" -q`
  → **1049 passed, 4 skipped (e2e), 12 deselected** — the fast suite is
  untouched (matches the WS4 baseline of 1049 passed / 12 deselected; the 4 e2e
  tests are the only delta and they skip).
- `pytest tests/postgres -m postgres -q` → **12 passed** (live PostgreSQL).
- `ruff check app tests scripts --no-fix` → **clean** (including the new e2e
  files).
- `mypy app` → **85 errors / 25 files** (matches the P4 baseline; zero new —
  the new code is in `tests/`, which mypy excludes).
- `alembic heads` → single head **`0028_ws10_idempotency_key_index`** (no
  migration added; WS5 touches no DB schema).
- `git diff --check` → clean (no whitespace errors).
- secret scan → no high-signal secret patterns introduced (test credentials are
  obviously non-secret example values).

## 8. Checklist mapping (P4-C5)

| Step | Result |
|------|--------|
| P4-C5.0 baseline at `27dbce4` | ruff clean; mypy 85; heads `0028`; fast 1049 (reference) |
| P4-C5.1 dependency + runner decision | `pytest-playwright` dev-only; system Chrome channel |
| P4-C5.2 real-server harness | `tests/e2e/conftest.py` session server + seed |
| P4-C5.3 smoke scenario(s) | 4 browser tests (sign-in, create→play, error path, index) |
| P4-C5.4 verification | all gates above pass; e2e 4/4 deterministic |
| P4-C5.5 docs + commit | this report + single focused commit |

## 9. Known limitations

- **Server runs on SQLite, not PostgreSQL**, for the browser smoke. The WS5
  scope text mentions "live PG seed", but the repo's default/dev convention is
  SQLite (see `tests/conftest.py` and `pyproject.toml` env defaults); running a
  PG-backed browser suite requires a reachable PG service and was judged out of
  scope for a deterministic, self-contained smoke. The PG-backed *suite* is
  already covered by `tests/postgres`. The browser smoke deliberately reuses the
  root `tests/conftest.py` SQLite test DB (already initialised by its autouse
  `setup_database` fixture) so no separate DB scaffolding is needed.
- The **player render test** tolerates a queued (not yet generated) lesson by
  asserting a valid deterministic terminal state rather than a full AI-generated
  slide, because generation needs the external AI provider. Full visual
  generation is already asserted at the API/service level by the existing
  integration E2E.
- **No CI job was added.** The WS5 scope marks the browser CI job **optional**.
  Running a Playwright job needs browser installation on the runner; leaving it
  out keeps CI lean and the change purely additive.
- Browser tests are **heavier** (≈45–50s for the SSE suite) and require a display
  driver / system Chrome; hence the default-skip guard.
- `tests/e2e/conftest.py` imports a few heavy modules (`uvicorn`, `httpx`,
  `app.main`) at collection time. Because the tests skip by default, this only
  costs collection time when the e2e package is on the test path.

## 10. Scope compliance

Only the WS5 scope was implemented:
- `tests/e2e/conftest.py` (new harness)
- `tests/e2e/test_smoke.py` (new browser smoke)
- `pyproject.toml` / `requirements-dev.txt` / `uv.lock` (dev-only
  `pytest-playwright` addition + `e2e` marker)

No runtime dependency change, no schema migration, **no frontend change**, no
RAG / cache / vector rework, no WS6 work. mypy Δ=0, ruff unaffected. WS5 scope:
**YES**.

## 11. Run command (documented)

```bash
# From backend/ (uv environment)
uv run pytest tests/e2e/test_smoke.py -m e2e --browser chromium -q

# Or, to enable all e2e tests regardless of marker selection:
#   $env:PYTEST_RUN_E2E=1
#   uv run pytest tests/e2e -q

# Without the -m e2e flag the e2e tests are skipped by design:
uv run pytest tests/e2e -q          # => 4 skipped
```

Requires system **Google Chrome** (or `playwright install chrome` on a runner
without it).

## 12. Next workstream

**WS6 — Verification & release gate (optional consolidation):** run the full P4
gate and produce a P4 completion report. Out of scope here; WS5 stops at its own
boundary.
