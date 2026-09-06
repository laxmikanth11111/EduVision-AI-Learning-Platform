# P16: Scope and Foundation — Asynchronous, Persistent, Learner-Owned Video Runtime

**Branch:** `feature/individual-user-foundation` · **Baseline:** `e81a61a` (P15 release-gated)
**Date:** 2026-09-06 · Primary capability: **A — Video Learning Runtime**

This document is the complete, implementable scope for P16. It contains the C0–C9
plan, the exact architecture (executor, render backend seam, DB model, service,
API, worker, frontend), the contract points with existing tests, and the release
gate. No further planning phase is required; implementation starts immediately
after this commit.

---

## 1. Problem statement (why P16)

Verified at baseline (see `POST_P15_PRODUCT_ARCHITECTURE_AUDIT.md` §1):

1. **Event-loop blocking:** `POST /api/v1/videos/create` (`video_router.py:110`) and
   `POST /api/v1/videos/{id}/render` (`:137`) call
   `video_renderer_service.render_video_mp4()` synchronously inside async handlers.
   The render is a per-frame PIL/OpenCV loop plus blocking `subprocess.run`
   FFmpeg/ffprobe calls (`video_renderer_service.py:70-81,119,133,146,170`). One
   render stalls the entire application (incl. `/health`) with no timeout,
   cancellation, or concurrency bound → authenticated DoS.
2. **No durability:** projects live only in an in-process `BoundedCache`
   (`video_router.py:35-37`; 500 entries / 1800 s TTL). Restart/eviction/scale-out
   orphans them.
3. **Fabricated data:** on cache miss `GET /videos/{id}` silently synthesises a fake
   "Computer Architecture" project and serves it HTTP 200 (`video_router.py:215-243`).
4. **Zero test coverage** on the whole render pipeline; 1,257 rendered `.mp4` files
   committed in `backend/uploads/`.
5. **No learner-facing UI** for the video runtime (no `frontend/videos.html`).

## 2. Objectives

- Offload rendering off the ASGI event loop (executor seam: `inline` for
  single-process/dev/tests, `celery` for scale-out), with deterministic status
  transitions and terminal failure state (`error`).
- Persist video projects as learner-owned rows (`video_projects`, ownership via
  `user_id`, isolation = 404-equalized; render requests verify ownership server-side).
- Bound concurrency per user (active render cap) and per test/suite (mock render
  backend), eliminating the CPU/disk DoS and CI bloat.
- Ship a working browser surface (create → render → watch) with status polling.
- Preserve the legacy `/api/v1/videos/*` contract that existing tests rely on
  (blueprint-shaped responses incl. `topic`/`timeline`/`validation`; 404 isolation),
  while routing renders through the new async executor so the event loop is never
  blocked.
- Extend observability: `p16_video_render_*` metrics + structlog events.
- Full regression: SQLite, PostgreSQL parity, browser E2E, ruff/mypy/alembic/secret
  scan/diff-check all green; mypy `83 / 24` zero-new; single Alembic head 0034.

## 3. Architecture

```
frontend/videos.html ──► /api/v1/video-projects/*   (new production router)
                                    │  persisting into video_projects (0034)
                                    ▼
                      VideoProjectService (state machine + concurrency cap)
                                    │
                    VideoRenderExecutor (seam by VIDEO_RENDER_EXECUTOR)
                      inline: asyncio.create_task(render_now)
                      celery: celery_app.send_task("eduvision.videos.render_project")
                                    ▼
                       VideoRenderBackend (seam by VIDEO_RENDER_BACKEND)
                      real:  VideoRendererService.render_video_mp4 (faststart)
                      mock:  deterministic tiny file, instant, test/E2E
```

Legacy `video_router.py` endpoints keep their shapes but call the same
`VideoProjectService` + executor (persist → defer → return blueprint). The fabricated
GET and the in-memory cache are retired.

### 3.1 Persistence — `video_projects` table (migration `0034_video_projects`)

| column | type | notes |
|---|---|---|
| `id` | UUID PK | `UUIDMixin` |
| `public_id` | String(40) UNIQUE idx | `vproj_<uuid4.hex[:16]>`, NOT NULL |
| `user_id` | UUID FK `users.id` ON DELETE CASCADE, idx | learner owner |
| `video_id` | String(64) | `video_<hex>` from composition engine; stable render/output name |
| `topic` | String(300) | human title |
| `status` | String(20) NOT NULL | `queued/rendering/ready/failed` |
| `progress_percentage` | Float NOT NULL default 0 | 0.0–100.0 |
| `playable_url` | String(500) NULL | set when ready (`/uploads/videos/…`) |
| `error` | String(1000) NULL | set when failed |
| `project_data` | JSON/JSONB NULL | blueprint `VideoProject.model_dump(mode="json")` for deterministic re-render |
| `created_at` / `updated_at` | `TimestampMixin` | |

Index: `ix_video_projects_user_status` on `(user_id, status)` for the concurrency
count and list surface. ORM model `app/models/video_project.py` (style:
`app/models/review_schedule.py`); register in `app/models/__init__.py`; request
validation reuses `app/schemas/video_projects.py` (strict, `extra="forbid"`).

### 3.2 Service — `app/services/video_project_service.py` (`VideoProjectService`)

Public async API (all owner-scoped):
- `create(user_id, topic, blueprint: dict | None, *, defer_render=True, session)` →
  persists row (`status=queued`), then dispatches via executor; returns record.
- `get_owned(user_id, project_public_id)` → record or **raise `NotFoundError`**
  (404-equalized: unknown vs foreign identical).
- `list_owned(user_id)` → newest-first list.
- `request_render(user_id, project_public_id)` → re-render a terminal project
  (ready → queued again; failed → queued); while active **raise `ConflictError`**
  (409); also enforces `VIDEO_RENDER_MAX_CONCURRENT_PER_USER` (409).
- `mark_rendering` / `mark_ready(playable_url)` / `mark_failed(error)` — state
  transitions used by the executor/task/tests.
- `render_now(record, project)` — deterministic single render execution (shared by
  inline executor, Celery task, and tests): calls the configured backend with a
  progress callback that flushes DB milestones, then flips `ready`/`failed`.
- `count_active(user_id)` — active `queued|rendering` count for the cap.
- Internal correctness: every dispatch verifies `record.user_id == user_id` before
  running; project JSON → `VideoProject.model_validate` → backend render.

`ConflictError`/`NotFoundError` already exist in the codebase (P10/P12 usage).

### 3.3 Executor — `app/services/video_render_executor.py`

- `executor = VideoRenderExecutor()` with `dispatch(user_id, project_public_id)`.
- Mode from `settings.VIDEO_RENDER_EXECUTOR`:
  - `inline`: `asyncio.create_task(self._run_inline(...))` — never awaited by the
    request; the task opens its own session, loads owner row, calls `render_now`.
  - `celery`: `send_task("eduvision.videos.render_project", args=[user_id, project_public_id])`
    (best-effort try/except; a dispatch failure marks the row failed).
- Module-level process-wide concurrency guard for `inline`: a per-user counting
  semaphore sized by `VIDEO_RENDER_MAX_CONCURRENT_PER_USER` is *not enough by
  itself* because the DB is the source of truth for the cap; the API-level count
  check (3.2) is authoritative and the executor re-checks on entry.

### 3.4 Render backend seam — `app/services/video_render_backend.py`

- `RenderResult` dataclass → `playable_url: str`, `error: str | None`.
- `RealFfmpegRenderBackend.render(project) -> RenderResult` — wraps the existing
  `video_renderer_service.render_video_mp4` (single small refactor: pass
  `progress: Callable[[float], None]`; call it per scene and at 100; use
  `video_renderer_service.UPLOADS_VIDEO_DIR`-relative output; keep
  `-movflags +faststart` and validation/fallback behaviour). All existing unit
  helpers (storyboard/script/subtitle/composition) untouched.
- `MockRenderBackend.render(project) -> RenderResult` — deterministic, instant,
  `playable_url="/uploads/videos/{video_id}.mp4"`, reports progress 25/60/90/100;
  **never invokes cv2/ffmpeg/audio**; used by tests/E2E via env
  `VIDEO_RENDER_BACKEND=mock`.
- Factory `get_video_render_backend()` reads `settings.VIDEO_RENDER_BACKEND`.

### 3.5 Celery task — `app/workers/video_tasks.py`

`video_render_task` (`bind=True`, `base=TaskWithDLQ`, `acks_late=True`,
`max_retries=0`) named **`eduvision.videos.render_project`**, registered in
`celery_app.include`; routing default → `videos` queue
(`task_routes` entry `"eduvision.videos.*"`). Body: fresh `UnitOfWork`/session,
load owner row (skip if missing/foreign), call `video_project_service.render_now`,
mark terminal state, structured logs. Tested directly via
`task.run.__func__(task, user_id, public_id)` (established pattern).

### 3.6 API — `app/api/v1/video_projects.py` (`video_projects_router`, prefix `/video-projects`)

| method | path | purpose | auth |
|---|---|---|---|
| POST | `/api/v1/video-projects` | create project: `{topic, description?, target_audience?, difficulty_level?, components?}` | `get_current_user` |
| GET | `/api/v1/video-projects` | list owned with statuses | `get_current_user` |
| GET | `/api/v1/video-projects/{public_id}` | get owned project | `get_current_user` \\
| POST | `/api/v1/video-projects/{public_id}/render` | (re)render | `get_current_user` |

Responses mirror legacy shapes for blueprint fields but add
`status`/`progress_percentage`/`playable_url`/`error_id`. Errors: 404 (`NotFound`)
unknown/foreign; 409 (`Conflict`) while active; 422 validation.

### 3.7 Legacy `video_router.py` refactor (contract-preserving)

- Shared blueprint builder factorised out (exists today as duplicated blocks in
  `/create`, `/storyboard`, `/script`).
- `/create` (201): build blueprint → `VideoProjectService.create(... defer_render=True)`
  → return `{"success": True, "data": <blueprint model_dump()> + "rendering_status":
  "queued", "playable_url": None, "project_public_id": …}`. Keeps
  `data["topic"]`, `data["timeline"]`, `data["validation"]` — all asserted by
  `tests/unit/test_video_engine.py` and `tests/integration/test_visual_generation_smoke.py`.
- `/{id}/render`: resolve owned project (404 otherwise) → `request_render` → return
  record dump (409 while active).
- `/{id}`, `/{id}/timeline|storyboard|metadata`: read from DB (no fabrication, no
  cache). On cross-user/unknown → 404 (isolation tests keep passing without the
  in-memory owner check).
- Retire `_VIDEO_PROJECT_CACHE`; `_get_owned_project` removed. Empty cache-fallback
  path (fake "Computer Architecture") deleted.
- `tests/unit/test_ws4_bounded_caches.py` still passes (tests `BoundedCache`
  mechanics, not the video cache).

## 4. C0–C9 implementation plan

- **C0 Baseline** — record gates: SQLite 1306, PG 34, E2E 24, ruff clean, mypy 83/24,
  alembic head `0033_educational_memories`, diff-check clean, `git status` clean at
  `e81a61a`. ✓ (captured at P16 start)
- **C1 Foundation + unit tests** — model + migration 0034 + repository + schema +
  service + executor + render-backend seam (+ config keys). Unit tests:
  `tests/unit/test_p16_video_projects.py` (state machine, cap, ownership/404,
  executor modes via patched `send_task`, backend factory, mock determinism) and
  `tests/unit/test_p16_video_render_task.py` (task success/failure/skip-foreign via
  `run.__func__`). Register metrics in `init_default_metrics`.
- **C2 API + integration tests** — `video_projects_router` + legacy router refactor +
  shared blueprint builder. `tests/integration/test_p16_video_projects_api.py`:
  create/list/get/render, cross-user 404, active 409, cap 409, terminal transitions,
  legacy `/videos/*` contract + isolation re-run. Update the 4 existing video tests
  to the async contract (queue-before-render, no fabricated data).
- **C3 Security** — owner checks in every service/execute path (server-side);
  `request_render` cap; schema bounds (`topic` ≤300, `components` ≤50); worker
  verifies ownership; output filenames derived from `video_id` only (no user input
  in paths); legacy endpoints size-limited identical to new router. `/uploads`
  unchanged (deliberate public media contract — carried).
- **C4 PostgreSQL** — `tests/postgres/test_p16_video_projects_pg.py`: migration
  0034 schema contract (columns, FK cascade on user delete, indexes), CRUD+status
  transitions, per-user cap, forged/foreign public_id → 404. "PG parity complete;
  no new schema risk."
- **C5 Frontend** — `frontend/videos.html` (vanilla JS): nav integration (index/
  dashboard/player links), create form, project list with status badges, poll
  `GET /video-projects` every 2 s while active, render/re-render button, `<video>`
  player wired to `playable_url`, error banner, 401 → authFetch refresh (match
  `tutor.html`/`dashboard.html` patterns and styling).
- **C6 Integration hardening** — E2E-level API flows in integration suite, idempotent
  re-render, failed-render path (mock backend forced to fail via env toggle),
  polling loop assertions, concurrent create safety.
- **C7 Browser E2E** — `tests/e2e/test_p16_video_projects_e2e.py`
  (`VIDEO_RENDER_BACKEND=mock` + `VIDEO_RENDER_EXECUTOR=inline` via
  `tests/conftest.py` env defaults set before app import): User A create → poll to
  ready → `<video>` present + src; render/re-render badge transitions; **User B
  cannot see or load User A's project** (fresh context, no shared cookies — per the
  P15-learned cookie/header rule). Add to the E2E suite marker flow.
- **C8 Performance / observability** — metrics `p16_video_render_starts_total`,
  `p16_video_render_completions_total`, `p16_video_render_failures_total`,
  `p16_video_render_concurrency_rejects_total`, histogram
  `p16_video_render_duration_seconds`; structlog `p16_video_render_started/
  completed/failed`; prove the request path no longer enters the renderer
  (grep/no-blocking-exit check + unit assertion that `dispatch` returns without
  awaiting render for `inline`); health endpoint unaffected.
- **C9 Full regression + gate** — SQLite 1306+new (unit → integration order),
  PG 34+new, E2E 24+new, ruff, mypy 83/24, alembic single head
  `0034_video_projects`, secret scan, `git diff --check`, report, commit
  `feat(p16): <capability>`.

## 5. Test-environment posture

- `tests/conftest.py` sets `os.environ.setdefault("VIDEO_RENDER_BACKEND", "mock")`
  and `VIDEO_RENDER_EXECUTOR="inline"` **before any `app.*` import** so settings
  resolve mock+inline for unit/integration/PG/E2E. This kills the 1,257-artifact
  render churn and makes suites fast/deterministic while the real backend stays the
  default in live config.
- The autouse `disable_celery_task_dispatch` fixture is extended with the video
  render task (`delay` patched → MagicMock) for tests that use the executor in
  `celery` mode; inline-mode tests use the real inline executor, which is guarded by
  the session factory patch in `tests/conftest.py`.

## 6. Risks and mitigations

- **Risk:** real-backend render still slow/artifact-heavy where used.
  Mitigation: real backend only for live usage; tests/E2E pinned to mock;
  faststart + progress callback; no per-frame DB writes.
- **Risk:** legacy contract drift breaking existing video tests.
  Mitigation: keep blueprint fields in create response; integration rewrite of the 4
  files is explicit (and removes 1,257-artifact churn); every legacy endpoint
  re-checked in C2/C6.
- **Risk:** inline background tasks racing session teardown in tests.
  Mitigation: state transitions are repository-driven and transaction-safe; tests
  that need the terminal state call `render_now` directly (deterministic).
- **Risk:** event-loop block anywhere else. Mitigation: C8 includes a repo-wide
  grep for `subprocess.run|Popen` in request-handler paths (expected result: only
  `video_renderer_service.py`, now reached only from executor/task/backend).
- **No new AI** in P16 (visual-intelligence description path stays an optional
  existing call on the create surface; components path is entirely deterministic).
- **No new dependencies** (uses existing `Celery`, `sqlalchemy`, `imageio_ffmpeg`,
  `cv2`, `PIL`).

## 7. Release gate (all must hold)

- `pytest tests/unit tests/integration` GREEN (≥1306 + P16 unit/integration).
- `pytest tests/postgres -m postgres` GREEN (≥34 + P16 PG tests) — PG reachable.
- `pytest tests/e2e -m e2e` GREEN (≥24 + P16 E2E).
- ruff clean (repo-wide); `python -m ruff format --check` on changed files.
- mypy `83 errors / 24 files` — **zero new**.
- Alembic single head `0034_video_projects`.
- Secret scan clean (P16 introduces no secrets; fixture password stays deterministic).
- `python -m compileall -q app tests` clean; `git diff --check` clean.
- Docs completeness: this scope + `POST_P15_*` + `P16_IMPLEMENTATION_REPORT.md`
  (25-section template), commit `feat(p16): async persistent learner-owned video runtime`.

Capabilities **DO-NOTED** for P16 (in the matrix for later phases): Adaptive
Assessment 2.0, Tutor/RAG 2.0 (incl. session-resume fix), Retention Automation,
Mastery Intelligence, Learning Workspace 2.0, Production Reliability hardening
bundle (CSRF, rate-limiter fail-closed, refresh-JTI reuse detection, `/uploads`
policy, analytics-table migration 0035+, dev JWT key).