# P17 — Production Reliability & Scale Foundation: Audit

**Baseline verified** on `feature/individual-user-foundation` at `68a601b` (P16):

| Gate | Result |
|---|---|
| SQLite unit + integration | **1327 passed** |
| PostgreSQL | **40 passed** |
| Browser E2E | **26 passed** |
| Ruff | clean |
| Mypy (`mypy app`) | **85 errors / 25 files / 314 sources** — authoritative P17 starting baseline, zero-new policy in force |
| Alembic | single head `0034_video_projects` |
| Working tree | clean |

> Note: P14–P16 docs anecdotally reported `83/24`; the actually measured baseline is `85/25` (checked 314 files). P17 treats `85/25` at this commit as the authoritative floor.

This document is the C0 reliability audit with exact evidence. Fixes live in the checkpoint workstreams C1–C15 (below). No features were implemented to produce this audit.

---

## R1 — Database reliability

- **Engine** (`app/database/session.py:19-34`): prod `AsyncAdaptedQueuePool` size 20 / overflow 10 / timeout 30s / recycle 1800s / pre-ping True (`app/core/config.py:34-38`); tests `NullPool`. Explicit and reasonable — no blind tuning needed.
- **BUG (fixed C1):** `UnitOfWork._commit_with_retry` (`app/database/unit_of_work.py:46-59`) retried a failed commit **without rolling back the aborted PG transaction** — after a `40001/40P01` the session's transaction is aborted and every retry fails forever. `retry_on_db_failure` (`app/database/retry.py:33-77`) had no between-attempt hook.
- **BUG (fixed C1):** `render_now` FAILED branch (`app/services/video_project_service.py:173-182`) committed the terminal state on a session whose transaction may be aborted by a failed `RENDERING` commit.
- Mid-flow durability commits (`video_project_service.py:76,132,154,177,187,198`, `auth.py:185,342`, `presentation_service.py:711,824`) are deliberate commit-before-dispatch/return; documented as an atomicity trade-off (never "transactional everything").
- Swallowed DB failures: `animation_runtime_router.py:81-82`, `video_runtime_router.py:115-116` (milestone writes, debug-only log), `quiz_attempt_service.py:588-589`, `learning_assistant_service.py:484-485,554-555` (silent enrichment degradation). Documented; not necessarily wrong (read-path degrade).
- Test DB does not exercise pooled concurrency (both test engines `NullPool`) — accept; covered by C11 stress on Postgres where practical.

## R2 — Redis reliability

- Client (`app/workers/redis_client.py`): lazy pool, `retry_on_timeout=True`, 10s socket timeout, no circuit breaker, no command-level retry. Resilience helpers (`check_redis_connection`, `redis_with_retry`) exist but are unused.
- Classification:
  - **CRITICAL** (correctness/job loss when down): every `safe_dispatch` enqueue (6 sites, `app/workers/tasks.py:92-137` + producers), video render celery dispatch (`video_render_executor.py:32-45`, single un-retried `send_task`), Celery broker/result DBs.
  - **DEGRADABLE**: HTTP rate limiting (fail-open, **sticky-disabled forever after one error** — `app/middleware/rate_limit.py:110-111,207-209`; **unit-mismatch bug**: ms passed as seconds into the Lua script and Z-counts — limiter effectively never 429s, `rate_limit.py:283`), auth JTI revocation (`auth.py:50-83` in-memory fallback, cross-instance fail-open), OAuth state (`auth.py:86-122`).
  - **OPTIONAL**: health checks.
- **Idempotency service is dead code**: `TaskIdempotencyService`/`idempotent_task` (`app/workers/idempotency.py`) never wired; `CELERY_IDEMPOTENCY_ENABLED` (`config.py:381`) unread. Redis-reliant locks have no owner token (blind DEL), 30s TTL.
- `CacheService` (`app/workers/cache.py`) and `get_redis` DI (`dependencies.py:33-35`) unused.

## R3 — Celery reliability

- Strong baseline: `task_acks_late=True`, `task_reject_on_worker_lost=True`, `prefetch_multiplier=1`, bounded dispatch retry, commit-before-dispatch everywhere, `task_store_errors_even_if_ignored=True`, X-Request-ID propagation into workers.
- **Gaps:** DLQ off by default (`CELERY_TASK_DLQ_ENABLED=False`, `config.py:66`) ⇒ retry-exhausted and broker-down jobs silently dropped (log+metric only); `eduvision.dlq.record` sink is **log-only** (no persistence/replay); 6 presentation tasks lack `base=TaskWithDLQ`; video render celery dispatch has **zero retry**; `safe_dispatch` blocks the event loop with `time.sleep` (called from async services); `broker_connection_retry_on_startup=False`; phantom routes (`ai/uploads/notifications/email` — zero registered tasks); no per-task time limits (global 3600/3000s); no admin task-status endpoint.
- `idempotent_task` decorator unused; duplicate suppression relies on ad-hoc DB status guards (which are themselves mostly correct).

## R4 — Background job reliability

- Per-task table documented (17 tasks) — see `P17_IMPLEMENTATION_REPORT.md` appendix. Embedding job/batch pipeline has DB-status idempotency (`QUEUED` guard) and a stagger; batches requeued max 1 (`config.py:293`).
- Eager-mode fire-and-forget (`presentation_service.py:718-719,825-830`) bypasses Celery retry/acks; process crash mid-run leaves non-terminal DB rows with no recovery cron (documented, accepted dev-mode path).

## R5 — Concurrency

- Per-user video-render cap is enforced at service level before queueing (`video_project_service.py:60-69,117-126`) + inline executor; **needs a true concurrent-request test** (C4/C6).
- `presentation_version_service` retries version races (max 3) with rollback on IntegrityError.
- No correctness-critical process-local locks found; ownership scoping is DB-filter based everywhere.

## R6 — Idempotency

- DB constraints + status guards solve most write duplication today (video `QUEUED/RENDERING` guard, embedding job/batch status guards, review outcome single-write, exam attempt status). Investigated adding `Idempotency-Key` infra — not justified. **C5 adds duplicate/concurrent/after-timeout tests to prove the existing guards.**

## R7 — Distributed state

- No leader election, no distributed locks beyond unused idempotency locks, no cross-process session state. Auth JTI/OAuth in-memory fallbacks are per-instance (multi-instance outage widows documented). Rate limiter is the only shared-coordination path and it fail-opens.
- **Not required to become distributed:** everything process-local that is `CACHE ONLY` (bounded caches) stays local (see R9).

## R8 — Observability

- Metrics: bounded-labels mostly respected; **violations found:** `embedding_batches_processed_total{job_id}` / `embedding_batches_failed_total{job_id}` (`rag_tasks.py:225,227`) — unbounded DB-PK label (fix C7); HTTP duration histogram has **no labels** (`logging.py:63`); raw-path fallback on 404s (`logging.py:19-26`) can unbounded `http_requests_total`. `p15_position_updates_total` increment has **no registration** (`learning_session_service.py:201`).
- **Missing (C7):** AI request failures/latency/retries, DB error counter, Redis error counter, worker-side retry counter, rate-limit rejection counter.
- Logging: `LOG_MASK_SENSITIVE` masks key-named values but **only str values** (`logging.py:47-48`); raw query strings logged unredacted (`logging.py:49`); plaintext `email` in `user_registered`/`google_oauth_success` logs (`auth.py:186,343`).

## R9 — Health / readiness

- `GET /api/v1/health` returns **200 even when degraded** (`health.py:51-53`); `/health/live` no checks; `/health/ready` returns **200 with `status: not_ready`** (`health.py:88-91`) — orchestrators/healthchecks cannot distinguish. Readiness checks DB+Redis+storage but **not Celery** (`health.py:76-86`). Storage check does full bucket listing per probe. **C8 fixes status semantics + adds tests.**

## R10 — Failure recovery

- Strong: stream-rolled UoW, transient-commit retry (now with rollback), mark-failed-on-exception video path, embedding partial-failure recovery, DLQ hooks.
- Weak/documented: `dlq.record` not persisted; video render celery dispatch no retry; inline render fire-and-forget leaves `RENDERING` rows orphaned if the process dies mid-render (no recovery job) — a known P16 limitation, recorded as deferred.

## R11 — Performance

- No N+1 found in the audited read paths (P15 progress is a single join). Owner-scoped queries are filtered by user_id in SQL. PG EXPLAIN spot-checks to be run in C10; only justified additive indexes. `video_projects` already has `(user_id, status)` composite.
- Known hot spots to verify: review queue listing, analytics aggregates, dashboard.

## R12 — Deployment readiness

- Config layer is strong: prod fails fast on default DB credentials, weak secret, debug, migration errors (`config.py:454-496`); non-DEBUG log level forced in prod. CORS/TrustedHost use allowlists; cookies path/secure configured.
- Verifications in C15: env completeness, secret scan on tree/tracked/diff, `/metrics` exposure review, worker fail-fast boot posture.
- `docker-compose.yml` pins Redis 7.4-alpine with 3 logical DBs (app cache / broker / result) — documented, no change needed.

---

## Workstream mapping (what P17 changes)

| WS | Change |
|---|---|
| C1 | UoW retry rollback; `render_now` recovery; +8 reliability tests |
| C2 | Rate-limit unit-mismatch fix, de-sticky fail-open, Redis error metrics, Redis-unavailable tests |
| C3 | Async `safe_dispatch`; video celery dispatch retry; make `dlq.record` persist to DB; DLQ default-on; persist 6 presentation tasks onto TaskWithDLQ; task table appendix |
| C4 | P16 video reliability tests (duplicate/concurrent/timeout/worker-failure/retry/partial) |
| C5 | Idempotency/duplicate tests for write ops (concurrent/same-twice/after-timeout) |
| C6 | Concurrent-write race tests (2 users, 2 completions, 2 renders, 2 submissions) |
| C7 | Bounded-label fixes, AI/DB/Redis/ratelimit metrics, duration labels, register p15, PII/log hygiene |
| C8 | `/health/ready` non-2xx semantics + DB/Redis availability tests |
| C9 | Process-local state classification (this appendix below) |
| C10 | PG EXPLAIN spot checks; additive indexes only if justified |
| C11 | `P17_LOAD_VERIFICATION.md` + controlled-concurrency stress module |
| C12 | Failure-injection matrix tests (DB/Redis/task/render/timeout/duplicate/concurrent/partial) |
| C13 | Security cross-audit regression tests |
| C14 | Real-JWT browser flows (Flow1–4) |
| C15 | Config/secret/env verification |
| C16-17 | Final regression + single head |
| C18 | `P17_IMPLEMENTATION_REPORT.md` + `feat(p17)` commit |

## C9 — process-local state classification (counts toward C9 audit)

| State | Location | Class | Disposition |
|---|---|---|---|
| BoundedCache (storage backend) | `app/workers/cache.py` | CACHE ONLY (unused) | stays local |
| Auth in-memory JTI fallback | `auth.py:35` | CACHE ONLY / degraded across instances | documented (R2) |
| OAuth state dict | `auth.py:40` | TEMPORARY / per-instance | documented |
| Rate-limit `_redis_available` flag | `rate_limit.py:110-111` | TEMPORARY (sticky bug) | fixed C2 |
| AI in-process response cache / rate limit | `app/ai/cache.py:1-5`, `app/ai/ratelimit.py:1-6` | CACHE ONLY (disabled by default) | stays local, documented |
| P16 inline render task registry (asyncio) | `video_render_executor.py:47-61` | JOB STATE (process-local) | correctness guarded by DB status transitions; document |
| Per-process metrics registry | `metrics.py:151` | JOB/CACHE mix | stays local (per-process counters), noted |
| Celery worker `task_routes` etc. | `celery_app.py` | CONFIG (static) | no change |
| `_revoked_refresh_jtis` | `auth.py:35` | USER STATE (revocation) | documented fail-open gap |
| SQLite test engines | conftest | TEST | no change |

No correctness-critical state needs to become distributed beyond what already lives in PostgreSQL.