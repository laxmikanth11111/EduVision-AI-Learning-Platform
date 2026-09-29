# B4 — Tutor Retention Global Cross-User Destructive Sweep: Release Report

| | |
|---|---|
| **ID** | B4 |
| **Issue type** | Authorization boundary (destructive cross-user mutation) |
| **Affected endpoint** | `GET /api/v1/tutor/sessions` (`list_sessions` → `enforce_retention`) |
| **Baseline commit** | `36d3d04` (`fix(effectiveness): enforce presentation ownership boundary on assessments and report` — B3) |
| **Fix commit** | `3ea948f` (`fix(security): enforce per-user ownership boundary on tutor retention sweep` — B4) |
| **Branch** | `feature/individual-user-foundation` |
| **Parent** | `36d3d04` |

## Summary

`GET /api/v1/tutor/sessions` is an authenticated, per-user read, but `list_sessions` invoked
`MasteryTutorService.enforce_retention()` — a **global, learner-unscoped** retention sweep
that selected **every tenant's** rows and mutated them with no `user_id` boundary: it
archived other users' idle sessions, soft-deleted other users' expired conversations, and
**hard-deleted every tenant's expired `tutor_messages`**. Any unrelated authenticated learner
listing their own sessions could permanently destroy another learner's aged conversation
messages.

### Proof (pre-fix, scratch two-user test, removed)

> **User B** → `GET /api/v1/tutor/sessions` → 200; **User A's** aged session archived,
> **User A's** expired conversation soft-deleted, and **User A's** 3 messages **hard-deleted**
> — all caused by User B's own session-history read.

### Fix

- `enforce_retention(user_id, now=None)` now takes the calling `user_id` and adds the
  ownership predicate (`TutorSession.user_id == user_id`,
  `TutorConversation.user_id == user_id`) to both mutation selects; the message hard-delete is
  indirectly scoped through the (now user-scoped) conversation ids.
- `list_sessions` passes `user_id` into the sweep.

No route contract, schema, or response shape changed. Every learner's own read still bounds
their own storage (owner semantics preserved).

## Verification

| Check | Result |
|---|---|
| New security suite `tests/integration/test_tutor_retention_security.py` | **3 passed** |
| `pytest tests/unit -q` | **1624 passed** |
| `pytest tests/integration -q` | **241 passed** |
| `ruff check` (changed files) | All checks passed |
| Secret scan (AIza…, sk-…, ghp_…, github_pat_…, xoxb-…, BEGIN PRIVATE KEY, client_secret=, access_token=, refresh_token=, password=) | Clean (only benign test-fixture usage and prior-doc scan strings) |
| `git diff --check` | Clean |

## Out of Scope (documented, not vulnerabilities)

- `GET /api/v1/metrics`: deliberately unauthenticated Prometheus counter/gauge scrape surface
  (`include_in_schema=False`), no learner PII. Left unchanged.
- Video runtime in-memory `_VIDEO_RUNTIME_STATES`/`_VIDEO_BOOKMARKS`/`_VIDEO_ASSESSMENTS`
  write paths: process-local caches; reads already enforce `user_id`; transient-state
  pollution only, not a durable data boundary.
- `PresentationService.create_presentation` → `validate_folder_ownership` (undefined → 500):
  availability bug that fails closed (no cross-user write succeeds); not an authorization
  leak. Flagged for a future milestone.

## Follow-Up

- Push: **NO** (not requested).
- Pull request: **NO** (not requested).
- Pre-existing untracked release reports preserved: `B1_QUIZ_GENERATION_IDOR_RELEASE_REPORT.md`,
  `B2_AI_ASSISTANT_LESSON_CONTEXT_IDOR_RELEASE_REPORT.md`,
  `B3_EFFECTIVENESS_ASSESSMENT_IDOR_RELEASE_REPORT.md`,
  `F1_LEARNING_MODE_COMPLETION_RELEASE_REPORT.md`, `NEXT_MILESTONE_RELEASE_REPORT.md`.