# Phase 1 — Individual-First Foundation & Production Hardening

**Project:** EduVision AI — AI-Powered Interactive Learning Platform
**Branch:** `feature/individual-user-foundation`
**Base:** `main` @ `998ebe1`
**Date:** 2026-09-01
**Scope:** Phase 1 only. No Phase 2 features (simulation/3D/voice/tutor/Visual Lab) were implemented.

---

## 1. Executive summary

Phase 1 established and enforced the "individual-first" product model and hardened
foundational production surfaces:

- **Individual-user model confirmed & enforced.** The active data model was already
  individual-first (52 tables, no teacher/student/classroom). The obsolete
  multi-role `UserRole` enum was reduced to a single individual `USER` role, the
  legacy teacher/student seed script was migrated to the individual model, and a
  null-owner authorization bypass in the visual-canvas API was closed.
- **Auth reliability.** Refresh-token revocation is now Redis-backed (with the same
  in-memory fallback already used for OAuth state) so a logged-out refresh token is
  rejected across all app instances, not just the process that logged it out.
- **Security.** Upload endpoints now enforce a hard byte limit on the actual request
  body (not just the declared `Content-Length`), preventing unbounded in-memory reads.
- **AI job reliability & cost control.** All 7 services that bypassed the AI
  orchestration layer now route through `AIContentService`, gaining the shared retry
  policy, overall timeout, rate limiting, and response cache.
- **Data integrity.** 4 foreign-key columns that were referenced in queries but lacked
  any index are now indexed (model + migration `0025`); the base-repository delete
  contract was fixed so a delete on a non-soft-deletable model hard-deletes instead of
  silently no-oping.

**Correction to a Phase 0 finding:** Phase 0 reported "real secrets committed in
`.env.example`". This was **overstated** — `git grep` across all history shows the
committed `.env.example` files contain only placeholders, and real credentials live
only in the untracked, gitignored `backend/.env`. No secret was ever committed.

**Verification:** full unit regression **753 passed** (739 baseline + 14 new), ruff
clean on `app`/`tests`/`scripts`, all modules compile and `app.main` imports.

---

## 2. Individual-first model verification

Verified (unchanged, previously established):
- Active models contain **no** `student_*`/`teacher_*`/`classroom` tables (52
  `__tablename__`s inspected).
- No active (non-migration) `app/` code branches on `student`/`teacher`/`classroom`.
- Active frontend (`backend/frontend/`) uses a single "Dashboard" nav — already
  individual-first.
- JWT always carries `role="user"`; the `User` model stores no `role` column (role is
  a claim-only concept).

## 3. UserRole simplification (individual user)

`backend/shared/constants/__init__.py` — the enum previously declared
`STUDENT/TEACHER/ADMIN/SUPER_ADMIN`. None of these were used in active application
code except as dead type annotations. Replaced with a single individual role:

```python
class UserRole(str, Enum):
    USER = "user"
```

- Value `"user"` matches the existing `role="user"` JWT claim so outstanding access
  tokens remain valid.
- `backend/scripts/seed_manual_test.py` referenced `UserRole.TEACHER`/`STUDENT`;
  rewritten to seed a single owner user (plus an optional collaborator), both
  individual `USER` roles.
- `app/schemas/user.py` (`UserResponse` with `role`) is unused dead code but still
  type-checks.

## 4. Authentication — Redis-backed refresh-token revocation

`backend/app/api/v1/auth.py`:
- Previously `_revoked_refresh_jtis: set[str]` was process-local, so a refresh token
  revoked on instance A could still be used against instance B.
- Now `_revoke_refresh_jti(jti)` writes the JTI to Redis
  (`eduvision:auth:revoked:refresh:<jti>`) with a TTL equal to the refresh-token
  lifetime; `_is_refresh_jti_revoked(jti)` checks Redis. Falls back to an in-memory
  set when Redis is unreachable (mirroring the existing OAuth-state pattern), so
  revocation still works during a Redis outage on the issuing process.
- `logout` and `/refresh` use the new async helpers.

## 5. Authorization — visual-canvas null-owner bypass closed

`backend/app/api/v1/visual_canvases.py:_assert_canvas_owner`:

```python
if canvas.user_id is None or str(canvas.user_id) != str(user.id):
    raise NotFoundError(...)
```

Previously a canvas with `user_id IS NULL` was readable/writable/deletable by any
authenticated user. Now a canvas is accessible only to its owning user; an unowned
canvas returns 404 to everyone. `list_user_canvases` already scoped by `user_id`, so
no unowned canvas appears in listings.

## 6. Security — bounded file uploads

`backend/app/api/v1/presentations.py` adds `_read_upload_bounded(upload)` and uses it
in `upload_source` and `upload_thumbnail`. It reads at most
`settings.UPLOAD_MAX_FILE_SIZE` (100 MB) + 1 bytes and raises
`413 CONTENT_TOO_LARGE` when the actual body exceeds the cap. The request-size
middleware only enforced the declared `Content-Length`; this closes the gap for
misdeclared/chunked bodies, preventing unbounded in-memory reads.

## 7. AI orchestration — route all generation through AIContentService

`backend/app/ai/service.py` adds a lazy module singleton `get_ai_content_service()`
(non-persistent; usage accounting is skipped when no `UnitOfWork` is supplied, which
is appropriate for these stateless generators). It applies the shared retry policy,
overall timeout, rate limiter, and response cache.

The following services stopped calling `AIProvider.generate` directly and now go
through `AIContentService.generate`:
1. `app/services/component_discovery_service.py`
2. `app/services/visual_classifier_service.py`
3. `app/services/visualization_decision_service.py`
4. `app/services/learning_objective_service.py`
5. `app/services/relationship_engine_service.py`
6. `app/services/quiz_generation_service.py`
7. `app/services/learning_assistant_service.py`

The `get_ai_provider()` factory and the `get_ai` FastAPI dependency remain as
infrastructure.

## 8. Data integrity — missing FK indexes

Analysis (not assertion) identified the exact columns referenced in queries that lack
index coverage (unique-constrained columns and composite-index-covered columns were
excluded):

| Table.column | New model `index=True` | Migration |
|---|---|---|
| `question_attempts.question_id` | ✅ | `0025` |
| `quiz_attempts.quiz_version_id` | ✅ | `0025` |
| `quizzes.lesson_version_id` | ✅ | `0025` |
| `user_answers.question_attempt_id` | ✅ | `0025` |

Notes:
- `quiz_attempts.quiz_id` is covered by `ix_quiz_attempts_quiz_user`; `quiz_versions.quiz_id`
  by `ix_quiz_versions_quiz_id`; `answer_keys.question_id`,
  `question_explanations.question_id`, and `score_summaries.attempt_id` are covered by
  their unique constraints — intentionally **not** re-indexed.
- Model changes benefit fresh `create_all` databases; migration `0025_fk_indexes`
  (attached to head `0024`) applies the indexes to existing databases. Adding an index
  is purely additive and cannot fail on populated data.

## 9. Data integrity — soft-delete consistency

`backend/app/database/repository.py:delete`:
- Previously `delete(hard=False)` on a model without `soft_delete` **silently no-oped**
  (the row was neither marked nor removed).
- Now, a non-soft-deletable model falls back to a hard delete, preserving the delete
  contract: a requested delete must never silently do nothing.
- Soft-deletable models still set `deleted_at` and flush (caller commits via UoW,
  consistent with `create`/`update`).

## 10. Known pre-existing conditions (not regressions, not fixed in Phase 1)

- **Alembic migration chain on Postgres** is documented as stuck at `0020`
  (`0021` fails on pre-existing `assistant_sessions`). This predates Phase 1 and is
  tolerated by the app (per `MEMORY.md`). `0025` attaches to head `0024`. Applying any
  migration requires a Postgres instance (Docker unavailable in this environment);
  this is deferred and should be repaired against a real database before any
  non-additive migration.
- **mypy is not a clean gate:** 66 pre-existing errors exist in untouched files
  (`workers/tasks.py`, `workers/rag_tasks.py`, `services/presentation_service.py`,
  `services/rag_indexing_service.py`, `services/topic_outline_service.py`, and
  untouched line ranges in partially-edited services). None of the lines changed in
  Phase 1 introduce a new mypy error.
- **Local live credentials:** `backend/.env` (untracked, gitignored) contains a live
  Gemini key, which `MEMORY.md` reports as **out of quota**, plus live Google OAuth
  credentials. Recommend rotating all three via their console dashboards as a
  precaution (they were handled in plaintext locally). No action strips them; they are
  not in version control.
- **Redis Windows service** has been observed frozen since 8/19 (accepts TCP, never
  replies). This is a documented environment condition.

## 11. Tests added / updated

`backend/tests/unit/test_phase1_integrity.py` (14 tests):
- visual canvas: null-owner and other-owner denied; owner allowed
- bounded upload: within limit accepted; over limit → 413
- `UserRole` is individual `USER`; no legacy members
- base repository delete: hard-delete fallback for non-soft-deletable; soft-delete
  sets `deleted_at`
- refresh-token revocation: revoke+detect (in-memory fallback); unrevoked → not revoked
- migration `0025`: revision chain; upgrade adds the 4 expected FK indexes; model
  agreement (indexes exist in metadata)

`backend/tests/unit/test_component_discovery_granularity.py` — updated the mock target
from `get_ai_provider` to `get_ai_content_service` (the refactored entry point).

## 12. Verification results

| Check | Result |
|---|---|
| Unit regression (`pytest tests/unit`) | **753 passed** (baseline 739 + 14 new) |
| Ruff (`ruff check app tests scripts`) | clean / all checks passed |
| Module compile + `app.main` import | OK |
| mypy on changed files | no new errors from Phase 1 changes (66 pre-existing elsewhere) |

## 13. Files changed

**Modified (19):** `app/ai/service.py`, `app/api/v1/auth.py`, `app/api/v1/presentations.py`,
`app/api/v1/visual_canvases.py`, `app/database/repository.py`, `app/models/question_attempt.py`,
`app/models/quiz.py`, `app/models/quiz_attempt.py`, `app/models/user_answer.py`,
`app/services/component_discovery_service.py`, `app/services/learning_assistant_service.py`,
`app/services/learning_objective_service.py`, `app/services/quiz_generation_service.py`,
`app/services/relationship_engine_service.py`, `app/services/visual_classifier_service.py`,
`app/services/visualization_decision_service.py`, `app/shared/constants/__init__.py`,
`app/services/../scripts/seed_manual_test.py`,
`tests/unit/test_component_discovery_granularity.py`.

**Added (2):** `app/database/migrations/versions/0025_fk_indexes.py`,
`tests/unit/test_phase1_integrity.py`.

## 14. Operational recommendations (follow-up, not Phase 1 code)

1. Rotate the Gemini key and Google OAuth client secret in `backend/.env`.
2. Repair the Alembic chain (`0021` -> head) against the real Postgres in a staging
   environment, then apply `0025`.
3. Decide whether `app/schemas/user.py` dead code should be removed.
4. Restart/repair the frozen Redis Windows service for OAuth/revocation reliability.

## 15. Out of scope (Phase 2+, not implemented)

Simulation engine, 3D visualizations, voice/audio, AI tutor, Visual Lab, or any
multi-role (teacher/student) features. Nothing above invents product behavior; all
changes preserve existing functionality.

## 16. How to verify

```powershell
# from backend/
.venv\Scripts\python.exe -m pytest tests/unit -q          # 753 passed
.venv\Scripts\python.exe -m ruff check app tests scripts  # clean
.venv\Scripts\python.exe -c "import app.main; print('ok')"
```
