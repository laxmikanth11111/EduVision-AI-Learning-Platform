# P3 Production Hardening - Audit Notes

**Context:** Phase 3 (production hardening) for the EduVision AI backend
(FastAPI + PostgreSQL + Redis + Celery). Covers audit point-in-time state,
the WS1-WS15 hardening workstreams, test/CI/security/Docker verification, and
the log of gate results. The evidence-linked final summary lives in
`P3_PRODUCTION_HARDENING_FOUNDATION_REPORT.md`.

Hard constraints observed throughout:

- **PostgreSQL is the production database** (never MySQL); SQLite remains the
  fast dev/test path only.
- **Phase 1 / Phase 2 guarantees must not regress** (mypy error budget,
  single Alembic head, initmsgs).
- Only results that were **actually executed** are marked VERIFIED.

---

## 0. Point-in-time state (audit start)

- Branch `feature/individual-user-foundation`; HEAD prior `44383a0`
  (config fail-fast for secrets/service URLs).
- Environment: no venv at start; `uv sync --extra dev` created
  `backend/.venv` -> Python 3.14.6, pytest 9.1.1, ruff 0.16.2, mypy.
- Docker CLI v29.6.2 + Compose v5.3.1 present; daemon initially **down**.
- Real PostgreSQL on `localhost:5432` (role `eduvision`, CREATEDB); Redis on
  `127.0.0.1:6379`.
- Baseline fast path (`pytest tests -m "not postgres"`): **939 passed** /
  1 failed (stale health assertion) / 12 deselected. Fixed -> 940 expected.
- Mypy baseline: **86 errors / 25 files** (zero-new constraint).

---

## 1. Workstream evidence

### WS1 - Repo / test-artifact hygiene
- `tests/conftest.py` `TEST_DB_PATH` default moved out of the repo/OneDrive
  tree to the OS temp dir (`tempfile.gettempdir()/eduvision_testdb/test.db`);
  `EDUVISION_TEST_DB_PATH` still overrides for CI/integration.
- Removed the stale `backend/test.db` artifact from disk; confirmed no other
  references (`rootauthor` script scan).
- VERIFIED: full suite passes from the new temp location.

### WS3/WS10 - Query-count N+1 regression (quiz submission)
- `submit_quiz` and feedback (`get_attempt`) now bulk-load question
  explanations, user answers, and concept names via `IN` queries instead of
  one SELECT per question.
- Added `tests/unit/test_quiz_query_count.py`: instruments the test engine
  with a `before_cursor_execute` listener and asserts **no**
  per-question singleton SELECTs leak back on submit and that bulk `IN`
  queries are issued.
- Added migration `0028_ws10_idempotency_key_index`: plain index on
  `generated_lessons.idempotency_key` for the key-only dedupe lookup (the
  composite/partial constraints cannot serve a key-only predicate).
- VERIFIED: query-count test passes; full 0001->0028 lineage applies cleanly
  on real PostgreSQL; head contract updated in `-m postgres` tests.

### WS4 - Bounded per-session runtime memory
- `_VIDEO_BOOKMARKS` / `_VIDEO_ASSESSMENTS` were BoundedCache by key (4096)
  but each per-session list grew without bound. Added `_append_capped`
  (500 bookmarks, 500 assessments per session) evicting oldest entries.
- `animation_runtime_router` holds only fixed-size dicts per key -> no change.
- VERIFIED: resource-limit tests (7 writes -> 5 retained, oldest evicted)
  pass.

### WS6 - Worker export reliability
- `export_generation_task` was `loop.create_task` fire-and-forget; now awaited
  via `_run_async` so it runs to completion and retries on failure.
- VERIFIED: `test_export_worker_task.py` (task contract + success/failure).

### WS8/WS9 - Health readiness + observability
- Readiness/healthcheck failure branches covered: DB exception, DB unhealthy
  (False), Redis down, storage down; asserts `status`, per-check status, and
  the sanitized error detail (`test_health.py`).
- Finished in-flight observability: structlog contextvars rollback for worker
  tasks (`reset_contextvars(**tokens)`), Prometheus request-duration histogram,
  worker task success/failure counters + duration histogram, label-less
  `_sum`/`_count` rendering.
- VERIFIED: `test_metrics.py`, `test_worker_observability.py`.

### WS11 - Uniform ownership policy
- `presentation_service.assert_ownership` previously returned ownerless
  presentations to any authenticated user; now raises 404, matching the
  quiz/lesson uniform ownership policy. All create paths stamp `owner_id`.
- VERIFIED: owner 200, cross-user 404, null-owner 404.

### WS12 - Dependency + CI/security hardening
- Removed test-only deps (pytest stack, aiosqlite) from `requirements.txt`
  so the prod Docker image no longer ships them; present in
  `requirements-dev.txt` and the pyproject dev-extra.
- Fixed pt. dev-extra drift: `testcontainers[postgres]` added to pyproject
  dev (only requirements-dev had it), lockfile updated.
- CI: `migration-check` now runs a **live** `alembic upgrade head` against a
  postgres service container (the previous offline `--sql` step could not
  render the JSONB seed dict literal in migration 0014 and had silently
  regressed). Added `postgres-tests` job and a `secret-scan` job.
- Secret scan (high-signal patterns): tracked tree + full history **CLEAN**.
  (Local `.env` with a Google OAuth secret is gitignored/untracked.)

---

## 2. Gate results (all VERIFIED this session)

| Gate | Command / method | Result |
|------|------------------|--------|
| Fast test suite | `pytest tests -m "not postgres"` | **968 passed**, 12 deselected (baseline 939) |
| PG suite (env DSN) | `pytest tests/postgres -m postgres` (local PG) | **12 passed** |
| PG suite (testcontainers) | `pytest tests/postgres -m postgres` (Docker) | **12 passed** |
| Ruff | `ruff check app tests scripts --no-fix` | clean |
| mypy | `mypy app` | 85 errors / 25 files (baseline 86 - no regression) |
| Migrations | single head, live `alembic upgrade head` on PG | head `0028_ws10_idempotency_key_index`, applies cleanly |
| Security tests | full suite included above | pass |
| Secret scan | Python regex scan, tracked tree + history | CLEAN |
| `git diff --check` | whitespace | clean |
| Docker build | `docker build -f backend/Dockerfile backend` | succeeded; prod image imports fastapi/sqlalchemy/asyncpg/celery, **no pytest** |

---

## 3. Residual / not-run items

- Compliance/legal audit items in the original 35-section brief beyond the
  hardening workstreams above (secret rotation policy, IR/DR runbooks) are
  policy documentation, not code changes; flagged for the follow-up track.

## 4. Commits produced (newest -> oldest)

- `89bf3ef` build(dev): testcontainers to uv dev-extra
- `4b13158` ci: real-PG migration check + postgres suite + secret scan; slim prod image
- `685984a` fix(runtime): bound per-session bookmark/assessment lists
- `4b332d3` perf(quiz): bulk-load submission details + idempotency index (WS1/WS3/WS10)
- `d25770d` fix(auth): uniform 404 for ownerless presentations (WS11)
- `8b8a6ee` fix(workers): await export generation (WS6)
- `18e917c` feat(obs): logging, histograms, worker task metrics (WS8/WS9)