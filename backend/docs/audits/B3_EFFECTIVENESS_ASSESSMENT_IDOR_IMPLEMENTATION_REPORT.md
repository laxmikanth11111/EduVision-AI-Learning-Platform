# B3 — Effectiveness Assessment / Report Ownership Boundary: Implementation Report

## 1. Milestone Scope

| | |
|---|---|
| **ID** | B3 |
| **Issue type** | Authorization boundary (IDOR) |
| **Affected service** | `backend/app/services/effectiveness_service.py` |
| **Affected endpoints** | `POST /api/v1/effectiveness/assessments/start`, `GET /api/v1/effectiveness/report/{presentation_id}` |
| **Branch** | `feature/individual-user-foundation` |
| **Baseline commit** | `7d9c092 fix(assistant): enforce lesson ownership boundary on session/conversation anchors` |
| **Fix commit** | (see final commit) |

## 2. Evidence and Finding

### 2.1 The vulnerability

The effectiveness module binds an `EffectivenessAssessment` to a caller-controlled
`presentation_id` (an internal `Presentation.id` UUID) without any existence or ownership
validation, and the report endpoint resolves the presentation for the response **without any
owner filter**:

- `POST /api/v1/effectiveness/assessments/start` (`api/v1/effectiveness.py:103-126`) →
  `EffectivenessService.start_assessment` → `get_or_create_assessment` created
  `EffectivenessAssessment(user_id, presentation_id)` with **no check that the presentation
  exists, belongs to `user_id`, or is not soft-deleted**.
- `GET /api/v1/effectiveness/report/{presentation_id}` (`api/v1/effectiveness.py:213-260`)
  computed a user-scoped gain, then fetched `select(Presentation).where(Presentation.id == presentation_id)`
  with **no `owner_id` filter and no `deleted_at` filter**, returning `presentation_title`
  from that row.

This is the same root-cause class B1/B2 closed for quiz generation and the AI assistant: a
resource lookup keyed by a caller-controlled identifier (`presentation_id`) at a service
boundary without ownership enforcement, where the presentation is the top-level ownership
unit in the individual-first model.

### 2.2 Why it is a security issue (AUTHENTICATION != AUTHORIZATION)

- The learner is authenticated (their own `user_id`), but the presentation resource they bind
  an assessment to and read a report from is **not** theirs.
- The attacker supplies another user's internal presentation id. The two endpoints that
  `start_assessment` feeds will then treat the caller as a participant of the victim's
  presentation, and the report returns the victim's **`presentation_title`** (and existence)
  to the caller.

### 2.3 Two-user proof (executed during this milestone)

A scratch discriminator test (temporary, removed) drove the real ASGI app with JWT auth for
two users and confirmed against the pre-fix code:

> Under the pre-fix behavior, **User B** calling `start_assessment` with **User A's**
> presentation id returned **201** and created an `EffectivenessAssessment` bound to User A's
> presentation; **User B** then called `GET /report/{presentation_id}` and received **200**
> with `presentation_title` = User A's private presentation title.

The committed regression tests deny exactly this cross-user bind and title read with **404**
on the fixed code.

### 2.4 Related candidate that is NOT a vulnerability (by design)

`GET /api/v1/effectiveness/comparison` (`compare_groups`) aggregates assessments across
participants grouped by `experiment_group` without a user filter. This is **intentional**
P2 comparison infrastructure: `tests/unit/test_p2_effectiveness.py::TestGroupComparison`
explicitly asserts cross-user aggregate counts. It was therefore excluded from this fix —
closing it would break the designed experiment-comparison feature, not an authorization
boundary.

## 3. Fix

### 3.1 Change

`backend/app/services/effectiveness_service.py`:

- Added `get_owned_presentation(user_id, presentation_id)` — an ownership predicate identical
  to the repository's established helpers (`assert_quiz_ownership`,
  `MasteryTutorService._verify_presentation_owner`, `_get_owned_presentation`):
  - presentation exists (`deleted_at` NULL) **and** `owner_id` matches the caller;
  - **404-equalized**: a missing presentation, an orphaned presentation (no owner), a
    soft-deleted presentation, and a non-owner all raise the same `Presentation not found`
    (`NotFoundError`, status 404) so no cross-user existence leak occurs.
- `start_assessment` now calls `get_owned_presentation(user_id, presentation_id)` before
  `get_or_create_assessment`, so an assessment can only be bound to a presentation the caller
  owns.

`backend/app/api/v1/effectiveness.py`:

- The report handler replaced its unowned inline `select(Presentation).where(...)` fetch with
  `service.get_owned_presentation(user_id=user.id, ...)` — defense-in-depth on the read path
  so `presentation_title` is never returned for a presentation the caller does not own, even
  against a legacy assessment row.

No route contract, schema, or response shape changed. The 404 body is produced by the
existing global exception handler (`error.code == "NOT_FOUND"`, `message == "Presentation not found"`),
consistent with B1/B2 and the sibling `GET /effectiveness/feedback/summary/{presentation_id}`
which already enforced `pres.owner_id != user.id → NotFoundError("Presentation not found")`.

### 3.2 Why the read path is safe post-fix

- `get_or_create_assessment` remains ownership-free internally so the by-design
  `compare_groups` unit tests (which bind assessments cross-user at the service level) keep
  passing.
- `start_assessment` is the only HTTP/service entry that binds an assessment to a
  presentation; with the ownership gate there, `compute_learning_gain` can only return data
  for assessments the caller owns against presentations the caller owns.
- The report's title fetch is additionally owner-gated, so even a pre-existing cross-user
  assessment row cannot leak the victim's `presentation_title`.

## 4. Regression Tests

New file `backend/tests/integration/test_effectiveness_security.py` (9 tests), modeled on the
B1/B2 two-user JWT security suites:

**HTTP route — owner success (1)**
- owner can start an assessment and read the report → 201 / 200 with their own title.

**HTTP route — cross-user denial (3)**
- User B starting an assessment for presentation A → 404 `NOT_FOUND`/`Presentation not found`;
- User B reading the report for presentation A — including against a **legacy assessment row
  bound to A's presentation** (simulated pre-fix data) → 404, no title leak;
- cross-user vs missing-presentation 404 bodies indistinguishable (equalization).

**HTTP route — missing / orphaned / soft-deleted (4)**
- missing presentation id → 404 even for a valid owner;
- soft-deleted presentation → 404 even for its owner;
- orphaned presentation (no owner) → 404 for everyone;
- report on a missing presentation → 404.

**Auth (1)**
- unauthenticated `start_assessment` and `report` → 401.

All 9 are discriminating: against the pre-fix implementation the cross-user bind succeeded
(201) and the report returned the victim's title (200), so the denial assertions fail on the
vulnerable code.

## 5. Verification

| Check | Result |
|---|---|
| `uv tool run --from ruff ruff check` (changed files) | All checks passed |
| `uv run --project . pytest tests/unit -q` | **1624 passed** |
| `uv run --project . pytest tests/integration -q` | **238 passed** (incl. 9 new) |
| Security scan (AIza…, sk-…, ghp_…, github_pat_…, xoxb-…, BEGIN PRIVATE KEY, client_secret=, access_token=, refresh_token=, password=) | **Clean** — only benign matches (`create_access_token`/`decode_access_token` test-fixture usage, fixture `password123` in test seeding) |
| `git diff --check` | Clean before commit |

## 6. Related-Path Sweep (same root-cause class)

Presentation-keyed / assessment-keyed paths in the effectiveness module and their status:

| Location | Status |
|---|---|
| `EffectivenessService.get_owned_presentation` (new) | **added in this milestone (B3)** |
| `EffectivenessService.start_assessment` | **fixed in this milestone (B3)** |
| `GET /effectiveness/report/{id}` title fetch | **fixed in this milestone (B3)** |
| `GET /effectiveness/feedback/summary/{id}` | already guarded (`pres.owner_id != user.id → 404`) |
| `record_quiz_score` / `record_attempt_score` | user-scoped via `assessment_id` + `user_id` predicates and `QuizAttempt.user_id` |
| `get_assessment` / `learning-gain` / `get_assessment_by_id` | user-scoped by `user_id` |
| `user_summary` / `export_study_data` | user-scoped by `user_id` |
| `submit_feedback` / `record_learning_event` | writes carry arbitrary `presentation_id`, but all reads are user-scoped or owner-gated (feedback summary); modeled as out-of-scope write-pollution, not a read-side boundary leak |
| `compare_groups` (comparison) | **by-design** cross-user aggregates; see §2.4 |

The efficiency module was the only remaining assessment/report path with a presentation
lookup at an HTTP/service boundary lacking ownership enforcement.

## 7. No Inventions / Scope Discipline

The milestone addresses exactly one evidence-backed authorization-boundary issue. No P0/P1
gaps from `REMAINING_GAPS.md` were touched. Pre-existing untracked release reports were
preserved:
`B1_QUIZ_GENERATION_IDOR_RELEASE_REPORT.md`, `B2_AI_ASSISTANT_LESSON_CONTEXT_IDOR_RELEASE_REPORT.md`,
`F1_LEARNING_MODE_COMPLETION_RELEASE_REPORT.md`, `NEXT_MILESTONE_RELEASE_REPORT.md`.