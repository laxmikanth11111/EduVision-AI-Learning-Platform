# P3 Production Hardening - Foundation Report

**Deliverable:** Phase 3 production-hardening foundation for the EduVision AI
backend (FastAPI + PostgreSQL + Redis + Celery).

This is the evidence-linked summary. Working notes are in
`P3_PRODUCTION_HARDENING_AUDIT.md`. The reference handoffs for prior phases are
`P1_SECURITY_FOUNDATION_REPORT.md` and `P2_DATA_RUNTIME_FOUNDATION_REPORT.md`.

All items below were **executed and verified** during this session unless
explicitly marked not-run.

---

## 1-5. Objective, scope, and guardrails

- **Objective:** execute the Phase 3 production-hardening audit: harden
  worker reliability, observability, query performance, in-process memory
  bounds, dependency/CI hygiene, and docs; keep every Phase 1/2 guarantee
  intact.
- **Scope:** WS1-WS15 implementation + tests + verification on both SQLite
  (fast path) and PostgreSQL (production), security/CI/Docker checks, and the
  required documentation.
- **Guardrails honored:** PostgreSQL is the only production database; SQLite
  stays the dev/test path; no Phase 1/2 regression (mypy budget, single Alembic
  head, ownership/uniform-auth semantics, worker retry/DLQ).
- **Environment:** `backend/.venv` created via `uv sync --extra dev`
  (Python 3.14.6 / pytest 9.1.1 / ruff 0.16.2 / mypy). Real PostgreSQL
  `localhost:5432` and Redis `127.0.0.1:6379`; Docker daemon started for the
  build and testcontainers verification.

## 6. Production database posture

- PostgreSQL is the configured production DB (`postgresql+asyncpg://...`),
  guarded at startup by the Phase-2 fail-fast controls. MySQL is not used.
- The **full Alembic lineage** (`0001` -> `0028`, single head
  `0028_ws10_idempotency_key_index`) was applied live against PostgreSQL on a
  scratch database and verified via the `-m postgres` suite.

## 7-8. Test infrastructure (fast + production paths)

- **SQLite fast path** (default): `pytest tests -m "not postgres"` ->
  **968 passed**, 12 deselected (baseline 939).
- **PostgreSQL production path**: `pytest tests/postgres -m postgres` ->
  **12 passed** under both the local-DSN fallback and the Docker
  (testcontainers) route.
- Test DB moved out of the repo/OneDrive tree to the OS temp dir
  (`EDUVISION_TEST_DB_PATH` still overrides for CI).

## 9-11. Worker reliability (WS6)

- `export_generation_task` now awaits the per-job coroutine via `_run_async`
  instead of `loop.create_task` fire-and-forget, so exports run to completion
  and retry through the existing `safe_dispatch`/`TaskWithDLQ` machinery.
- Covered by `test_export_worker_task.py` (task name, retries, `acks_late`,
  success/failure paths).

## 12-14. Observability (WS8/WS9)

- Structured logging: correct `structlog.contextvars` rollback for worker task
  signal handlers (`reset_contextvars(**tokens)`), one structured event per
  request.
- Metrics: Prometheus request-duration histogram with default buckets and
  label-less `_sum`/`_count` rendering; worker task success/failure counters
  and duration histogram driven by Celery signals; `init_default_metrics`.
- Health/readiness: failure branches (DB exception, DB unhealthy, Redis down,
  storage down) covered in `test_health.py`; `test_metrics.py` and
  `test_worker_observability.py` cover metrics/worker-signal behavior.

## 15-17. Data/query performance (WS1/WS3/WS10)

- `submit_quiz` and attempt-feedback bulk-load explanations, user answers, and
  concept names (`IN` queries) instead of per-question SELECTs.
- `tests/unit/test_quiz_query_count.py` instruments the test engine and
  asserts no N+1 leaks.
- Migration `0028` adds a plain index on `generated_lessons.idempotency_key`
  so key-only dedupe lookups are point queries. Verified on PostgreSQL.

## 18-20. In-process memory bounds (WS4)

- `_VIDEO_BOOKMARKS` / `_VIDEO_ASSESSMENTS` per-session lists capped at 500
  each (oldest evicted); session count already bounded by `BoundedCache(4096)`.
- `animation_runtime_router` holds fixed-size dicts only.
- Resource-limit tests verify eviction behavior.

## 21-24. Auth/ownership (WS11)

- `presentation_service.assert_ownership` returns 404 for ownerless
  presentations, matching the quiz/lesson ownership policy; all create paths
  stamp `owner_id`. Tests: owner 200, cross-user 404, null-owner 404.

## 25-28. Dependencies + CI + security (WS12)

- `requirements.txt` slimmed (test deps removed) so the prod Docker image no
  longer ships pytest/aiosqlite; `requirements-dev.txt` + pyproject dev-extra
  retain them. `testcontainers[postgres]` added to the uv dev-extra and
  lockfile (was manifest drift).
- CI: `migration-check` now runs a **live** `alembic upgrade head` on a
  postgres service container (the prior offline `--sql` step had silently
  regressed on the migration-0014 JSONB seed dict); added a `postgres-tests`
  job and a `secret-scan` job over the tracked tree + full history.
- Secret scan (high-signal patterns: Google OAuth, AWS, GitHub tokens, Slack,
  private keys, OpenAI-style keys): tracked tree and full history **CLEAN**.
  Only an untracked gitignored `.env` holds a real value locally.

## 29-31. Verification results (VERIFIED)

| Gate | Result |
|------|--------|
| Fast suite (`-m "not postgres"`) | 968 passed / 12 deselected |
| PG suite (`-m postgres`) | 12 passed (DSN + testcontainers) |
| Ruff | clean |
| mypy (zero-new) | 85 / 25 files (baseline 86) |
| Migrations | single head; live PG upgrade to 0028 OK |
| Secret scan | CLEAN (tree + history) |
| `git diff --check` | clean |
| Docker build | success; slim prod image (no pytest) |

## 32. Follow-ups / not-run

- **Not-run (this machine):** compliance/DR/SOC policy documentation and
  third-party dependency license review referenced by the original brief are
  documentation tasks, not code changes.
- **Residual:** none of the runnable hardening gates failed; all gaps found
  (worker fire-and-forget, memory bound, N+1, ownership inconsistency, CI
  regression, manifest drift) were fixed and committed.

---

*End of P3 production hardening foundation report.*
HEAD: `89bf3ef` on `feature/individual-user-foundation`.