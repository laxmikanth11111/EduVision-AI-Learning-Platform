# P2 Data & Runtime Foundation — Audit Notes

**Context:** Phase 2 (WS0–WS13) production data layer, PostgreSQL readiness,
transaction integrity, and runtime reliability hardening for EduVision AI.
These are the working audit notes; the final, evidence-linked report lives in
`P2_DATA_RUNTIME_FOUNDATION_REPORT.md`.

--- 

## Migration state (verified)

- Single Alembic head in the migration chain.
- `0001`..`0027` linear, no branches. Head = `0027_ws5_lesson_user_owner`.
- PG parity migration `0026_ws2_pg_parity`; WS5 migration `0027_ws5_lesson_user_owner`.
- `alembic upgrade head` runs at app lifespan; WS9 added fail-fast control.

## Workstream evidence

### WS0/WS1 — Baseline + verification strategy
- Phase 1 established baseline: unit 798, integration 108, mypy 86 errors /
  25 files (zero-new constraint), ruff clean, single head.
- PG verification suite added as a separately selectable run
  (`pytest -m postgres`); SQLite fast path remains the default
  (`pytest tests -m "not postgres"`).

### WS2 — PostgreSQL real-dialect verification
- Introduced `0026_ws2_pg_parity` and `f0b77b4` fixes: portable JSONB
  (`JSON().with_variant(JSONB(), "postgresql")`), FK enforcement, real dialect
  reporting.
- Fixed migration lineage drift found only by the real-PG run (`a6f3782`).
- Added the `-m postgres` verification suite (`44ee955`).

### WS3 — Commit-before-dispatch reordering
- `presentation_service.set_source` and `generate_lesson` now commit the DB
  transaction before dispatching Celery work, removing the
  dispatch-before-persist race (`b474a21`).

### WS4 — Failure atomicity (orphan upload cleanup)
- `set_source` / `set_thumbnail`: if the DB write fails after the storage
  upload, the freshly uploaded object is best-effort deleted so no orphaned
  blob is left behind (`3cc5c10`).

### WS5/WS8 — Lesson ownership + NULL-user idempotency
- `create_lesson` stamps `user_id` from `presentation.owner_id`.
- `0027_ws5_lesson_user_owner`: partial unique index on `idempotency_key`
  `WHERE user_id IS NULL` (PG + SQLite dialect branches) (`ffdaa0c`, `b91a93c`).

### WS6 — Atomic increment
- `quiz_attempt_service` `quiz.attempt_count += 1` replaced with a SQL
  `UPDATE` (`905d278`). Core lesson `attempt_count` path was already atomic.

### WS7/WS12 — Bounded worker retry + DLQ
- `safe_dispatch` bounded retry with capped exponential backoff, optional
  `on_failure`, and `_forward_to_dlq` (`f045cf9`).

### WS9 — Lifespan fail-fast
- `LIFESPAN_FAIL_FAST_ON_MIGRATION_ERROR` + `AUTO_MIGRATE_ON_STARTUP` controls
  (`820077c`).

### WS10 — Soft-delete consistency (VisualCanvas)
- Soft-deleted canvas sub-graphs are no longer reachable through standalone
  sub-repository queries (`83f18f7`).

### WS11 — Bounded runtime state
- Animation/video runtime sync routers now use a bounded, thread-safe
  `BoundedCache` instead of unbounded module-level dicts (`a854542`).

## Documented-and-deferred (NOT in scope for this phase)
- RAG/document soft-delete consistency on related tables.
- `rag_repository.record_retry` / `GeneratedLesson.schedule_retry` (no callers).
- Cross-replica runtime-state sharing for animation/video (in-memory only).
- Legacy `role`/`student`/`teacher` columns historical fragility (0021) not
  repaired in-phase.
