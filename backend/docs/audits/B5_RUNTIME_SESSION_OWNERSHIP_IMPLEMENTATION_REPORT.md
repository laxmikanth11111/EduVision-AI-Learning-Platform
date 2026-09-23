# B5 — Runtime Session Ownership Boundary: Implementation Report

## 1. Milestone Scope

| | |
|---|---|
| **ID** | B5 |
| **Issue type** | Authorization boundary (cross-user state modification / destructive mutation, in-memory) |
| **Affected service** | `backend/app/api/v1/video_runtime_router.py`, `backend/app/api/v1/animation_runtime_router.py` |
| **Affected endpoints** | `POST /api/v1/videos/runtime/sync`, `POST /api/v1/videos/runtime/bookmark`, `POST /api/v1/videos/runtime/assessment`, `POST /api/v1/animations/runtime/sync` |
| **Branch** | `feature/individual-user-foundation` |
| **Baseline commit** | `3ea948f fix(security): enforce per-user ownership boundary on tutor retention sweep` |
| **Fix commit** | (see final commit) |

## 2. Evidence and Finding

See `B5_SECURITY_OWNERSHIP_AUDIT_REPORT.md` (section D–F) for the full read-only audit.
Summary of the exploited write-side gap:

- Reads already enforced ownership (`if not state or state.get("user_id") != str(user.id): data: null`).
- Writes did **not**: `session_id` is caller-chosen free-form text used verbatim as the shared
  `BoundedCache` key, and the write handlers `set()`/append-ed with **no ownership predicate**.
- Effect (User B against User A's `session_id X`):
  1. B `POST /videos/runtime/sync {session_id: X, ...}` returns 200 and **destroys** A's live video
     state (A's later `GET /state/X` and `/tutor-context/X` return `data: null`).
  2. B `POST /videos/runtime/bookmark|assessment {session_id: X, ...}` returns 201/200 and **injects**
     attacker-owned items into A's session bucket.
  3. The identical pattern exists on `POST /animations/runtime/sync` against `_RUNTIME_STATES`.

Pre-fix discriminating run of the committed suite (this milestone, against vulnerable HEAD):

```
5 failed, 4 passed in 14.06s
  test_video_sync_cross_user_isolation   FAILED (200 == 404)
  test_video_bookmark_cross_user_isolation FAILED (201 == 404)
  test_video_assessment_cross_user_isolation FAILED (200 == 404)
  test_animation_sync_cross_user_isolation FAILED (200 == 404)
  test_equalized_404_reveals_no_ownership FAILED (200 == 404)
```

## 3. Fix

### 3.1 Change

Added a small local, 404-equalized ownership helper in each router and invoked it at **every
runtime write site before any mutation**. The helper implements `read-before-write`:

- **Key absent** (`existing is None` / empty bucket) → allowed (preserves first-write/fresh-key
  creation semantics — unchanged behavior for brand-new session keys).
- **Key present, dict state** (runtime states) → owner = `existing["user_id"]`; must equal the caller,
  else equalized 404.
- **Key present, list bucket** (video bookmarks/assessments) → the set of `user_id`s across the bucket
  must be exactly `{caller}`; a bucket whose entries are mixed or belong to another user → equalized 404
  (blocks both injection and clobbering of a bucket, while never leaking whether the key exists).

`video_runtime_router.py`:

- `_assert_session_owned(session_id, existing, user_id)` helper (accepts dict or list bucket).
- `sync_video_runtime`: guard placed immediately before `_VIDEO_RUNTIME_STATES.set(...)`.
- `create_video_bookmark`: guard placed before resolving/appending `_VIDEO_BOOKMARKS`.
- `submit_video_assessment`: guard placed before resolving/appending `_VIDEO_ASSESSMENTS`.
- Imported `NotFoundError` from `app.core.exceptions`.

`animation_runtime_router.py`:

- `_assert_session_owned(session_id, existing, user_id)` helper (dict state only).
- `sync_animation_runtime`: guard placed immediately before `_RUNTIME_STATES.set(...)`.
- Imported `NotFoundError` from `app.core.exceptions`.

All four rejections raise the repository-standard equalized `NotFoundError`
(`message="Runtime session not found"`, `code="NOT_FOUND"`, 404) — the same convention used across
B1–B4, so cross-user addresses and non-existent keys return a **uniform** 404 with no existence oracle
and no ownership/identity detail.

### 3.2 Why the fix is complete and minimal

- **Every write path to the shared caches is guarded.** A grep over `app/` shows the only
  `.set(...)` calls on `_VIDEO_RUNTIME_STATES`, `_VIDEO_BOOKMARKS`, `_VIDEO_ASSESSMENTS`, and
  `_RUNTIME_STATES` live inside the four guarded handlers; all other references are the guarded reads.
- **Mixed-owner buckets are uniformly rejected** (even for the owner), so a previously-poisoned bucket
  cannot be "adopted" back — the safest closed behavior and consistent with the repo's NULL-owner
  convention on visual canvases.
- No model, schema, migration, config, or API response-shape change. Owner flows and fresh-key flows
  keep their exact 200/201 contracts.
- No new authorization framework; extends the repo's `user_id` predicate convention.

## 4. Regression Tests

New file `backend/tests/integration/test_video_animation_runtime_security.py` (9 tests), built on the
two-user JWT harness (mirrors `test_tutor_retention_security.py`):

- **Video sync cross-user isolation** — B's sync of A's session → 404; A's `GET /state` unchanged.
- **Video bookmark cross-user isolation** — B's bookmark into A's session → 404; A's bucket byte-for-byte
  unchanged (direct `_VIDEO_BOOKMARKS` bucket-integrity assertion).
- **Video assessment cross-user isolation** — B's assessment into A's session → 404; A's bucket unchanged.
- **Animation sync cross-user isolation** — B's sync of A's session → 404; A's `GET /state` unchanged.
- **Owner still works (video)** — A sync + bookmark + assessment round-trip 200/201 with correct data.
- **Owner still works (animation)** — A sync round-trip 200 with correct state.
- **Fresh-key creation** — B may create state/bookmarks/assessments under a brand-new key (200/201).
- **404-equalization** — cross-user write 404 body equals non-existent-key 404 body; read side also
  returns identical `data: null` JSON for cross-user and non-existent keys (no existence oracle on
  either side).

The cross-user and equalization tests are discriminators: all **5** failed against vulnerable HEAD and
all **9** pass after the fix.

## 5. Verification

| Check | Result |
|---|---|
| Pre-fix run of new suite (vulnerable HEAD) | **5 failed, 4 passed** (cross-user + equalization fail as expected) |
| Post-fix run of new suite | **9 passed** |
| `uv run --project . pytest tests/unit/test_video_runtime.py tests/unit/test_animation_runtime.py tests/integration/test_visual_generation_smoke.py -q` | **17 passed** (no runtime regression) |
| `uv run --project . pytest tests/unit -q` | **1624 passed** |
| `uv run --project . pytest tests/integration -q` | **250 passed** (241 prior + 9 new) |
| `uv run --project . ruff check app tests` | **All checks passed** |
| Secret scan of diff (sk-…, api-key, secret, password, private keys) + new test file | **Clean** — only benign `hash_password("password123")` test fixtures |
| `git diff --check` | Clean before commit |

## 6. Related-Path Sweep

| Surface | Status |
|---|---|
| `POST /videos/runtime/sync` | **fixed (B5)** — ownership guard before `set` |
| `POST /videos/runtime/bookmark` | **fixed (B5)** — ownership guard before append |
| `POST /videos/runtime/assessment` | **fixed (B5)** — ownership guard before append |
| `POST /animations/runtime/sync` | **fixed (B5)** — ownership guard before `set` |
| `GET /videos/runtime/state/{id}`, `/tutor-context/{id}` | already user-scoped → `data: null` for foreign sessions (unchanged) |
| `GET /animations/runtime/state/{id}` | already user-scoped → `data: null` for foreign sessions (unchanged) |
| `learning_context_service` / `educational_memory_service` writes inside sync handlers | best-effort, own-`user_id`-scoped milestones; learning-context sessions are server-generated (`ctxsess_…`) so a caller-chosen runtime `session_id` cannot address another user's context. Out of the runtime-state boundary; left unchanged. |
| Deferred items I.1–I.4 (export worker re-assert, folder-validation 500/403-oracle, simulation owner caller-conditional, unscoped `get_by_public_id`) | remain deferred — not B5 scope |

## 7. No Inventions / Scope Discipline

The milestone changes exactly the four B5 runtime write paths plus the committed regression tests and
this report. No P0/P1 ops/LLM gap items from `REMAINING_GAPS.md` were touched. Pre-existing untracked
release reports and the untracked B5 audit report were preserved untouched. All tests/checks pass;
exactly one atomic commit follows.

Final repository state: post-commit tracked tree clean; the untracked
`B5_RUNTIME_SESSION_OWNERSHIP_RELEASE_REPORT.md` (plus the pre-existing reports) remains uncommitted.
Push: **NO**. PR: **NO**.