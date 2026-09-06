# Post-P15 Product Architecture Audit

**Phase:** P16 pre-planning audit
**Branch:** `feature/individual-user-foundation`
**Baseline commit inspected:** `e81a61a` (P15 final, release-gated)
**Audit date:** 2026-09-06
**Companions:** `POST_P15_CAPABILITY_MATRIX.md`, `P16_SCOPE_AND_FOUNDATION.md`

This audit establishes the exact state of the architecture as at the end of P15 so
the P16 selection is grounded in evidence rather than assumption. Every claim below
was verified directly against source in this session; where a carried item from
earlier audits (P12/P13/P14/P15 reports) turned out to be **different in reality**,
that is called out explicitly.

---

## 1. Headline finding (P16 selection)

**The video-rendering path is the single most severe reliability defect in the
codebase, and it has zero automated coverage.**

Three concrete defects were verified in `backend/app/services/video_renderer_service.py`
and `backend/app/api/v1/video_router.py`:

1. **Event-loop blocking in the request path.** `POST /api/v1/videos/create`
   (`video_router.py:110`) and `POST /api/v1/videos/{video_id}/render`
   (`video_router.py:137`) call `render_video_mp4()` **synchronously inside async
   handlers**. That function runs a *per-frame* PIL/OpenCV draw loop
   (`video_renderer_service.py:70-81`) followed by blocking `subprocess.run(...)`
   FFmpeg calls (`:119`, `:133`, `:146`, `:170`). A single render stalls the whole
   ASGI event loop — including `/health` and every other learner request — for the
   full render duration, with no timeout, no cancellation, and no per-user or
   global concurrency bound. An authenticated user can trivially DoS the server by
   issuing concurrent renders.
2. **No durable persistence.** The only "store" is an in-process
   `BoundedCache` (`video_router.py:35-37`, max 500 entries, 1800s TTL). On restart,
   eviction, or horizontal scale-out the project is orphaned; `GET /{video_id}`
   (`:215-243`) then **silently fabricates a fake default "Computer Architecture"
   project** for any unknown id — a data-integrity bug (wrong content, wrong owner,
   wrong everything) served with HTTP 200.
3. **Zero test coverage.** `grep render_video_mp4|video_renderer|VideoProject` under
   `backend/tests` finds **no renderer test at all**, while 1,257 rendered `.mp4`
   files and 81 audio files are committed under `backend/uploads/` — i.e. the heavy
   pipeline has been executed repeatedly (via smoke/demo tests and ad-hoc scripts)
   but never asserted.

**P16 addresses this as candidate A "Video Learning Runtime": an asynchronous,
persistent, learner-owned, concurrency-bounded video lesson engine.** This is also
the relief for the carried HIGH/PRODUCTION item "synchronous video render via
blocking subprocess calls" that appeared in the P13/P14/P15 audits.

Carried item correction: earlier audits labelled the videos surface
"experimental, no owner model". Verified reality: owner isolation exists structurally
(enforced per-request via `BoundedCache` owner match → 404 elsewhere for cross-user),
ownership tests exist in `tests/integration/test_two_user_isolation.py:415-499`, but
isolation rests on the fragile in-memory cache + fabricated-on-miss behaviour, not on
the database.

---

## 2. Audit method

Evidence was gathered by direct source inspection of `backend/app` and
`backend/tests` plus the P12–P15 audit/scope/report documents. Coverage spanned:
retention/review+mastery, adaptive assessment, tutor/RAG + AI seam + dead config,
plans/goals/paths, analytics, media engines (video/animation/simulation), auth and
JWT, middleware (rate limit/CSRF), static mounts, worker/Celery/beat, settings,
metrics, PG parity, and the browser surface (`backend/frontend/*.html`). Confirmed
baseline gates (re-run this session): ruff clean, mypy `83 errors / 24 files`
(= P15 baseline, zero new), single Alembic head `0033_educational_memories`,
`git diff --check` clean, clean tree at `e81a61a`.

---

## 3. Product-loop observation

The closed learning loop now reaches throughout the product:

```
content (upload → presentation/lesson) → learn (slide player,
resume: P15) → assess (adaptive quiz: P12) → master (P10/P13 memory +
analytics) → retain (spaced review: P14) → plan/goal (P11) → tutor
(RAG: P4/P8) → [video runtime — NOT looped in]
```

The only headline product surface with **neither persistence, nor learner-facing
browser UI, nor tests, nor safe execution** is the video engine. Closing that gap is
a loop-completion move (create a visual mini-lesson → watch it in the browser →
resume into the player): it reuses the mature composition/script/storyboard/scene
model, the `/uploads` playable-media serving (already wired for `<video>`), and the
P15 slide-resume groundwork, while removing the worst event-loop risk and a real
data-integrity bug.

---

## 4. Per-area audit findings

### 4.1 Retention (P14) / Mastery (P10/P13) — audit
- Mastery is per-concept inside the `educational_memories.memory_data` JSON blob
  (`backend/app/models/educational_memory.py:33-50`); quiz feedback is the only
  writer (`quiz_attempt_service.py:_update_concept_mastery`, applied at `:1073`);
  review completion deliberately does not mutate mastery (`retention.py` helpers are
  pure; `ReviewScheduleService.complete` → `record_review_activity` only resets the
  clock).
- Spaced repetition is a **deterministic fixed ladder** `(1,3,7,14)` days
  (`review_scheduler.py:29`) modulated by a 4-outcome step (`again/hard/good/easy`)
  — not adaptive/ML. Next schedules are created **lazily on read** (`list_due →
  _ensure_schedules` `review_schedule_service.py:254-306`).
- `review_schedules` = real table + PK/FK/index set (migrations `0011`, `0031`).
- **No background automation**: no Celery review/reminder task, no beat entry, no
  overdue sweeper; re-engagement is request-driven only (`GET /me/review`,
  `GET /me/plan/today`). Retention surface
  (`GET /me/analytics/retention`) classifies overdue/at_risk/on_track on read.
- Verdict: capability COMPLETE (manual surface), automation MISSING. Appropriate
  future phase; not P16.

### 4.2 Adaptive assessment (P6/P12) — audit
- Engine is `app/services/adaptive_assessment.py` — pure, deterministic selector
  (band→difficulty target, within-attempt ±1 concept deltas, stable ordering tuple).
- Questions **are persisted** (`quizzes`, `questions`, `question_options`,
  `quiz_attempts.adaptive` via migration `0032`); adaptive delivery reorders a
  fixed bank; no on-the-fly generation, no early exit, no time or confidence
  adaptivity, single `concept_id` per question. Rationale describes only the last
  answer.
- `questions.meta` JSONB already carries `tags`/`knowledge_area` (unconsumed).
- Verdict: COMPLETE core, obvious 2.0 growth paths (skills dimension, early exit,
  time/confidence) — most have no schema migration need. Compelling next product
  feature; **did not win the weighted table** (see `POST_P15_CAPABILITY_MATRIX.md`)
  because P16's highest-severity gap is the video runtime, and only one primary
  capability may be selected per phase.

### 4.3 Tutor / RAG (P4/P7/P8) — audit
- Persistence EXISTS (`tutor_sessions`, `tutor_conversations`, `tutor_messages`,
  migrations `0013` + `0029`); learner-scoped retrieval (cosine over ≤200 embedded
  rows, threshold 0.3, top-k 8, positional fallback); deterministic offline fallback
  (`source_kind="deterministic"`); 9 auxiliary tables (`tutor_citations`,
  `tutor_contexts`, …) exist **schema-only**, un-consumed.
- Verified real bug: `frontend/tutor.html:resumeSession()` passes a **session**
  public id where the API expects a **conversation** public id, so conversation
  history fails to reload between page loads.
- **Inert guardrail confirmed**: `TUTOR_INJECTION_FLAG_THRESHOLD` and the five
  hallucination/groundedness knobs (`config.py:221-238`) have zero consumers —
  matches P12/P13/P14 audits (prompt-injection guard deferred every phase).
- Streaming EXISTS at provider layer (`AIContentService.stream`, Gemini/OpenAI SSE)
  but the tutor endpoint is request/response; frontend has no `EventSource`.
- Verdict: PARTIAL/COMPLETE with distinct 2.0 work; tutor resume fix is a candidate
  P16 C-item; full Tutor 2.0 (streaming+citations+summaries+guardrail) is a future
  phase.

### 4.4 Study plans / goals / paths (P11) — audit
- `plan.py` (GET `/me/plan/today`, POST complete), `goals.py`, `path.py` routers;
  deterministic Today plan composes due reviews. Working; no outstanding high-severity
  gap. Verdict: COMPLETE for current scope.

### 4.5 Analytics (P13) — audit
- On-the-fly computation (attempts, trends, concepts, effort, retention view).
- **Latent schema defect verified (carried, MED):** `LearningAnalyticsSnapshot`,
  `CreatorAnalyticsSnapshot`, and `SystemAnalytics` (`app/models/analytics.py`) have
  **no Alembic CreateTable**; `0022` only renames legacy names; `system_analytics`
  appears in zero migrations. Currently dead code (nothing writes them) — a future
  migration must add them. (Earlier audits' named `LearnerSegment`/`StudyBehavior`/
  `ProgressEvent` models **do not exist**.) Not a P16 blocker.

### 4.6 Security — audit
- **OAuth linking: FIXED.** `auth.py:321-330` links a same-email Google account onto
  the existing password row via `users.google_id` (no orphan duplicate on the normal
  path). Residuals: unverified-email trust; `MultipleResultsFound` race is
  theoretical (both columns unique).
- **Refresh JTI revocation: PARTIAL (carried).** Logout adds the refresh `jti` to a
  Redis/in-memory blacklist checked on refresh; **no rotation/reuse-detection** — a
  stolen un-revoked refresh token stays valid for 7 days.
- **Rate limiter: PARTIAL (carried, fail-open).** Enabled app-wide incl. auth, but
  `rate_limit.py:157-159 / 207-211` return `call_next` on Redis/exception —
  **fails open**; `127.0.0.1` whitelisted in dev.
- **CSRF: STILL PRESENT.** `generate_csrf_token/validate_csrf_token`
  (`security.py:138-143`) and `CSRF_*` settings are dead; no CSRF middleware; only
  SameSite=Lax hardening. Carried MED.
- **`/uploads` mount: STILL PRESENT (carried MED).** `main.py:181-183` mounts
  `uploads/` with zero auth; video/audio/media all served anonymously (deliberate —
  asserted by `tests/integration/test_uploads_mount.py`). P16 keeps this contract;
  hardening is a separate carried phase.
- **JWT/cookies: CONFIGURED, weak in dev.** 15-min access / 7-day refresh, HS256,
  Secure+Lax HttpOnly cookies; but `.env` sets neither signing key, so JWTs fall
  back to the hardcoded `CHANGE-ME…` default (`security.py:38-39`) outside
  production validators. `.env` also contains committed live-looking
  `GOOGLE_*`/`AI_API_KEY` secrets.

### 4.7 Media engines — audit
- **Video runtime (4K.3/4K.4):** `/videos/runtime/*` sync/bookmark/assessment/
  tutor-context surfaces are **in-memory only** (bounded caches); learner-owned
  checks exist; nothing persists. Fine for now; P16 moves the *project+render*
  lifecycle to the DB, not these runtime helpers.
- **Animation / simulation / visual canvases:** exist as domains with routers and
  isolation tests; no high-severity findings this audit.

### 4.8 Performance / reliability — audit
- The only **blocking subprocess in the request path** is the video renderer
  (`subprocess.run` at `video_renderer_service.py:119,133,146,170`) — see §1. No
  other `subprocess.{run,Popen,...}` occurs anywhere in `app/`.
- **Real renderer writes 1,257 + 81 binary artifacts** that are currently committed
  to the tree under `backend/uploads/` — repo bloat directly caused by sync-render
  demo flows; async + mock-backend tests reduce future churn.

### 4.9 Worker / Celery — audit
- Rich infra EXISTS: `TaskWithDLQ` base, `acks_late=True`, idempotency module,
  routing map, beat schedule (`celery_app.py:69-106`), well-tested pattern
  (`task.run.__func__(...)` in `tests/unit/test_lesson_generation_worker.py:11`).
  **No video render task today**; P16 adds one (`eduvision.videos.render_project`).

### 4.10 Frontend (vanilla MPA) — audit
- Pages: `index.html`, `dashboard.html`, `player.html`, `tutor.html`, `upload.html`,
  `processing.html`, `signin.html`, `signup.html`. **No videos page exists** — the
  video engine is API-only. P16 introduces `frontend/videos.html` (create/list/
  render/watch) reusing the established `authFetch`/token-refresh pattern and nav
  styling.

### 4.11 Content intelligence — audit
- Lesson/quiz generation via AI seam with persisted outputs and background lesson
  generation; no high-severity gaps. Not P16.

---

## 5. Error / strictness posture

- `CompileError`? No — this codebase uses `404`-equalized ownership errors
  (`NotFoundError`), `ConflictError` (409) for attempt/capacity guards, and
  Pydantic-schema request validation. P16 follows the same conventions (404 for
  cross-user/unknown project, 409 for concurrency-cap violations/defer-during-active).
- Execution tools update the activator — no destructive git recovery; the tree is
  clean at `e81a61a` throughout.

---

## 6. P16 selection rationale

Primary capability **A — Video Learning Runtime** (score 83/100, top of
`POST_P15_CAPABILITY_MATRIX.md`). Justification: it (1) removes the highest-severity
production defect (event-loop blocking, no concurrency bound) that every audit since
P13 has carried as HIGH; (2) fixes a genuine data-integrity bug (fabricated projects)
and an isolation weakness (identity resting on an in-memory cache); (3) closes a
product loop the learner cannot reach today (visual mini-lessons have no browser UI);
(4) is fully implementable without further planning (single additive table +
deterministic state machine + existing renderer/binary + existing frontend patterns);
(5) is verified end-to-end in-browser (create → render → watch) and across
SQLite/PostgreSQL ownership semantics.

Capabilities DO-NOTED for P16 (kept on the matrix for later phases):
Adaptive Assessment 2.0 (skills/early-exit/time/confidence), Tutor/RAG 2.0
(streaming, citations, session-resume fix, injected-guardrail consumer),
Retention Automation (background scheduling/reminders), Mastery Intelligence
(adaptive intervals), Learning Workspace 2.0 (dashboard consolidation), Production
Reliability hardening bundle (CSRF wiring, rate-limiter fail-closed, refresh-JTI
reuse detection, `/uploads` access policy, analytics table migration, dev JWT key).