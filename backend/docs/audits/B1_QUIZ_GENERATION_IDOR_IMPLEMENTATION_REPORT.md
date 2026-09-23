# B1 — Quiz-Generation IDOR (audit + fix)

> Milestone: **B1 — quiz-generation IDOR / authorization-boundary hardening** on
> `feature/individual-user-foundation` (baseline `f4d0a53`).
> Classification vocabulary: **IMPLEMENTED / VERIFIED / PARTIAL / BLOCKED /
> NOT APPLICABLE**.

## A. Objective

`POST /api/v1/quizzes/generate` asks the AI provider to generate a knowledge-check
quiz from an arbitrary lesson identified by `lesson_id` (a UUID public id). The
endpoint must refuse to generate a quiz from a lesson the authenticated user does
not own, and the denial must not leak whether a cross-user lesson exists.
This closes the **B1** audit candidate recorded in
`NEXT_MILESTONE_IMPLEMENTATION_REPORT.md` (§I, item 2) and
`F1_LEARNING_MODE_COMPLETION_RELEASE_REPORT.md` (§J).

## B. Root cause (VERIFIED, exploited)

`QuizGenerationService.generate_quiz` loaded the lesson with:

```python
lesson_stmt = select(GeneratedLesson).where(GeneratedLesson.public_id == lesson_public_id)
```

No ownership check. `user_id` was only used to *stamp* the created rows; the AI
call consumed whatever lesson content the caller named. The single entry point
(`app/api/v1/quiz.py`) authenticated the caller but never authorized the target
resource — exactly the "AUTHENTICATION != AUTHORIZATION" case.

Pre-fix (.venv backend, fresh test DB, `_call_ai` stubbed to a valid payload):

| Invocation | Observed | Expected |
|---|---|---|
| User B calls `generate_quiz` with User A's lesson (HTTP) | **201** — quiz created and persisted from lesson A | 404 |
| Same, via service directly | **no error raised**, quiz persisted | `NotFoundError` (404) |
| Orphaned lesson (presentation with no owner) | **201** | 404 |
| Lesson under a soft-deleted presentation | **201** | 404 |
| Nonexistent `lesson_id` | **422** `ValidationError` | 404 (equalized) |

Probing evidence ran exactly as: cross-user → `201 == 404` assertion failure;
service-level cross-user → `Failed: DID NOT RAISE NotFoundError`. The harness
proves the authorization flow because the stub short-circuits only the external
AI API call; every query, validation, and persistence step on lesson A ran to
completion for user B.

## C. Fix (IMPLEMENTED)

`backend/app/services/quiz_generation_service.py`:

- Added `_get_owned_lesson(user_id, lesson_public_id)` returning the lesson when
  the caller owns it via its parent presentation owner **or** the lesson's direct
  `user_id`, and raising **404-equalized** `NotFoundError` (`"Lesson not found"`
  with `details={"lesson_id": ...}`) otherwise.
- `generate_quiz` now loads the lesson through `_get_owned_lesson`; the raw
  `select(GeneratedLesson)` — with no owner predicate — is removed.
- Imported `NotFoundError` and `Presentation`.

Conformity: the helper mirrors `MasteryTutorService._get_owned_lesson`
(`app/services/mastery_tutor_service.py:894`) exactly — same ownership unit
(presentation `owner_id` non-null, presentation not soft-deleted, owner matches;
OR lesson `user_id` matches) and the same 404-equalized error for missing /
orphaned / soft-deleted / cross-user lessons. `assert_quiz_ownership`
(`quiz_attempt_service.py`) uses the same presentation-owner convention. No
schema/migration change; no frontend change (no consumer exists).

Rate-limit mapping (same path, per milestone scope): `app/core/config.py`
`RATE_LIMIT_ROUTES` overrode quiz generation via
`^/api/v1/presentations/[^/]+/quizzes$=10/60` — a route that does not exist in
the API (the only quizzes router is `APIRouter(prefix="/quizzes")` in `quiz.py`),
so generation silently fell back to `RATE_LIMIT_DEFAULT = 100/60` despite the
config comment stating the expensive AI path gets a tighter budget. Corrected to
`^/api/v1/quizzes/generate$=10/60`; the docstring example in
`app/middleware/rate_limit.py` was updated to match. Applies wherever
`RATE_LIMIT_ENABLED` is on and `RATE_LIMIT_ROUTES` is not env-overridden.

## D. Semantics (VERIFIED)

- Owner via presentation owner (single top-level ownership unit): allowed.
- Owner via lesson `user_id` (legacy/edge data): allowed.
- Cross-user lesson: 404 `"Lesson not found"`, no `Quiz` rows written.
- Orphaned presentation (`owner_id IS NULL`) or soft-deleted presentation: 404.
- Nonexistent `lesson_id`: 404 — **behavior change** from the prior
  `422 ValidationError`, conforming to every other lesson endpoint in the
  repository. No existing test asserted the 422.
- The four denial shapes are byte-for-byte identical in `code` and `message`, so
  the endpoint leaks nothing about cross-user resource existence.

## E. Regression evidence (VERIFIED, discriminating tests)

New file `backend/tests/unit/test_quiz_generation_security.py` — 11 tests,
HTTP + service level, every denial assertion proven to fail against the old
code and pass against the fix:

| Test | Old code | Fixed |
|---|---|---|
| `test_owner_generates_quiz_from_own_lesson` (HTTP) | pass | pass |
| `test_owner_generated_quiz_bound_to_owner` (HTTP + DB) | pass | pass |
| `test_service_allows_owner` | pass | pass |
| `test_service_owner_via_lesson_user_id` | pass | pass |
| `test_cross_user_cannot_generate_quiz_from_other_lesson` (HTTP) | **fail — 201** | pass |
| `test_cross_user_error_identical_to_missing_lesson` (HTTP) | **fail — 201** | pass |
| `test_orphaned_lesson_returns_404` (HTTP) | **fail — 201** | pass |
| `test_deleted_presentation_lesson_returns_404` (HTTP) | **fail — 201** | pass |
| `test_service_rejects_cross_user_lesson` | **fail — no raise** | pass |
| `test_service_rejects_missing_lesson` | **fail — 422 vs 404** | pass |
| `test_missing_lesson_returns_404` (HTTP) | **fail — 422 vs 404** | pass |

Pre-fix run summary: `7 failed, 4 passed`. Post-fix: `11 passed in ~10s`.

## F. Tests added (11 total)

- **Unit** (`tests/unit/test_quiz_generation_security.py`): owner HTTP happy path
  + persisted row binding checks; cross-user HTTP 404 denial with zero `Quiz`
  rows persisted; cross-user denial identical to missing-lesson 404 (no
  existence leak); missing / orphaned / soft-deleted-presentation 404s; and the
  four service-level equivalents so the security layer is enforced at the
  reusable service boundary (not only at the route). The AI call is stubbed via a
  deterministic `_fake_call_ai` so the harness exercises real validation +
  persistence while staying offline.

## G. Test results (exact, re-executed this milestone)

| Suite | Command | Result |
|---|---|---|
| Ruff | `uv run --project . ruff check app tests` | **All checks passed** |
| Unit (full) | `uv run --project . pytest tests/unit -q` | **1624 passed** (baseline 1613 + 11) |
| Integration (full) | `uv run --project . pytest tests/integration -q` | **216 passed** |
| Two-user isolation (integration) | `test_two_user_isolation.py` | **24 passed** |
| Targeted subtree | `test_rate_limit`, `test_quiz_generation_security`, `test_quiz_routes`, `test_gateway_injection_guard` | **75 passed** |

No pre-existing failures were surfaced by the full runs; no existing test asserted
the removed 422 behavior or the old rate-limit route pattern.

## H. Security (VERIFIED)

Diff + changed-file scan for `AIza…`, `sk-…`, `ghp_…`, `github_pat_…`, `xoxb-…`,
`BEGIN PRIVATE KEY`, `client_secret=`, `access_token=`, `refresh_token=`,
`password=`: **no secrets**. `backend/.env` stays untracked/gitignored and
untouched. No `console.log` / `debugger` / temporary artifacts in the diff.

Related sweep (all verified, no conversion needed):

- Single call site for `QuizGenerationService`: `app/api/v1/quiz.py:45`.
- No frontend consumer of `/quizzes/generate` or `QuizGenerationService`
  (prior docs consistently mark it "UNWIRED (frontend)").
- `test_gateway_injection_guard` (calls `_call_ai` with `uow=object()`) is
  unaffected by the ownership change.
- No test-only modifications were necessary; there were no pre-existing tests
  for this route to convert.

## I. Known limitations

- Equalization changes the not-found status from **422 → 404**; clients must
  treat both as "cannot generate", and the error contract is unchanged in shape
  (`success: false, error: {code, message, details, request_id}`).
- The 10/60 generation budget is the intended default; a deployment that env-
  overrides `RATE_LIMIT_ROUTES` must carry the `^/api/v1/quizzes/generate$`
  entry to keep the tighter budget.
- The fix stops generation, not reads of already-generated quizzes; quiz
  *read/attempt* authorization is already enforced by `assert_quiz_ownership` and
  was outside this milestone's path.

## J. Repository state

Planned single atomic commit, message
`fix(quiz): enforce lesson ownership boundary on quiz generation`, containing the
three app-file changes plus the new test file and this report. Release
verification is recorded separately in
`B1_QUIZ_GENERATION_IDOR_RELEASE_REPORT.md`.