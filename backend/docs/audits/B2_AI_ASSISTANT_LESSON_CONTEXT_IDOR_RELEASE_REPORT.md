# B2 — AI Assistant Lesson-Context IDOR: Release Report

## 1. Summary

- **Commit**: `7d9c092` — `fix(assistant): enforce lesson ownership boundary on session/conversation anchors`
- **Branch**: `feature/individual-user-foundation`
- **Parent**: `a34b5d3` (B1 — quiz-generation IDOR)
- **Status**: Released to feature branch. **Not pushed, no PR.**

B2 closes a cross-user lesson-context IDOR in the AI assistant service. The assistant's
session/conversation bind endpoints resolved any `GeneratedLesson` by `public_id` with **no
ownership check**, then the message-send path pulled that victim lesson's private content and
source-material RAG chunks into the caller's AI context. The fix enforces the same
404-equalized lesson ownership rule used by quiz generation (B1), the mastery tutor, and the
lesson player.

## 2. What changed

| Aspect | Before | After |
|---|---|---|
| Lesson lookup | `_resolve_lesson_id(public_id)` — unguarded bind | `_get_owned_lesson_id(user_id, public_id)` — presentation-owner OR `lesson.user_id` required |
| Cross-user bind | 201 + victim `lesson_id` persisted | 404 `NOT_FOUND` / `Lesson not found` (equalized) |
| Missing / orphaned / deleted-presentation lesson | 201 (silently unanchored) | 404 (identical body to non-owner) |
| Unanchored sessions (`lesson_id=None`) | work | unchanged |
| Response/schema/route contract | — | unchanged |

Files:
- `backend/app/services/learning_assistant_service.py` (the fix)
- `backend/tests/integration/test_assistant_security.py` (new, 13 discriminating tests)
- `backend/docs/audits/B2_AI_ASSISTANT_LESSON_CONTEXT_IDOR_IMPLEMENTATION_REPORT.md`

## 3. Verification evidence

| Check | Result |
|---|---|
| `tests/unit` | **1624 passed** |
| `tests/integration` (incl. 13 new B2) | **229 passed** |
| `ruff check app tests` | All checks passed |
| Secrets scan | Clean (benign matches only: prior audit-doc pattern strings; `create_access_token`/`create_refresh_token` calls) |
| `git diff --check` | Clean before commit |
| Two-user pre-fix proof | Reproduced: pre-fix cross-user bind returned 201 and persisted the victim lesson id; the new tests deny it with 404 |

## 4. Known limitations / deferred

- Defense-in-depth at the **read** site (`_build_context_text` / `_retrieve_relevant_chunks`)
  was not added; it is not needed for newly created conversations because `lesson_id` is only
  set through the now-guarded creation paths. If a future code path begins assigning
  `lesson_id` outside `create_session`/`create_conversation`, the read site would need the
  same predicate re-applied.
- B1's recorded runner-up candidates (F2 session uniqueness, F4 stale-write conflict
  detection) remain data-integrity candidates, not authorization-boundary issues, and were
  intentionally not assumed to be the next security milestone.
- `REMAINING_GAPS.md` P0 items (live full-stack smoke test, Python 3.13 vs 3.11 divergence,
  LLM-verifier coverage) are untouched.

## 5. Process compliance

- Single atomic commit; no history rewrite; no push, no PR, no destructive git operations.
- Pre-existing untracked release reports preserved:
  `B1_QUIZ_GENERATION_IDOR_RELEASE_REPORT.md`, `F1_LEARNING_MODE_COMPLETION_RELEASE_REPORT.md`,
  `NEXT_MILESTONE_RELEASE_REPORT.md`.
- Milestone was selected from repository evidence (same root-cause class as B1), with a
  two-user proof executed before the fix, and a related-path sweep recorded in the
  implementation report.