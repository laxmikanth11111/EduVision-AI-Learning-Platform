# P2 — Production Data Layer, PostgreSQL Readiness, Transaction Integrity & Runtime Reliability

**Branch:** `feature/individual-user-foundation`
**Status:** COMPLETE
**Date:** 2026-09-01

This is the Phase 2 foundation report (WS0–WS13). It is split into 30 numbered
sections. Every runtime claim is tied to a committed change and to an executed
test result; anything not verified is explicitly marked **NOT VERIFIED** rather
than asserted.

---

## 1. Execution summary

Phase 2 hardened EduVision's data layer for production: a real-PostgreSQL
verification suite is now selectable alongside the fast SQLite path, every live
database mutation goes through Alembic migrations with a single head, the
remaining non-atomic live-path increment was made atomic, worker dispatch now
happens only after commit, worker retries are bounded with a DLQ, startup is
fail-fast on migration errors, orphaned uploads are cleaned up on DB failure,
and unbounded in-memory runtime state is now bounded.

**Verified test results (run this phase):**
- Non-PG (SQLite) suite: **929 passed**, 12 deselected, 0 failed.
- PG suite (`-m postgres`): **12 passed**, 929 deselected, 0 failed.
- `ruff check` clean on all changed files.
- mypy: zero new errors from this phase (see §11).

---

## 2. Baseline (Phase 1 hand-off)

- Unit tests: 798; integration tests: 108.
- mypy: 86 errors across 25 files (zero-new constraint in force).
- ruff: clean.
- Alembic: exactly one head.
- Single-user ownership model and security guarantees (quiz IDOR protection,
  upload validation, scoped storage download) established.

---

## 3. Goals of Phase 2

1. Keep the fast SQLite path as the default dev loop.
2. Add a genuinely separate, real-PostgreSQL verification suite that runs only
   when explicitly requested.
3. Close transaction-integrity gaps (dispatch-before-commit, non-atomic
   increments, orphaned uploads on partial failure).
4. Make runtime infrastructure reliable in production (bounded retries, DLQ,
   fail-fast startup, bounded state, soft-delete isolation).
5. Prove every claim honestly; defer what cannot be safely changed.

---

## 4. WS0 — Verification strategy

- SQLite fast path preserved as default: `pytest tests -m "not postgres"`.
- PG suite isolated by marker: `pytest -m postgres`, driven by
  `CI_DATABASE_URL=postgresql+asyncpg://...`.
- PG suite runs against a real local PostgreSQL 16 instance on port 5433.

---

## 5. WS1 — Baseline confirmation & guardrails

- Confirmed single head, clean ruff, mypy zero-new constraint.
- Established the commit discipline: each workstream lands as one
  `type(scope): message` commit with its tests; history is never rewritten.

---

## 6. WS2 — PostgreSQL real-dialect verification

Deliverables and commits:
- `f0b77b4` — portable JSONB (`JSON().with_variant(JSONB(), "postgresql")`),
  FK enforcement, real-dialect reporting.
- `a6f3782` — fix migration lineage drift surfaced only by the real PG run.
- `44ee955` — add the `-m postgres` verification suite.

**VERIFIED:** PG suite 12/12 passing; SQLite path shows no regression
(906 passing at that time; 929 by the final regression).

---

## 7. WS2 outcomes — schema/parity handling

- `questions.concept_id` UUID with guarded index `ix_questions_concept_id`.
- `user_answers.order_values`.
- `concepts` table.
- `learning_events` columns.
- `answer_keys.public_id` / `scoring_rule` nullability relaxations.
- `question_explanations.public_id` nullability relaxation.
- All schema changes flowed through Alembic; single head maintained.

---

## 8. WS3 — Commit-before-dispatch

`presentation_service.set_source` and `generate_lesson` now commit the DB
transaction **before** dispatching Celery work, eliminating the
dispatch-before-persist race where a worker could observe work that the
database had not yet committed.

**VERIFIED:** 3 new unit tests in `test_presentation_service.py`; full suite
green. Commit `b474a21`.

---

## 9. WS4 — Failure atomicity (orphan upload cleanup)

In `set_source` / `set_thumbnail`, if the storage upload succeeds but the DB
write fails, the freshly uploaded object is best-effort deleted via
`_storage_delete_best_effort`, leaving no orphaned blob.

**VERIFIED:** 3 new unit tests in `test_presentation_service.py`; green.
Commit `3cc5c10`.

---

## 10. WS5/WS8 — Lesson ownership + NULL-user idempotency

- `create_lesson` stamps `user_id = presentation.owner_id`.
- Migration `0027_ws5_lesson_user_owner` adds a partial unique index on
  `idempotency_key WHERE user_id IS NULL` (PG + SQLite dialect branches) so
  unowned lessons stay uniquely idempotent while owned lessons are scoped by
  user.

**VERIFIED:** unit tests + PG integrity tests; head upgraded to `0027_ws5...`;
single head confirmed. Commits `ffdaa0c`, `b91a93c`.

---

## 11. WS6 — Atomic increment

The only non-atomic live-path increment remaining was `quiz.attempt_count` in
`quiz_attempt_service.py`; converted to a SQL `UPDATE ... VALUES
(attempt_count = attempt_count + 1)`. The core lesson `attempt_count` path was
already a conditional SQL-side UPDATE and is unchanged.

**VERIFIED:** no behavior change; suite green. Commit `905d278`.

---

## 12. WS7/WS12 — Bounded worker retry + DLQ

`safe_dispatch` now: bounded retry count, capped exponential backoff, optional
`on_failure` callback, and `_forward_to_dlq` when `CELERY_TASK_DLQ_ENABLED`.

**VERIFIED:** 5 new tests in `test_embedding_worker_tasks.py`; green.
Commit `f045cf9`.

---

## 13. WS9 — Lifespan fail-fast

New settings `AUTO_MIGRATE_ON_STARTUP` and `LIFESPAN_FAIL_FAST_ON_MIGRATION_ERROR`;
the lifespan raises `RuntimeError("Database migration failed at startup;
refusing to start")` on migration failure when enabled, tolerant warning
otherwise.

**VERIFIED:** 4 new unit tests in `test_lifespan_failfast.py` (patch
`alembic.command.upgrade`); green. Commit `820077c`.

---

## 14. WS10 — Soft-delete consistency (VisualCanvas)

Soft-deleted canvases keep their sub-graph rows (so restore is possible), but
standalone sub-repository queries (nodes/edges/relationships/layout/
quiz-blueprint by canvas) previously returned rows regardless of the parent
canvas's `deleted_at`. Each canvas-scoped sub-query now verifies the parent
canvas is present **and not soft-deleted**, raising `NotFoundError` otherwise.

**VERIFIED:** 3 new unit tests in `test_visual_canvas_soft_delete.py`; green;
PG suite green. No schema change required. Commit `83f18f7`.

---

## 15. WS11 — Bounded runtime state

Animation and video runtime sync routers kept per-session state in unbounded
module-level dicts, so a long-running server accumulated memory without limit.
Replaced with a bounded, thread-safe `BoundedCache` (`app/utils/bounded_cache.py`)
that evicts the least-recently-written session once capped.

**VERIFIED:** 4 new unit tests in `test_bounded_cache.py`; runtime router tests
green; behavior unchanged. Commit `a854542`.

---

## 16. Migration discipline

- Every database change in this phase went through an Alembic migration
  (`0026`, `0027`).
- Single head verified programmatically: `0027_ws5_lesson_user_owner`.
- `alembic upgrade head` runs at app startup (WS9 gate).

---

## 17. SQLite fast path preserved

The default test/dev loop remains SQLite; PG is opt-in via `-m postgres`. No
SQLite-only regression was introduced (929 non-PG passing final).

---

## 18. PostgreSQL suite status

**VERIFIED:** 12/12 passing against real PostgreSQL 16 (asyncpg) on port 5433.
Covers integrity constraints, partial index behavior, and migration head
assertions.

---

## 19. Transaction integrity summary

| Concern | Status |
|---|---|
| Dispatch before commit (source upload, lesson gen) | FIXED (WS3) |
| Orphaned upload on DB failure | FIXED (WS4) |
| Non-atomic quiz attempt increment | FIXED (WS6) |
| Lesson owner stamping + NULL-user idempotency | FIXED (WS5/WS8) |
| Failed-startup migration | FIXED (WS9 fail-fast) |

---

## 20. Concurrency & retry summary

- Bounded worker retry with capped backoff (WS7).
- Dead-letter queue support (WS12).
- `rag_repository.record_retry` / `GeneratedLesson.schedule_retry`: **no
  callers** — documented-and-deferred, not changed.

---

## 21. Runtime reliability summary

- Fail-fast startup on migration error (WS9).
- Bounded in-memory runtime state with LRU-style eviction (WS11).
- Soft-delete isolation for visual graphs (WS10).

---

## 22. Ownership & isolation

- Lessons carry owner (`user_id`) from the presentation owner (WS5).
- Idempotency uniqueness preserved for unowned (NULL-user) lessons via a
  partial unique index (WS8).
- Visual-canvas sub-graph data cannot leak from soft-deleted canvases (WS10).
- Phase 1 security guarantees (quiz IDOR protection, upload validation,
  scoped storage) unregressed.

---

## 23. Code quality gates

- `ruff check`: clean on all changed files.
- mypy: zero new errors attributable to this phase (see §11 note on
  pre-existing model type errors).
- Commits are logically grouped per workstream with `type(scope): message`.

---

## 24. Test inventory added this phase

- PG verification suite (`-m postgres`, WS2).
- Presentation service: dispatch-after-commit + orphan-cleanup tests (WS3/WS4).
- Lesson owner + partial-index + PG integrity tests (WS5/WS8).
- Embedding worker retry/DLQ tests (WS7/WS12).
- Lifespan fail-fast tests (WS9).
- Runtime-router bounded state tests (WS11).
- Visual-canvas soft-delete isolation tests (WS10).

---

## 25. Final regression (WS13)

**VERIFIED, run after all workstreams committed:**
- Non-PG: 929 passed, 12 deselected, 0 failed.
- PG: 12 passed, 929 deselected, 0 failed.
- ruff clean; single head; mypy zero-new.

---

## 26. What is NOT verified

- Cross-replica sharing of animation/video runtime state (in-memory only; a
  known Phase-4 prototype limitation — deferred).
- Real multi-worker Celery concurrency under production load (unit/integration
  coverage only).
- Historical migrations 0001–0025 on a fresh production Postgres (documented as
  fragile, notably 0021) — not repaired in-phase.

---

## 27. Risks & mitigations

- **In-memory runtime/project state:** bounded (WS11) but not distributed;
  acceptable for single-instance pilot, revisit for horizontal scaling.
- **RAG soft-delete consistency** on related tables remains partially
  documented-and-deferred; not a live-path data-integrity regression.

---

## 28. Commits delivered (newest last)

- `83f18f7` fix(visual): soft-deleted canvas sub-graph isolation
- `a854542` fix(runtime): bound in-memory sync state
- `3cc5c10` fix(storage): orphan upload cleanup on DB failure
- `820077c` feat(main): fail-fast startup on migration errors
- `f045cf9` feat(worker): bounded retry + DLQ for safe_dispatch
- `905d278` fix(quiz): atomic attempt counter increment
- `b91a93c` test(db): owner stamping / NULL-user idempotency / PG partial index
- `ffdaa0c` fix(lesson): stamp user_id from owner; guard NULL-user idempotency
- `b474a21` fix(worker): commit before dispatch
- `44ee955` test(db): PG verification suite
- `a6f3782` fix(db): migration lineage drift
- `f0b77b4` fix(db): portable JSONB, enforce FKs, real dialect

---

## 29. Documented-and-deferred

- Cross-replica runtime state (animation/video).
- `record_retry` / `schedule_retry` (no callers).
- Historical 0001–0025 migration fragility on fresh Postgres.
- RAG-related soft-delete consistency breadth.

---

## 30. Conclusion

Phase 2 is complete and verified. The SQLite fast path is unchanged, the
real-PostgreSQL verification suite is green and separately selectable,
transaction-integrity and runtime-reliability gaps are closed and covered by
tests, the migration chain is single-headed, and no Phase 1 security guarantee
regressed and no new mypy errors were introduced. Remaining gaps are explicitly
bounded and documented for follow-up phases.
