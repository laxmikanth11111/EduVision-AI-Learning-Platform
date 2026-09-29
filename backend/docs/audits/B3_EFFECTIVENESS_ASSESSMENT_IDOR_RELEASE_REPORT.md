# B3 — Effectiveness Assessment / Report IDOR: Release Report

| | |
|---|---|
| **ID** | B3 |
| **Issue type** | Authorization boundary (IDOR) |
| **Affected endpoints** | `POST /api/v1/effectiveness/assessments/start`, `GET /api/v1/effectiveness/report/{presentation_id}` |
| **Baseline commit** | `7d9c092` (`fix(assistant): enforce lesson ownership boundary on session/conversation anchors` — B2) |
| **Fix commit** | `36d3d04` (`fix(effectiveness): enforce presentation ownership boundary on assessments and report` — B3) |
| **Branch** | `feature/individual-user-foundation` |
| **Parent** | `7d9c092` |

## Summary

The effectiveness module bound an `EffectivenessAssessment` to a caller-controlled
`presentation_id` (internal `Presentation.id` UUID) without validating existence or ownership,
and the report endpoint resolved the presentation for `presentation_title` with no owner or
soft-delete filter. A non-owner could start an assessment against another user's presentation
(201) and then read that user's private presentation title via the report (200).

### Proof (pre-fix, scratch two-user test, removed)

> **User B** → `POST /assessments/start {presentation_id: <A's>}` → **201**; then
> **User B** → `GET /report/{presentation_id}` → **200** with User A's
> `presentation_title`.

### Fix

- `EffectivenessService.get_owned_presentation(user_id, presentation_id)`: presentation must
  exist, not be soft-deleted, and have `owner_id == user_id`; otherwise 404-equalized
  `NotFoundError("Presentation not found")` (missing / orphaned / soft-deleted / non-owner
  all identical — no existence leak).
- `start_assessment` enforces it before binding an assessment.
- Report handler replaces its unowned inline `Presentation` fetch with the same owner-gated
  lookup (defense-in-depth on the read path).

No route contract, schema, or response shape changed.

## Verification

| Check | Result |
|---|---|
| New security suite `tests/integration/test_effectiveness_security.py` | **9 passed** |
| `pytest tests/unit -q` | **1624 passed** |
| `pytest tests/integration -q` | **238 passed** |
| `ruff check` (changed files) | All checks passed |
| Secret scan (AIza…, sk-…, ghp_…, github_pat_…, xoxb-…, BEGIN PRIVATE KEY, client_secret=, access_token=, refresh_token=, password=) | Clean (only benign test-fixture usage) |
| `git diff --check` | Clean |

## Out of Scope (documented, not vulnerabilities)

- `GET /effectiveness/comparison` (`compare_groups`): cross-user aggregate counts are
  **intentional** P2 experiment-comparison behavior, asserted in
  `tests/unit/test_p2_effectiveness.py::TestGroupComparison`.
- `submit_feedback` / `record_learning_event`: accept arbitrary `presentation_id` on write,
  but every read path is user-scoped or owner-gated; flagged as write-pollution, not a
  read-side boundary leak.

## Follow-Up

- Push: **NO** (not requested).
- Pull request: **NO** (not requested).
- Pre-existing untracked release reports preserved: `B1_QUIZ_GENERATION_IDOR_RELEASE_REPORT.md`,
  `B2_AI_ASSISTANT_LESSON_CONTEXT_IDOR_RELEASE_REPORT.md`,
  `F1_LEARNING_MODE_COMPLETION_RELEASE_REPORT.md`, `NEXT_MILESTONE_RELEASE_REPORT.md`.