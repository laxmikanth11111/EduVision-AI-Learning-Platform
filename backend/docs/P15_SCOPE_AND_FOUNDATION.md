# P15 Scope & Foundation — Persistent Lesson Resume & Learner Continuity

**Phase:** P15
**Branch:** `feature/individual-user-foundation`
**Previous:** P14 (Retention & Review Automation) — VERIFIED (see `POST_P14_PRODUCT_ARCHITECTURE_AUDIT.md`)
**Candidate selected:** A — Persistent Lesson Resume & Learner Continuity (weighted 459, ranked #1 of 9)
**Date:** 2026-09-06

---

## 1. Primary Capability

> **Persistent Lesson Resume & Learner Continuity ("Pick up where you left off")**
>
> When a learner leaves a lesson and returns, the platform restores them to the slide where they stopped — from **any entry point** (dashboard, deep-link, cold reload) — and the navigation loop is closed so that resuming is the obvious next step: the post-login hub links to the Dashboard, the player offers a completion CTA back to the Dashboard, and the Dashboard's lesson-progress rows carry working resume deep-links. The player persists the learner's **slide** (not just topic) position to the already-migrated `learning_sessions` row.

This is the only broken transition left in the connected learning spine (transition #17 — Return/Resume) and the only candidate that fixes an **explicit UI promise** (signin.html:55 "Pick up where you left off", dashboard.html:332 "click a lesson to resume"). It is deterministic, zero-AI, learner-scoped, and requires **no schema migration** (all resume columns already exist from migration `0009_learning_sessions`).

## 2. Foundation (existing, reused — no schema work)

| Piece | Where | State |
|---|---|---|
| `learning_sessions.current_slide_position` (int, default 0) | migration `0009_learning_sessions` + model `app/models/learning_session.py:106` | idle — no endpoint writes it today |
| `learning_sessions.current_block_position` | written by `LearningSessionService.set_topic/advance` | used for topic resume |
| `learning_sessions.completion_percentage` / `total_time_seconds` / `resume_version` | migration 0009 | present |
| `LearningSessionService.get_or_create` | `learning_session_service.py:94-137` | idempotent start/resume: same user+lesson → same session row |
| `LearningSessionService.set_topic` + `to_player_session` | `:139-156`, `:173-192` | persists topic, returns `topic_index` |
| `LessonPlayerService.start/set_topic/advance_topic` | `lesson_player_service.py:111-239` | authenticated path uses persistent sessions |
| Indexes `ix_learning_sessions_user_*` + `uq_learning_sessions_user_idempotency` | migration 0009:88-101 | resume lookup O(1) |
| Player slide model | `frontend/player.html:349-354` | slides = concept+visual pair per topic ⇒ `slide = topicIdx*2 (+0|+1)` |
| Lesson progress deep-link surface | `dashboard.html:332-348` | emits `player.html?lesson=` only (no resume position) |

**Conclusion: resume is a wiring closure, not a schema problem.**

## 3. Checkpoints & Acceptance Criteria

| Chk | Deliverable | Acceptance |
|---|---|---|
| C1 | Foundation: `LearningSessionService.set_position(session_id, user_id, slide_index)` clamps to `[0, total_slides-1]`, writes `current_slide_position`, updates `completion_percentage` = `(slide_index+1)/total_slides*100` and `last_activity_at`; serialize `slide_index` + `completion_percentage` through `to_player_session` | Unit: position persists, clamps, updates completion, returns None for foreign/missing session |
| C2 | API: `POST /lessons/{lesson_id}/player/position` (body `{session_id, slide_index}`) → `PlayerSessionResponse`; `LessonPlayerService.set_position(...)` resolves lesson → total slides → persists; dashboard `LessonProgressItem.resume_slide` + server-built `resume_link` (`player.html?lesson=..&slide=..`) | Integration: set/read round-trip; dashboard item carries resume fields; API 404-equalized cross-user; 422 on invalid body |
| C3 | Security: cross-user `position` write → 404 no-write (ownership), unauth → 401; `slide_index` bounded/clamped; no information leakage | Tests mirror P14 two-user isolation patterns |
| C4 | PostgreSQL: resume read/write against migrated `learning_sessions` on the real engine; Alembic single-head + ORM-parity unchanged | PG tests pass; `alembic heads` still `0033` |
| C5 | Frontend: player restores saved slide from session (via `/player/start` session payload `slide_index`; `?slide=` overrides); navigation sync posts `/position` (slide-accurate) instead of only `/set-topic`; final-slide completion CTA ("Finish → Dashboard"); sign-out link in player header; dashboard rows use `resume_link`; upload.html nav gains Dashboard link | Browser manual + E2E |
| C6 | Integration: player ↔ session table ↔ dashboard ↔ navigation loop consistent | Full suite green |
| C7 | Browser E2E: real resume journey (advance → navigate away → return → same slide), refresh persistence, cold-load deep-link, User A/B isolation | New `test_p15_resume_e2e.py`, full E2E suite green |
| C8 | Performance/observability: ≤1 UPDATE per debounced sync, no N+1 (progress already single-join), optional `p15_resume_*` metrics, log lines; lint/mypy-consistent | ruff clean; mypy ≤83 (no new); bounded work |
| C9 | Release regression: SQLite + PG + E2E + ruff + mypy + alembic + secret scan + docs + commit `feat(p15): ...` | All gates green, working tree clean |

## 4. Scope Boundaries (explicit non-goals)

- NO AI (any) is added. Position persistence is deterministic; no provider paths touched.
- NO schema migration. `learning_sessions` columns (migration 0009) are reused as designed; `resume_version` is only bumped (it exists; no new column).
- NO changes to quiz/assessment, mastery, review, analytics, tutor, or content-generation logic. `completion_percentage` provenance for the dashboard stays the same.
- NO video-render offload, no workspace/bookmarks, no retention trend-line, no platform-hardening fold — each is separately documented (deferred) in the P14 audit.
- The player's in-memory anonymous path is left functionally intact (its behavior is unchanged; the position write path only applies to authenticated persistent sessions).
- `tutor.html` refresh-token divergence, OAuth linking, uploads-mount auth, and the analytics-table gap are carried at their documented severity — they are NOT P15 scope (a later hardening phase owns them).

## 5. Security & Ownership Model

- All new DB writes go through `LearningSessionService.find_by_public_id(public_id, user_id=...)` which returns `None` for another user's session and for malformed prefixed ids — the established 404-equalized ownership pattern (same as P14 review).
- `user_id` is always derived from `get_current_user` (`str(user.id)`); clients only ever supply `session_id` + `slide_index`.
- `slide_index` is clamped against the lesson's current topic count * server-side; the frontend additionally clamps against `slides.length`. A stale or malicious index can never exceed the lesson.
- No stored HTML/SVG/JS: only integers + datetimes are persisted; nothing user-supplied is rendered back raw.
- Rate limiting: the position endpoint inherits the authenticated-route baseline (no new unbounded surface; debounced client writes).

## 6. Performance & Scalability Requirements

- Resume read: single indexed row (`ix_learning_sessions_user_lesson` path) — bounded O(1).
- Position write: single-row UPDATE inside the existing session service/UoW; client-side 400ms debounce (same as today's `set-topic`).
- Dashboard lesson progress: existing single join — resumes add zero extra queries (the resume link is computed from the already-loaded session row).
- Anchored player reads (start/loadLearnerJourney) unchanged and bounded.
- Observability: `p15_position_updates_total` optional counter; structlog info on resume (session restored with position); no PII.

## 7. Browser / E2E Verification Strategy

New `tests/e2e/test_p15_resume_e2e.py` following the P12/P14 seeding pattern (fresh SQLite + seeded `GeneratedLessonVersion` `status="succeeded"` with topic blocks so the player renders):

1. **Resume journey:** start lesson → navigate to a mid-deck slide (auto server sync) → navigate away → reopen `player.html?lesson=` → assert the restored slide equals the last visited slide.
2. **Refresh persistence:** on the same open page, `page.reload()` → same slide retained (from server session).
3. **Cold-load deep-link:** dashboard resume link (`?lesson=..&slide=N`) → player opens at N; a flag `?slide=` still overrides server position.
4. **User isolation:** User B opens the same lesson → starts at slide 0 (server holds no position for B); User A's position unchanged after B's visit.

## 8. Test-Matrix Expectations

| Layer | Expected result |
|---|---|
| SQLite unit/integration | all pass (1295 + new resume tests) |
| PostgreSQL (`-m postgres`) | all pass (30 + new resume/PG tests) + single-head guard |
| Browser E2E (`-m e2e`) | all pass (21 + new resume journey) |
| Ruff | clean (whole repo) |
| Mypy | ≤83 errors (P13 baseline), zero new |
| `alembic heads` | single head `0033_educational_memories` (unchanged) |
| `git diff --check` / secret scan | clean / no real secrets |

## 9. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Position sync racing navigation | Existing debounce pattern; single-row update; sync triggered from `goTo` (like `syncTopic` today); failures are best-effort non-blocking |
| Lesson version / topic count changes between visits | Server clamps to current slide count; out-of-range position → slide 0 (existing `startIndexFromUrl` behavior) |
| Regressing existing player/E2E flows | Resume only activates when the server session provides a slide position; `?slide=` override retained; full E2E suite re-run |
| Cross-user position leak | 404-equalized `find_by_public_id` + `user_id` from `get_current_user` only (P14 pattern, replicated + browser-verified) |
| mypy/ruff regressions | Changes are additive + typed; run both gates before commit |

## 10. Execution Order (C1 → C9)

1. `learning_session_service.py`: `set_position` + `to_player_session` slide fields
2. `schemas/player.py`: `slide_index` (+ `completion_percentage`) on `PlayerSessionResponse`; new `SetPositionRequest`
3. `lesson_player_service.py`: `set_position` (authenticated path) — resolve lesson → total slides
4. `api/v1/player.py`: `POST /lessons/{lesson_id}/player/position`
5. `schemas/learner_progress.py` + `learner_progress_service.py`: `resume_slide` + `resume_link`
6. Unit/integration + security tests (C3)
7. PG tests (C4) — position persistence on real engine
8. Frontend (C5): player.html (resume init, /position sync, completion CTA, sign-out), dashboard.html (resume rows), upload.html (dashboard link)
9. E2E (C7) + performance/metrics (C8)
10. Full regression → `P15_IMPLEMENTATION_REPORT.md` → commit `feat(p15): ...`