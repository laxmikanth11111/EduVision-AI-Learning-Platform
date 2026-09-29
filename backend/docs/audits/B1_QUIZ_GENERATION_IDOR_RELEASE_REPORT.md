# B1 — Quiz-Generation IDOR — Release Report

> Milestone: **B1 — quiz-generation IDOR / authorization-boundary hardening** on
> `feature/individual-user-foundation` (baseline `f4d0a53`).

## What was implemented

Backend (`backend/app/services/quiz_generation_service.py`)

1. `generate_quiz` now loads the lesson through a new `_get_owned_lesson` helper
   instead of a raw `select(GeneratedLesson).where(public_id == …)`. Ownership is
   the lesson's parent presentation owner **or** the lesson's direct `user_id`,
   mirroring `MasteryTutorService._get_owned_lesson` byte-for-byte in the
   repository's established 404-equalization convention.
2. All non-owner shapes — missing lesson, orphaned presentation, soft-deleted
   presentation, cross-user lesson — now surface the **same**
   `404 NotFoundError "Lesson not found"` (previously cross-user generated a
   quiz from someone else's lesson with **201**, and a nonexistent lesson
   returned **422** `ValidationError`).

Rate-limit mapping (same path)

3. `RATE_LIMIT_ROUTES` previously budgeted `^/api/v1/presentations/[^/]+/quizzes$=10/60`,
   a route that does not exist, so generation fell through to the loose
   `RATE_LIMIT_DEFAULT` (100/60). Corrected to `^/api/v1/quizzes/generate$=10/60`
   so the expensive AI-generation path gets the tighter budget the config comment
   intends (`app/core/config.py`), with the parser docstring example updated
   (`app/middleware/rate_limit.py`).

Tests

4. New `backend/tests/unit/test_quiz_generation_security.py` — 11 discriminating
   tests (HTTP + service boundary). Pre-fix run: **7 failed / 4 passed** (the
   cross-user cases returned successful 201s); post-fix: **11 passed**.

## Verification (all `uv run --project .`, fresh test DB)

- Unit: **1624 passed** (integrated the B1 file).
- Integration: **216 passed** (incl. `test_two_user_isolation.py` 24).
- Targeted subtree (rate-limit, quiz-generation security, quiz routes, gateway
  injection guard): **75 passed**.
- `ruff check app tests`: clean.
- Changed-file secret scan: clean. No debug artifacts.

## Commit

Single atomic commit: `fix(quiz): enforce lesson ownership boundary on quiz generation`
(4 files: 3 app-file changes + new test file + this implementation report).
Tree clean afterwards. **Push: NO. PR: NO.**

## Known limitations

- Not-found status changed **422 → 404** (documented contract-equivalent for
  "cannot generate"; error shape unchanged).
- The 10/60 generation budget applies wherever `RATE_LIMIT_ENABLED` is on and
  `RATE_LIMIT_ROUTES` is not env-overridden.
- Quiz read/attempt authorization already enforced via `assert_quiz_ownership`;
  unchanged.

## Next milestone (recommended)

**F2 — session uniqueness** and **F4 — stale-write conflict detection**: detect
concurrent saves by version/ETag rather than last-write-wins (recording the next
candidate from the same deferred audit list).