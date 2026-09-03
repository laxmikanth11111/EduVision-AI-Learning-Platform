# P5 — Interactive Learner Journey — Implementation Report

## Status

**COMPLETE** — implemented on top of `205bd33` ("docs(p4): define post-p4
roadmap decision") as the P5 serisi of focused commits (C1–C5).

## 1. Objective

Implement the **P5 "Interactive Learner Journey"** phase in EduVision AI:

1. **Persistent per-user lesson progress** — a learner's position in a lesson
   survives refresh and is strictly scoped to the owning user.
2. **In-lesson assessment checkpoints** — surface whether the lesson has an
   assessment (a `Quiz`) and report past attempt/performance at that checkpoint.
3. **Assessment → mastery update** — reuse the existing
   `educational_memory_service` + `recommendation_engine` to derive the
   learner's concept mastery and a deterministic next learning action.
4. **Next-action recommendation** — deliver the mastery + recommended next
   action to the vanilla SPA player.
5. **Vanilla SPA integration** — render the learner-journey panel in
   `backend/frontend/player.html` without any frontend migration.
6. **Browser E2E verification** — skip-gated `tests/e2e` coverage following the
   `test_smoke.py` pattern.

### Constraints honored

- **Reuse/extend** existing capabilities (`LearningSession`, `Quiz`,
  `QuizAttempt`, `educational_memory_service`, `recommendation_engine`).
- **Single Alembic head** — no new migration was required.
- **Zero new mypy errors**, **Ruff clean**, `git diff --check` clean, secret
  scan clean.
- **PostgreSQL production + SQLite dev/test preserved.**
- **Bounded resources / no N+1** queries in the added paths.
- **No frontend migration.**
- Focused commits per checkpoint C1–C5 + this final report.

## 2. Design decisions (locked in)

| Decision | Rationale |
|---|---|
| `LearningSession` (table `learning_sessions`, migration 0009) is the persistent progress store | Existing durable, user-scoped model; **no new migration**. |
| `recommendation_engine.generate_recommendations(...)` is reused for next-action | Deterministic, mastery-driven (WEAK/DEF/ADV thresholds). |
| `EducationalMemoryService.load_from_db` reused for mastery | DB-backed concept mastery (`educational_memories`). |
| `Quiz` bound to a lesson via `lesson_id` = the assessment checkpoint | Existing association gives assessment lookup. |
| Active frontend = vanilla SPA in `backend/frontend/` | `EduVision_AI_Frontend/` is a duplicate/inactive copy; no frontend migration. |
| Anonymous/tooling path keeps `_SESSIONS` bounded in-memory cache | Honors WS4 six-cache contract + `test_ws4_bounded_caches` + integration teardown `_SESSIONS.clear()`; authenticated users persist via DB. |

## 3. Work performed

### C1 — Persistent per-user sessions

- **New** `backend/app/services/learning_session_service.py`:
  `LearningSessionService` with `find_for_lesson`, `find_by_public_id`,
  `get_or_create` (idempotent resume), `set_topic`, `advance`,
  `to_player_session`. All operations are user-scoped; missing records return
  `None` (404 at the API layer).
- `backend/app/services/lesson_player_service.py` rewritten to delegate the
  authenticated path to `LearningSessionService`, restoring the **anonymous /
  transient** path through the module-level `_SESSIONS: BoundedCache[str,
  dict]` (WS4 contract). Added `_load_accessible_lesson` (non-None return) to
  satisfy static narrowing; removed unused `QuizAttemptService` import.
- `backend/app/api/v1/player.py` start/advance/set-topic/get-state rewired to
  the persistent service.

### C2 — Assessment checkpoint

- `get_checkpoint(...)` added to `LessonPlayerService`.
- `list_by_lesson` added to `QuizRepository`.
- `GET /lessons/{lesson_id}/player/checkpoint` added in `player.py`
  (`APIResponse[dict[str, Any]]`); maps `PermissionError → 403` and
  `ValueError → 404`.

### C3 — Mastery + next action

- `get_mastery_and_next_action(...)` added to `LessonPlayerService`, reusing
  `educational_memory_service.load_from_db` + `generate_recommendations`.
- `GET /lessons/{lesson_id}/player/mastery` added in `player.py`, same error
  mapping.

### C4 — Vanilla SPA player integration

- `backend/frontend/player.html`:
  - `.lj-panel` CSS block + `#ljPanel` container in the sidebar.
  - `learnerCompletion` module variable set in `init()`.
  - `loadLearnerJourney()` + `renderLearnerJourney()` fetch `/checkpoint` +
    `/mastery`, rendering a lesson-progress bar, Assessment chip, and next
    action.
  - Removed a fabricated `quiz.html` dead link (no quiz UI exists); no
    `launchCheckpoint`.
  - Inline JS validated with `node --check`.

### C5 — Tests + verification

- **Unit:** `test_lesson_player_service.py` (persistent resume, cross-owner
  isolation, checkpoint), `test_player_routes.py` (checkpoint + mastery
  endpoints, mocked service), new `test_learning_session_service.py`.
- **Postgres (real PG via testcontainers):** `tests/postgres/test_learner_journey.py`
  — idempotent resume, persistence across advances, two-user isolation (3
  tests).
- **E2E (skip-gated, `-m e2e`):** `tests/e2e/test_learner_journey.py` — panel
  renders, checkpoint endpoint returns 200. Cannot execute in this environment
  (Playwright Python module not installed); documented limitation — correctly
  skips in the default suite.

## 4. Defect found & fixed (P5-facilitated)

While wiring the persistent path, the full fast suite surfaced a **latent
`LearningSession` model bug**: the `user_id`, `lesson_id`, and
`lesson_version_id` columns used the PostgreSQL-only
`sqlalchemy.dialects.postgresql.UUID` type, which corrupts UUID values when the
`learning_sessions` table is read through SQLite (dev/test) — surfacing as
`AttributeError: 'float' object has no attribute 'replace'` in `_python_UUID`.

**Fix:** `backend/app/models/learning_session.py` now uses the codebase-standard
`sqlalchemy.types.Uuid(as_uuid=True)` (same type as `UUIDMixin`/`AuditMixin`).
This is behaviour-identical in PostgreSQL DDL (native `UUID`) while round-
tripping correctly on SQLite. **No migration change** — verified with the real
Postgres test suite (migrations still apply cleanly; 15/15 pass).

## 5. Verification results

| Gate | Result |
|---|---|
| Fast suite `-m "not postgres and not e2e"` | **1062 passed, 0 failed** (was 8 failed + 28 ERROR before the `_SESSIONS` + model fixes) |
| PostgreSQL suite `-m postgres` | **15 passed** (real PG migrated via testcontainers), incl. 3 learner-journey |
| Browser E2E `-m e2e` | Skip-gated; cannot run locally (no Playwright module) |
| Ruff `app/ tests/` | **All checks passed** |
| mypy `app/` | **83 errors** (baseline 85; **zero new**, and the endpoint-narrowing fix removed 2) |
| `alembic heads` | **Single head** `0028_ws10_idempotency_key_index` |
| `git diff --check` | clean |
| Secret scan | no secrets in authored files (matches only in pre-existing `test_production_readiness.py` placeholders) |

## 6. Commits (checkpoint sequence)

- **C1** — persistent per-user lesson progress + anonymous bounded path.
- **C2** — assessment checkpoint lookup + endpoint.
- **C3** — mastery + next-action endpoint.
- **C4** — vanilla SPA learner-journey panel.
- **C5** — unit/postgres/e2e tests + this report + P5-completion doc.

## 7. Environment limitations

Browser E2E cannot be executed here because the Playwright Python module is not
installed (`pytest_playwright: False`). Tests are authored and skip-gated
(`-m e2e`), matching the existing `test_smoke.py` pattern, so they remain valid
CI artifacts for an environment that has Playwright provisioned.
