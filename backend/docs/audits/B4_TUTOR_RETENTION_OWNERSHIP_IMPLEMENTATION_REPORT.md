# B4 — Tutor Retention Global Cross-User Destructive Sweep: Implementation Report

## 1. Milestone Scope

| | |
|---|---|
| **ID** | B4 |
| **Issue type** | Authorization boundary (destructive cross-user mutation) |
| **Affected service** | `backend/app/services/mastery_tutor_service.py` |
| **Affected endpoint** | `GET /api/v1/tutor/sessions` (`list_sessions`) |
| **Branch** | `feature/individual-user-foundation` |
| **Baseline commit** | `36d3d04 fix(effectiveness): enforce presentation ownership boundary on assessments and report` |
| **Fix commit** | (see final commit) |

## 2. Evidence and Finding

### 2.1 The vulnerability

`GET /api/v1/tutor/sessions` (`api/v1/tutor.py`) is an authenticated, per-user route: it
resolves `user.id` from `get_current_user` and passes it to
`MasteryTutorService.list_sessions(user_id, ...)`. But at the top of that read,
`list_sessions` called `await self.enforce_retention()` — a **global, learner-unscoped**
retention sweep that operated on **every tenant's** rows:

- `select(TutorSession).where(deleted_at is None, status == ACTIVE, updated_at < idle_cutoff)`
  — **no `user_id` filter** → it **archives** (status-flips) other users' idle active sessions.
- `select(TutorConversation).where(deleted_at is None, updated_at < cleanup_cutoff)`
  — **no `user_id` filter** → it **soft-deletes** other users' expired conversations.
- `delete(TutorMessage).where(conversation_id.in_(expired_ids))` — **hard-deletes** the
  message rows of every tenant's expired conversations (the actual storage bound, and
  permanent data loss).

This is the same root-cause class B1/B2/B3 closed elsewhere: an authenticated route whose
service boundary lacks ownership enforcement — but here the boundary violation is a
**destructive write** (hard-delete) of another learner's data, triggered by any unrelated
learner's read.

### 2.2 Why it is a security issue (AUTHENTICATION != AUTHORIZATION)

- The learner is authenticated (their own `user_id`), but the retention sweep they trigger
  by listing their own sessions **mutates and permanently deletes rows owned by every other
  learner** in the system.
- Impact is cross-tenant data destruction and availability: an unrelated authenticated user
  can force the archive of another user's idle sessions and the **hard-deletion** of another
  user's aged conversation messages simply by calling their own session-history read.
- There is no mechanism by which the victim consents, and the operation is irreversible for
  the message rows (they are not soft-deleted; they are removed from the table).

### 2.3 Two-user proof (executed during this milestone)

A scratch discriminator test drove the real ASGI app with JWT auth for two users and
confirmed against the pre-fix code:

> Under the pre-fix behavior, **User B** calling `GET /api/v1/tutor/sessions` caused
> **User A's** aged idle `active` session to be **archived**, **User A's** expired
> conversation to be **soft-deleted**, and **User A's** 3 conversation messages to be
> **hard-deleted** — all as a side effect of User B listing her own sessions.

The committed regression tests deny exactly this cross-user destructive sweep on the fixed
code, while preserving the owner's own storage bound.

## 3. Fix

### 3.1 Change

`backend/app/services/mastery_tutor_service.py`:

- `enforce_retention(user_id, now=None)` now requires the calling `user_id` and adds an
  **ownership boundary to every mutation**:
  - idle-session select: `TutorSession.user_id == user_id`;
  - expired-conversation select: `TutorConversation.user_id == user_id`;
  - the message hard-delete is already indirected through the (now user-scoped) conversation
    ids, so it is implicitly scoped too.
- `list_sessions` now calls `await self.enforce_retention(user_id)`, propagating the
  authenticated learner's id into the sweep.

No route contract, schema, or response shape changed. The storage-bound guarantee is
preserved: each learner's own read still archives their own idle sessions and removes their
own expired conversation messages.

### 3.2 Why the fix is complete and minimal

- The only production caller of `enforce_retention` is `list_sessions` (verified by grep;
  the docs already flagged "no beat task" — `enforce_retention` runs on read only), so the
  single call-site update fully closes the exposed path.
- Every read/mutation in the sweep is now bounded by the caller's `user_id`, matching the
  repository pattern used everywhere else in the tutor router
  (`get_for_user_or_raise`/`list_for_user` are already user-scoped).
- No new authorization framework was introduced; the fix extends the existing
  `user_id` predicate convention used across the codebase.

## 4. Regression Tests

New file `backend/tests/integration/test_tutor_retention_security.py` (3 tests), modeled on
the B3 two-user JWT security suite:

- **Auth (1)** — unauthenticated `GET /api/v1/tutor/sessions` → 401.
- **Owner storage bound preserved (1)** — User A's own read still archives A's aged idle
  session and soft-deletes A's expired conversation + hard-deletes A's messages (the
  intended retention behavior still works).
- **Cross-user immutability (1)** — User B's read leaves User A's session `active`, A's
  conversation `deleted_at` NULL, and A's 3 messages fully intact (the boundary fix).

The cross-user test is discriminating: against the pre-fix implementation it failed (A's
conversation got soft-deleted and A's messages were hard-deleted by B's read).

Existing unit tests in `backend/tests/unit/test_mastery_tutor_retention.py` were updated to
pass the owning `user_id` to the new required parameter; their assertions (owner-side
archive/cleanup semantics) are unchanged.

## 5. Verification

| Check | Result |
|---|---|
| `ruff check` (changed files) | All checks passed |
| `uv run --project . pytest tests/integration/test_tutor_retention_security.py tests/unit/test_mastery_tutor_retention.py tests/integration/test_assistant.py tests/integration/test_assistant_security.py -q` | **31 passed** |
| `uv run --project . pytest tests/unit -q` | **1624 passed** |
| `uv run --project . pytest tests/integration -q` | **241 passed** (incl. 3 new) |
| Security scan (AIza…, sk-…, ghp_…, github_pat_…, xoxb-…, BEGIN PRIVATE KEY, client_secret=, access_token=, refresh_token=, password=) | **Clean** — only benign matches (scan-pattern strings in prior audit docs; test-fixture password/api-key values; `settings.AI_API_KEY` references) |
| `git diff --check` | Clean before commit |

## 6. Related-Path Sweep (same root-cause class)

Tutor-router and retention paths and their status:

| Location | Status |
|---|---|
| `MasteryTutorService.enforce_retention` | **fixed in this milestone (B4)** — user-scoped |
| `list_sessions` (`GET /tutor/sessions`) | **fixed in this milestone (B4)** — passes `user_id` |
| `get_session` / `send_message` / `list_messages` / `remediate` | already user-scoped via `get_for_user_or_raise(user_id, ...)` |
| `TutorSessionRepository.list_for_user` / `get_for_user` | already user-scoped |
| `TutorConversationRepository.get_for_user` / `latest_for_session` | already user-scoped |
| `enforce_retention` callers | only `list_sessions` (verified); no other entry point |
| `GET /api/v1/metrics` (no auth dependency) | **not a B4 issue**: Prometheus-format counter/gauge registry with no learner-PII; deliberately unauthenticated scrape surface (`include_in_schema=False`). Left unchanged. |
| Video runtime in-memory `_VIDEO_RUNTIME_STATES`/`_VIDEO_BOOKMARKS`/`_VIDEO_ASSESSMENTS` write paths | in-memory, process-local caches; read paths already enforce `user_id`; modeled as out-of-scope transient-state pollution, not a durable data boundary. Left unchanged. |
| `PresentationService.create_presentation` `validate_folder_ownership` (undefined → 500) | availability bug (fails closed with 500, no cross-user write succeeds); not an authorization boundary leak. Flagged for a future milestone, out of B4 scope. |

## 7. No Inventions / Scope Discipline

The milestone addresses exactly one evidence-backed authorization-boundary issue — the only
destructive cross-user mutation found in the read-only sweep. No P0/P1 gaps from
`REMAINING_GAPS.md` were touched (those are ops/LLM items, not authz). Pre-existing untracked
release reports were preserved:
`B1_QUIZ_GENERATION_IDOR_RELEASE_REPORT.md`,
`B2_AI_ASSISTANT_LESSON_CONTEXT_IDOR_RELEASE_REPORT.md`,
`B3_EFFECTIVENESS_ASSESSMENT_IDOR_RELEASE_REPORT.md`,
`F1_LEARNING_MODE_COMPLETION_RELEASE_REPORT.md`, `NEXT_MILESTONE_RELEASE_REPORT.md`.