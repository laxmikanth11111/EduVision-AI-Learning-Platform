# B5 — Runtime Session Ownership Boundary: Release Report

| | |
|---|---|
| **ID** | B5 |
| **Issue type** | Authorization boundary (cross-user state modification / destructive mutation, in-memory) |
| **Affected endpoints** | `POST /api/v1/videos/runtime/sync`, `POST /api/v1/videos/runtime/bookmark`, `POST /api/v1/videos/runtime/assessment`, `POST /api/v1/animations/runtime/sync` |
| **Baseline commit** | `3ea948f` (`fix(security): enforce per-user ownership boundary on tutor retention sweep` — B4) |
| **Fix commit** | `8c0c3f2` (`fix(security): enforce per-user ownership boundary on runtime session state` — B5) |
| **Branch** | `feature/individual-user-foundation` |
| **Parent** | `3ea948f` |

## Summary

The interactive video and animation runtime sync endpoints maintain per-user playback state in
module-global in-memory `BoundedCache` stores (`_VIDEO_RUNTIME_STATES`, `_VIDEO_BOOKMARKS`,
`_VIDEO_ASSESSMENTS`, `_RUNTIME_STATES`) keyed by a caller-chosen, unvalidated `session_id`. The
**read** paths enforced ownership (`state.user_id == str(user.id)` → else `data: null`), but the
**write** paths had **no ownership predicate**: any authenticated user who knew a victim's
`session_id` could unconditionally overwrite the victim's live playback state or inject attacker-owned
bookmarks/assessments into the victim's session bucket. Because `session_id` is free-form text (tests
use literals like `"test_vid_session"`), such keys are in practice low-entropy and guessable.

### Proof (pre-fix, committed discriminator suite — 5 failed / 4 passed)

| Scenario | Pre-fix observed | Post-fix |
|---|---|---|
| B syncs A's video session | 200; A's state destroyed (A reads `null`) | **404**; A state untouched |
| B bookmarks into A's video session | 201; bucket polluted | **404**; A bucket byte-for-byte unchanged |
| B assesses into A's video session | 200; bucket polluted | **404**; A bucket unchanged |
| B syncs A's animation session | 200; A's anim state destroyed | **404**; A state untouched |
| 404-equalization (cross-user vs non-existent) | 200 vs 404 (oracle exposed) | uniform 404; read side identical `data:null` |

### Fix

Added a local 404-equalized `_assert_session_owned(session_id, existing, user_id)` helper in each
router and invoked it **before every mutation** (read-before-write):

- key absent / empty bucket → allowed (fresh-key creation preserved, 200/201 behavior unchanged);
- dict state → must equal caller's `user_id`;
- list bucket (bookmarks/assessments) → the bucket's `user_id` set must be exactly `{caller}`,
  blocking both injection and clobbering;
- any foreign/mixed session → repository-standard equalized `NotFoundError` (404, `code="NOT_FOUND"`,
  no existence oracle, no ownership leak).

No model, schema, migration, config, or API response-shape changed.

## Verification

| Check | Result |
|---|---|
| Pre-fix run of new suite (vulnerable HEAD) | **5 failed, 4 passed** (cross-user/equality fail as expected) |
| Post-fix run of new suite `tests/integration/test_video_animation_runtime_security.py` | **9 passed** |
| Runtime regression tests (`test_video_runtime.py`, `test_animation_runtime.py`, visual smoke) | **17 passed** |
| `pytest tests/unit -q` | **1624 passed** |
| `pytest tests/integration -q` | **250 passed** (241 prior + 9 new) |
| `ruff check app tests` | All checks passed |
| Secret scan of diff + new test file | Clean (only benign `hash_password("password123")` fixtures) |
| `git diff --check` / `git show --check HEAD` | Clean |

## Out of Scope (documented, not vulnerabilities)

- **Video runtime read paths** (`GET /state`, `/tutor-context`) already user-scoped; unchanged.
- **Sync-handler best-effort side writes** (`learning_context_service.publish_event`,
  `educational_memory_service.add_milestone`): milestones are own-`user_id`-scoped; learning-context
  sessions are server-generated (`ctxsess_…`) so caller-chosen runtime `session_id`s cannot address
  another user's context. Separate stores, outside the runtime-state boundary.
- **Deferred B5 audit items I.1–I.4** (export-worker tenant re-assert, presentation folder
  `validate_folder_ownership` 500 + 403-vs-404 oracle, simulation engine owner caller-conditional,
  unscoped `get_by_public_id` variants) — not B5 scope; remain documented for a future milestone.

## Follow-Up

- Push: **NO** (not requested).
- Pull request: **NO** (not requested).
- Commit: exactly one atomic commit `8c0c3f2`.
- Pre-existing untracked reports preserved: `B1_QUIZ_GENERATION_IDOR_RELEASE_REPORT.md`,
  `B2_AI_ASSISTANT_LESSON_CONTEXT_IDOR_RELEASE_REPORT.md`,
  `B3_EFFECTIVENESS_ASSESSMENT_IDOR_RELEASE_REPORT.md`,
  `B4_TUTOR_RETENTION_OWNERSHIP_RELEASE_REPORT.md`,
  `F1_LEARNING_MODE_COMPLETION_RELEASE_REPORT.md`, `NEXT_MILESTONE_RELEASE_REPORT.md`,
  plus `B5_SECURITY_OWNERSHIP_AUDIT_REPORT.md` (audit deliverable).
- This release report is intentionally **uncommitted**.