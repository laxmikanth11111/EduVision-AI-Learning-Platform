# P16 — AI-Powered Video Learning Runtime (Candidate A)

**Status:** Shipped · **Branch:** `feature/individual-user-foundation` · **HEAD:** after `e81a61a` (P15)

Async, persistent, **learner-owned**, concurrency-bounded video rendering. Replaces the
blocking on-create pipeline with a durable per-user render pipeline, a real MP4 renderer
behind a backend seam, an inline/celery executor seam, a bounded per-user concurrency cap,
timeout-protected rendering, and a learner-only API + SPA.

---

## 1. Outcome vs. old behaviour

| Old (`video_router.py`) | New (`P16`) |
|---|---|
| Blocking `render_video_mp4(...)` on every create | Async pipeline: `queued → rendering → ready/failed` |
| Fabricated/cached result fallback on render error | 403/404 on absent blueprint; FAILED status with stored error |
| No persistence of the render job | `video_projects` table (migration `0034`) |
| Any update could clobber the single learning section | Set pipeline reads `learning_sections`; creates its own row |
| No ownership scoping | `user_id` FK; every endpoint filter-scoped; cross-user 404 |
| No concurrency guard | Per-user cap of 1 active render (configurable), 409 + metric on reject |
| No timeout | `asyncio.wait_for` + `asyncio.to_thread` around the real renderer |
| Global-ish logging | `get_logger` with structured context throughout the pipeline |

Legacy blueprint contract on `POST /api/v1/video_projects` **preserved**: it still returns
`data` with `project_public_id`, `rendering_status=queued`, `playable_url=null` alongside the
new persistent record; `GET /api/v1/video_projects/most-recent` now returns the persisted
project instead of a fabricated one.

---

## 2. Architecture (Candidate A)

```
POST /api/v1/video_projects            ──► project_service.create()          (409 cap check)
GET  /api/v1/video_projects            ──► repository.list_by_user()
GET  /api/v1/video_projects/{public_id} ◄── repository.get_by_public_id(user-scoped)
POST /api/v1/video_projects/{id}/render ─► project_service.request_render()   (409 if active, 404 if foreign)

video_render_executor (seam: VIDEO_RENDER_EXECUTOR)
 ├─ inline (default)  ──► asyncio.create_task(_run_render)      → async-io safe
 └─ celery            ──► send_task("eduvision.videos.render_project")

video_render_task (celery) ──► project_service.render_now()
  ▲ project = _rebuild_project(...)   ← None → fail fast RuntimeError("video blueprint is missing or invalid; re-create the project")
  ▲ wait_for( to_thread( backend.render(project, progress_cb) ), timeout )

video_render_backend (seam: VIDEO_RENDER_BACKEND)
 ├─ real │ wraps render_video_mp4(progress_callback=...) → writes uploads/videos/{video_id}.mp4
 └─ mock │ writes a small MP4 stub + milestone progress (test hook)

VideoProject model: public_id `vproj_<hex16>`, video_id `video_<hex10>`,
  user_id FK → users.id (CASCADE), topic, status, progress, playable_url,
  error, project_data JSON/JSONB, optimistic-lock `version`.
```

### Executor / backend rules
- `VIDEO_RENDER_EXECUTOR` ∈ `{inline, celery}`; `VIDEO_RENDER_BACKEND` ∈ `{real, mock}`.
- `render_now()`: load fresh record (`with_for_update`), set `rendering` + progress 10 and
  **commit before** the to_thread so a concurrent poller never sees a stale row.
- `asyncio.wait_for(asyncio.to_thread(...), VIDEO_RENDER_TIMEOUT_SECONDS)` → TimeoutError ⇒ FAILED.
- `progress_callback` runs on the worker thread and writes progress to the DB (thread-safe via
  its own session); engine pool applies to every committed write.
- Metrics: `p16_video_render_starts_total`, `_completions_total`, `_failures_total`,
  `_concurrency_rejects_total{reason}`, `_duration_seconds{outcome}` histogram — visible over
  `GET /api/v1/metrics` (verified: `# HELP p16_*` lines render with labels/buckets).

### Service invariants
- `create()` and `request_render()` enforce the per-user cap **before** queueing → 409.
- Unknown *or other-user* public_id → 404 (no ID oracle).
- `request_render` on `ready/failed` without `force` → 409; `force` re-renders.
- `status` transitions validated by a `CHECK` constraint mirroring `VideoRenderStatus`.

---

## 3. Migration note (PostgreSQL)

`app/database/base.py` metadata `convention` names constraints with **printf-style** tokens
(`"pk": "pk_%(table_name)s"`). `0034_video_projects.py` must interpolate those tokens with
`%` (`convention["pk"] % {"table_name": TABLE}`, `convention["fk"] % {…}`) — not `.format()`,
which leaves the literal token in the generated name and collides with the identical literal
name produced by `0033_…` on Postgres (`DuplicateTableError: relation "pk_%(table_name)s"
already exists`). Historical `0033` was left untouched. Head is now `0034`.

---

## 4. Test matrix

| Suite | Command | Result |
|---|---|---|
| SQLite unit + integration | `pytest tests/unit tests/integration` | **1327 passed** |
| PostgreSQL | `pytest tests/postgres` | **40 passed** |
| E2E (browser) | `pytest tests/e2e -m e2e` | **26 passed** |
| Ruff | `ruff check .` | clean |
| Mypy (P16 files) | mypy on touched modules | zero new errors (worker decorator + pre-existing cv2 tolerated, matching `tasks.py`) |
| Whitespace | `git diff --check` | clean |

### New/updated tests
- `tests/unit/test_p16_video_projects.py` — status checks, progress range, cap, ck constraint.
- `tests/unit/test_p16_video_render_task.py` — task wiring/mocking.
- `tests/integration/test_p16_video_projects_api.py` — endpoints, celery run round-trip, 401
  auth, legacy contract, cross-user isolation.
- `tests/integration/test_two_user_isolation.py` — seeded two-user JWT isolation (seed fixture
  now commits after flush to satisfy the `user_id` FK).
- `tests/postgres/test_p16_video_projects_pg.py` — head, table/constraints/index/JSONB, cap &
  conflict, lifecycle round-trip under real Postgres, cross-user equalize.
- `tests/postgres/test_migrations.py` + `test_p12/13/14/15_pg.py` — head assertions 0033→0034.
- `tests/e2e/test_p16_video_projects_e2e.py` — full UI create→ready→play loop and learner
  isolation across two fresh browser contexts. Tests are sync `def` (pytest-playwright's page
  is sync; `async def` raises `Runner.run() cannot be called from a running event loop`).

### E2E auth nuance (important for future isolation tests)
The root `tests/conftest.py` installs an **autouse** `get_current_user` override (every
authenticated request resolves to the fake `TEST_USER_ID`) so unit/integration endpoints work
without JWT churn. The E2E server shares that same app object, so without suppressing the
override **every** browser login would map to the same fake user and a cross-user leak test
becomes vacuous. `05`-style isolation tests must pop
`app.dependency_overrides[get_current_user]` (see `_use_real_auth()` in the P16 E2E module) to
make login cookies/Authorization real identities; the autouse fixture re-installs it per test.

---

## 5. Scope guardrails (DO-NOTED)
Out of scope and left untouched: Tutor/RAG 2.0 (+ pre-existing `tutor.html:resumeSession()`
id bug), Retention Automation, Mastery Intelligence, Workspace 2.0, Production Reliability
bundle, Adaptive 2.0. No new third-party dependencies were introduced (ffmpeg stays the
bundled v7.1 runtime; TTS stays enabled by default).

## 6. Next steps
- Full regression re-run before each release gate (the values in §4 are from this commit's runs).
- Phase-honour roadmap: production reliability bundle then adaptive 2.0; do not refactor before
  the board reflects this UI runtime as shipped.