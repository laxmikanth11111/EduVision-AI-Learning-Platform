# B2 — AI Assistant Lesson-Context IDOR: Implementation Report

## 1. Milestone Scope

| | |
|---|---|
| **ID** | B2 |
| **Issue type** | Authorization boundary (IDOR) |
| **Affected service** | `backend/app/services/learning_assistant_service.py` |
| **Affected endpoints** | `POST /api/v1/assistant/sessions`, `POST /api/v1/assistant/conversations` |
| **Branch** | `feature/individual-user-foundation` |
| **Baseline commit** | `a34b5d3 fix(quiz): enforce lesson ownership boundary on quiz generation` |
| **Fix commit** | (see final commit) |

## 2. Evidence and Finding

### 2.1 The vulnerability

`LearningAssistantService._resolve_lesson_id` (now `_get_owned_lesson_id`) resolved a
`GeneratedLesson` purely by `public_id` and returned the row's id **without any ownership
validation**. Both entry points that carry an attacker-controlled `lesson_id` called it directly:

- `LearningAssistantService.create_session(user_id, request)` → `request.lesson_id`
- `LearningAssistantService.create_conversation(user_id, request)` → `request.lesson_id`

A non-owner was therefore able to anchor their assistant session/conversation to another
user's lesson. The message-send path then flowed that victim content into the caller's
context:

- `_build_context_text(conv)` loads the victim lesson's title, mode, and **live lesson block
  content** (from the latest `GeneratedLessonVersion`/`GeneratedBlock`).
- `_retrieve_relevant_chunks(lesson_id=...)` loads the victim **source-material RAG chunks**
  (`DocumentChunk` rows linked to the lesson's presentation content units).
- Both are embedded into the AI prompt context (and persisted in `AssistantContextSnapshot`
  rows) for the *caller's* conversation.

This is the same root cause B1 closed for quiz generation (a `GeneratedLesson.public_id`
lookup without ownership enforcement), repeated in the AI assistant service, which B1 did
not cover.

### 2.2 Why it is a security issue (AUTHENTICATION != AUTHORIZATION)

- The learner is authenticated (their own `user_id`), but the lesson resource bound to the
  conversation is **not** theirs.
- The attacker only needs another user's lesson `public_id`. Lesson public ids are exposed in
  the product surface (player deep links, lesson lists, shared content) and are iterable.
- The confidentiality impact is cross-user leakage of private lesson content and the source
  material used to generate it, delivered through the AI context (and fallback echoes) of a
  conversation the attacker fully controls.

### 2.3 Two-user proof (executed during this milestone)

A scratch discriminator test (temporary, removed) temporarily restored the pre-fix
`_resolve_lesson_id` body (`select(...).where(public_id == ...); return lesson.id`) and
confirmed:

> Under the pre-fix behavior, **User B** anchoring a conversation to **User A's** lesson
> `public_id` returned **201** and the persisted `AssistantConversation.lesson_id` pointed at
> User A's lesson — i.e. the victim lesson was bound into the attacker's conversation.

The committed regression tests deny exactly this bind with **404** on the fixed code.

## 3. Fix

### 3.1 Change

`backend/app/services/learning_assistant_service.py`:

- Renamed `_resolve_lesson_id` → `_get_owned_lesson_id(user_id, lesson_public_id)`.
- Added an ownership predicate identical to the repository's established helpers
  (`QuizGenerationService._get_owned_lesson`, `MasteryTutorService._get_owned_lesson`,
  `assert_quiz_ownership`):
  - lesson exists **and** is owned via its parent `Presentation.owner_id` (top-level
    ownership unit, soft-deleted presentation excluded) **or** via the lesson's direct
    `user_id` (legacy/edge data);
  - **404-equalized**: a missing lesson, an orphaned presentation (no owner), a soft-deleted
    presentation, and a non-owner lesson all raise the same `Lesson not found`
    (`NotFoundError`, status 404) so no cross-user existence leak occurs.
- `lesson_id=None` (no anchor) passes through unchanged → unanchored sessions/conversations
  keep working.
- Both call sites (`create_session`, `create_conversation`) now pass the authenticated
  `user_id`.

No route contract, schema, or response shape changed. The 404 body is produced by the
existing global exception handler (`error.code == "NOT_FOUND"`, `message == "Lesson not found"`),
consistent with B1 and the tutor endpoints.

### 3.2 Why the read path is safe post-fix

`_build_context_text` / `_retrieve_relevant_chunks` consume `conv.lesson_id`/`session.lesson_id`
that are only ever set through `create_session`/`create_conversation` — both now enforce
ownership before persistence. The conversation repository's `get_for_user_or_raise` also
scopes every read to the authenticated user. Defense in depth is therefore not required at
the read site for a new conversation.

## 4. Regression Tests

New file `backend/tests/integration/test_assistant_security.py` (13 tests), modeled on the
B1 security suite:

**HTTP route — owner success (2)**
- owner can anchor a session to their own lesson → 201, `lesson_id` persisted;
- owner can anchor a conversation to their own lesson → 201, `lesson_id` persisted.

**HTTP route — cross-user denial (5)**
- User B anchoring a session to lesson A → 404 `NOT_FOUND`/`Lesson not found`;
- User B anchoring a conversation to lesson A → 404;
- cross-user error byte-identical to a missing-lesson error (equalization);
- missing lesson id → 404;
- orphaned presentation (no owner, no user_id) → 404 for everyone;
- soft-deleted presentation (ownership only via deleted presentation) → 404.

**Service boundary (5)**
- owner can resolve their own lesson id;
- non-owner resolution → `NotFoundError` (404);
- missing → `NotFoundError` (404);
- legacy ownership via direct `lesson.user_id` still honored;
- `None` lesson id passes through → unanchored sessions unchanged.

All 13 tests are discriminating: against the pre-fix implementation the cross-user binds
succeeded (201), so the denial assertions fail on the vulnerable code.

## 5. Verification

| Check | Result |
|---|---|
| `uv tool run --from ruff ruff check app tests` | All checks passed |
| `uv run --project . pytest tests/unit -q` | **1624 passed** |
| `uv run --project . pytest tests/integration -q` | **229 passed** (incl. 13 new) |
| Security scan (AIza…, sk-…, ghp_…, github_pat_…, xoxb-…, BEGIN PRIVATE KEY, client_secret=, access_token=, refresh_token=, password=) | **Clean** — only benign matches (scan-pattern strings in prior audit docs; `create_access_token`/`create_refresh_token` calls in `auth.py`) |
| `git diff --check` | Clean before commit |

## 6. Related-Path Sweep (same root-cause class)

Lesson-by-`public_id` lookups across the backend and their status:

| Location | Status |
|---|---|
| `LearningAssistantService._get_owned_lesson_id` | **fixed in this milestone (B2)** |
| `QuizGenerationService._get_owned_lesson` | already guarded (B1, commit `a34b5d3`) |
| `MasteryTutorService._get_owned_lesson` / `_verify_presentation_owner` / `_verify_concept_ownership` | already guarded |
| `LessonPlayerService._load_accessible_lesson` (`owner_id` enforced at every route) | already guarded |
| `GeneratedLessonRepository.get_by_public_id` | callers (player, worker tasks, generation) owner-scoped or worker-only; no unguarded lesson bind |
| `LessonGenerationService.run_generation` | **worker-only** (`workers/tasks.py:373`) — not an HTTP owner-check gap |
| `RagIndexingService` / `concept_service.get_concept` | worker/internal or non-lesson scoped |

The assistant service was the only remaining lesson-bound session/conversation path without
ownership enforcement.

## 7. No Inventions / Scope Discipline

The milestone addresses exactly one evidence-backed authorization-boundary issue. No P0/P1
gaps from `REMAINING_GAPS.md` (live full-stack smoke test, Python 3.13 vs 3.11 divergence,
LLM-verifier coverage) were touched. Pre-existing untracked release reports were preserved.