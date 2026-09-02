# P4 Architecture Baseline

Single authoritative reference of the audited P3 architecture at `2da2856` for P4 work. Companion to `P3_P4_HANDOFF_AUDIT.md` (verification) and `P4_SCOPE_AND_FOUNDATION.md` (planning).

---

## 1. Runtime topology

```
 Browser (vanilla SPA in backend/frontend/)
    │  fetch() + localStorage tokens (authFetch refresh)
    ▼
 FastAPI (app.main:create_app)  --/api/v1 routers--  PostgreSQL (asyncpg)
    │                                               Redis (async: cache/rate/revocation)
    ├── /uploads  (StaticFiles, isolated store)
    ├── /frontend (StaticFiles, vanilla SPA)
    │
    └── Celery (broker=Redis, app=app.workers.celery_app)
            ├── content generation (AIContentService)
            ├── embeddings / indexing
            ├── export (was-dead; P4 WS2)
            └── (DLQ opt-in via CELERY_TASK_DLQ_ENABLED)
```

Mounts (verified in `app/main.py`): `/api/v1/*`, `/health`, `/ready`, `/metrics`(ondemand), `/uploads`, `/frontend`.

## 2. Backend layers

`src = backend/app`

| Layer | Location | Count |
|---|---|---|
| Routers (API v1) | `app/api/v1/` | 16 modules |
| Services | `app/services/` | 50+ files |
| Repositories | `app/repositories/` | ~19 files |
| Models (SQLAlchemy) | `app/models/` | 50 files |
| Schemas (pydantic) | `app/schemas/` | 39 files |
| AI orchestration | `app/ai/` + `app/services/*ai*` + providers | provider factory |
| Embeddings | `app/services/embedding*` + `app/workers/tasks.py` | full pipeline |
| Middleware | `app/middleware/` | 9 modules (order-sensitive) |
| Observability | `app/observability/` | metrics, logging |
| Workers | `app/workers/` | celery_app + tasks (15 tasks) |
| DB/Migrations | `app/database/migrations` | linear 0001→0028 |

## 3. State & storage

- **Persistent:** PostgreSQL (prod-only). Migrations linear; head `0028_ws10_idempotency_key_index`.
- **Cache:** Redis (async) — durable runtime state, rate limiting, token revocation.
- **Storage:** physical `backend/uploads/` + `backend/storage-data/` (gitignored); served through isolated proxy.
- **In-process (KNOWN UNBOUNDED, P4 WS4):** `_VIDEO_PROJECT_CACHE` (video_router), `_BLUEPRINT_CACHE` (animation_router), `_SESSIONS` (lesson_player), `_memories` (educational_memory), `_contexts` (learning_context), visual `_cache`. All per-process.

## 4. Concurrency & tasks

- Celery: `app/workers/celery_app.py` — `task_acks_late=True`, `reject_on_worker_lost=True`, `prefetch_multiplier=1`, JSON serializer, `task_ignore_result=True`, `time_limit=3600` / `soft=3000`. **docker-compose.yml lines 122/145 reference the non-existent `app.core.celery_app` — P4 WS1 must fix.**
- Dispatch: `safe_dispatch` bounded retry; commit-before-dispatch for generators; DLQ opt-in. `export_generation_task` awaited (fixed `8b8a6ee`) but never invoked (dead code).
- Async context: `_run_async` wrapper used for sync-in-async task bodies.
- In-process runtime state is not cross-replica safe (P4 WS4).

## 5. Security model

- **Auth:** JWT access + refresh; Argon2 hashing; Redis revocation (refresh flow); optional OAuth wiring.
- **Ownership:** user-scoped top-level unit; `owner_id` on presentation; quizzes/lessons/assistant anchored to presentation → uniform 404 via `assert_ownership` / `assert_quiz_ownership`. No ownerless leaks (P1 verified).
- **Upload protection (3×):** request-size middleware + `_read_upload_bounded` 413 + magic-byte validation.
- **Headers:** TrustedHost → SecurityHeaders (CSP, XFO, nosniff, referrer, permissions, HSTS-on-prod) + order-sensitive chain.
- **CSRF:** token utilities exist but **no CSRF middleware**; current auth = bearer over strict-origin CORS. Re-evaluate only if cookie sessions introduced (P4 non-goal unless pushed).
- **Config fail-fast:** `validate_environment` (config.py) rejects `CHANGE-ME` secrets, `eduvision:eduvision@...` DSN in release, missing s3 creds; `LIFESPAN_FAIL_FAST_ON_MIGRATION_ERROR=True` in prod.

## 6. AI / RAG

- Providers: google-generativeai (def), openai, local — via AIContentService + provider factory; prompts never logged; retry/rate-limit/cache/cost accounting.
- Embeddings: openai 1536-D, gemini 768-D/3072-D, local 384-D; batch/refresh/integrity/stats services; chunk_embedding + vector_index tables exist.
- **Retrieval: positional (NOT vector)** — WS3 moves to pgvector (or app-side cosine fallback).

## 7. Observability

- Structured logging (structlog) + request IDs. Per-process memory for runtime state.
- Metrics registry (`app/observability/metrics.py`): http request/duration, worker tasks, DLQ, plus **dead registrations** (task_dispatch_*, quiz_cache_*) — P4 WS1 instrument-or-remove.
- Health `/health` (liveness) + `/ready` (db-dependent).
- Multi-worker scrape gap: worker metrics not aggregateable cross-process without pull-side aggregation — P4 noted item.

## 8. Frontend (ACTIVE — do not confuse with the orphan)

- **Active:** `backend/frontend/` — vanilla JS multi-page SPA: `index.html`, `signin/signup.html`, `upload.html`, `processing.html`, `player.html` (+ `assets/app.js`, `assets/style.css`). No package.json/node_modules/build. Uses `fetch()` + localStorage tokens; `authFetch` refresh; rAF Motion Engine canvas rendering.
- **Orphaned:** `EduVision_AI_Frontend/eduvision_frontend/` — legacy static mockup, tracked but NOT served. Treat as sensitive; remove only with explicit approval.

## 9. Testing & tooling baseline (P4 gate)

| Tool | Command | Baseline |
|---|---|---|
| Fast tests | `pytest tests -m "not postgres"` | 968 pass / 12 deselect |
| Postgres tests | `pytest tests/postgres -m postgres` (live PG) | 12 pass |
| Lint | `ruff check app tests scripts --no-fix` | clean |
| Types | `mypy app` | 85 err / 25 files (check 273) |
| Secrets | git-ls-files regex scan | clean |
| Migration | `alembic current` (live PG) | single head 0028 |

- `tests/e2e/` is empty → P4 WS5 adds first browser smoke.
- CI: `.github/workflows/ci.yml` (lint / unit / integration / live-PG / secret-scan / docker); actual Actions runs unverified from clone (P3 checkpoint limitation).

## 10. Approval boundaries (MUST-NOT-MODIFY unless a P4 workstream formally changes them)

Ownership-404 contract, middleware ordering, fail-fast validation, per-session/upload caps, structlog request-ID correlation, metrics registry membership (additive), Alembic linear-head discipline, PostgreSQL-only production rule.

---

*End of P4 architecture baseline.*