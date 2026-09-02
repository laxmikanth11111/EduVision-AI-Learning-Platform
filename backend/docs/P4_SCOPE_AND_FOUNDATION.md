# P4 Scope and Foundation Plan

**Status:** Definition-of-complete for P4, derived from the audited P3 baseline (`2da2856`) and the related `P3_P4_HANDOFF_AUDIT.md`.

---

## 1. Mission

**EduVision's individual-student value loop, at production quality.** P1–P3 delivered a secure, runtime-hardened, production-ready foundation: a user-scoped learning platform (individual foundation), a single-owner presentation+quiz+lesson+assistant stack with embedding/RAG scaffolds, and production hardening (DLQ, metrics, fail-fast, CI). P4 takes the platform from "foundation complete" to **end-to-end product capability**: the two paths that turn foundation into value — (A) make the AI-assisted **presentation → quiz → lesson pipeline user-verifiable and exportable**, and (B) make **RAG/assistant retrieval actually vector-semantic** — while **closing the runtime correctness gaps** (celery module defect, export dead code, unbounded caches) that block deployment.

## 2. Baseline (from audited HEAD, `2da2856` — all verified)

- Fast suite **968 passed / 12 deselected / 0 failed** (SQLite).
- Postgres suite **12 passed** on live PG at `0028` head.
- **mypy 85 errors in 25 files (273 checked)** — P4 gate = **zero new errors**.
- Ruff clean; secret scan clean; single Alembic head `0028_ws10_idempotency_key_index`.
- PostgreSQL-only for prod; `LIFESPAN_FAIL_FAST_ON_MIGRATION_ERROR` + `validate_environment` fail-fast enforced.
- Runtime: 16 API routers, ownership-404 semantics, bounded per-session caps, JWT+refresh (no opaque cookie session), CSRF token utils but **no CSRF middleware** (current auth model = bearer+strict-origin CORS; CSRF re-eval only if P4 adds cookie sessions).
- Frontend: **vanilla JS multi-page SPA** served from `backend/frontend/` (no framework, no build step). The `EduVision_AI_Frontend/eduvision_frontend/` dir is an orphaned mockup — do NOT build on it.

## 3. What P1/P2/P3 already provide (do NOT re-do)

| Capability | Phase proven | P4 relationship |
|---|---|---|
| Ownership unit (individual) + uniform 404 | P1 | Keep; extend to export/vector as-needed |
| Auth (JWT access+refresh, Argon2, Redis revocation, OAuth) | P1 | Extend only if cookie sessions introduced |
| Storage isolation + triple upload protection | P1/P2 | Reuse for export/asset uploads |
| Data integrity (FK indexes, JSONB-portable enums, idempotency index) | P2/P3 | Additive migrations only |
| Bounded pagination, per-session caps, rate limits | P2/P3 | Reuse patterns for any new endpoint |
| Structured logging + request IDs; metrics registry | P3 | Additive registrations only |
| DLQ-forward, ack-late, commit-before-dispatch, bounded retries | P3 | Reuse for new tasks (export, vector index) |
| Fail-fast config validation | P3 | Reuse |
| Embeddings infrastructure (providers, batch, integrity, refresh, stats) | P3 | **Consumed** by vector RAG workstream |
| Quiz idempotency index + bulk-load optimization | P3 | Reuse |

## 4. Architecture baseline (must stay true)

- **Backend:** FastAPI async app in `app/`, PostgreSQL (asyncpg) only in prod, Redis (async) for cache/rate-limit/token-revocation, Celery (Redis broker) for async tasks. Alembic linear migrations 0001→0028.
- **Frontend:** `backend/frontend/` vanilla multi-page SPA served by FastAPI at `/frontend`; localStorage tokens + `authFetch`; Motion-Engine canvas animation in `player.html`.
- **Workers:** `app/workers/celery_app.py` is the real Celery app (config: acks_late, prefetch=1, ignore_result, time/soft limits).
- **AI:** `AIContentService` orchestrates providers (gemini/openai/local); prompt store; embedding pipeline; **retrieval is positional today**.

## 5. P4 goals vs non-goals

### Goals
1. **Fix deployment-blocking correctness gaps** (WS1) — celery module path, export dead code, dead metric registrations.
2. **Deliver the export capability** (WS2) — the was-dead `ExportService`/`export_generation_task` becomes real, user-invoked, observability-tracked.
3. **Deliver vector semantic retrieval** (WS3) — RAG moves from positional to embedding-similarity; keep single-table cognitive surface.
4. **Replace unbounded in-memory caches with bounded/durative ones** (WS4).
5. **Give the active vanilla frontend its first real end-to-end tests** (WS5 — e2e/live-browser-based despite no-build frontend).
6. **Leave the repo with the same clean, single-head, zero-new-error posture.**

### Non-goals (explicitly out of scope)
- Rewrite the frontend to a framework (Next.js/React/Vite build) — the active frontend stays vanilla no-build; only incremental JS may be added.
- Introduce SQLite in production, or a second database engine.
- Full auth overhaul (OAuth flows beyond current).
- Multi-tenant/shared-team collaboration, org/access-control layers.
- Public multi-tenant SaaS infra (payments/billing/caching-farm).
- A whole-new visual/2D engine model — the Motion Engine in `player.html` remains the player surface.
- Reopening P1/P2/P3 verified behaviors.

## 6. Workstreams (dependency-ordered)

### WS1 — Deployment-gate correctness fixes (foundation, smallest risk)
- **Objective:** make the documented compose/paths/dead-code/metrics gaps match reality or be removed.
- **Foundation:** verified audit (this doc); clean tree at `2da2856`.
- **Impact:** unblocks `docker compose up` worker/beat; removes assertions about dead code.
- **Tasks:**
  - Fix `docker-compose.yml` worker/beat to `celery -A app.workers.celery_app` (or document the sanctioned launch command); keep beat service.
  - Wire or remove `export_generation_task` dispatch (coordinate with WS2) and `record_retry`/`schedule_retry` hooks (wire in WS3/WS2 or strip).
  - Instrument or remove dead metrics (`task_dispatch_total`, `task_dispatch_retries_total`, `quiz_cache_*`).
- **Tests:** unit tests for any wiring change; `docker compose config` lint (when Docker available); CI live-PG migration check still must pass.
- **Dependencies:** none.
- **Exit criteria:** compose file references existent modules; no dead dispatch paths; metric registry = only produced metrics; tests green; mypy Δ=0.
- **Risk:** low.

### WS2 — Export capability (dead code → live user flow)
- **Objective:** `ExportService` + `export_generation_task` become an invocable, ownership-checked, progress-tracked user flow (e.g., PDF/archive export of a presentation/lesson).
- **Foundation:** existing `export_*` models/services/task (currently un-invoked), storage isolation, DLQ + ack-late pattern, bounded dispatch.
- **Impact:** first new user-visible P4 capability; moves a whole was-dead subsystem live.
- **Tasks:** add API route(s) with ownership-404 + per-user caps; feed the existing `create_export_job`; report pollable statuses; ensure export files go to isolated storage; add e2e coverage.
- **Tests:** unit (job lifecycle, caps, 404s) + integration (route→task→file) + pg (idempotency).
- **Dependencies:** WS1 (dispatch wiring).
- **Exit criteria:** end-to-end export with pollable progress; no unbounded memory growth; mypy Δ=0.
- **Risk:** medium — new API surface must preserve ownership model.

### WS3 — RAG vector semantic retrieval
- **Objective:** assistant/lesson retrieval uses embedding similarity (vector search) instead of positional-only chunk ranking; keep documents/lessons/presentations centers unchanged.
- **Foundation:** existing `vector_index`, `chunk_embedding`, embeddings pipeline (P3), provider factory.
- **Impact:** RAG quality (the core P4 differentiator for the assistant path).
- **Tasks:** choose approach (pgvector column+index vs application-side similarity; pgvector strongly preferred — Postgres-only rule holds); migrate index table(s) (0029+); build provider-agnostic search that falls back to positional when vectors absent; wire `record_retry`/`schedule_retry` if they gate index health; add metrics for search latency/relevance.
- **Tests:** unit (retrieval ordering, fallback), integration (index→search), postgres (vector ops on live PG), any e2e assistant query.
- **Dependencies:** WS1 (cleanup); embeddings infra is inherited-ready.
- **Exit criteria:** similarity-based top-k retrieval replaces positional in the assistant path; fallback preserves behavior when vectors missing; mypy Δ≦0; no new prod DB engine.
- **Risk:** medium-high — pgvector dependency and index weight; keep fallback path.

> **WS3 delivered:** implemented as **application-side cosine similarity** over the persisted `ChunkEmbedding.vector` JSONB values (single-engine; **no pgvector**; **no new migration**; head stays `0028`). Positional fallback preserved; ownership stays an **API/service-layer responsibility**; retrieval is scoped to the authorized lesson/presentation content-unit set; soft-deleted chunks are excluded.

### WS4 — Runtime memory bounds (replace unbounded dicts)
- **Objective:** `_VIDEO_PROJECT_CACHE`, `_BLUEPRINT_CACHE`, `_SESSIONS`, `_memories`, `_contexts`, visual `_cache` move from per-process-unbounded → bounded with TTL/eviction or durable (Redis/DB) backing.
- **Foundation:** existing bounded per-session caps (P2/P3 pattern).
- **Impact:** production memory predictability; multi-worker safety.
- **Tasks:** introduce a small bounded cache utility (or extend existing cap pattern) and apply across the listed host names; where the state is session-scoped, scope to user+presentation with TTL.
- **Tests:** unit (eviction/TTL), integration (multi-access consistency).
- **Dependencies:** none (orthogonal).
- **Exit criteria:** no unbounded dicts remain; behavior tests still pass; mypy Δ=0.
- **Risk:** low-medium.

### WS5 — Frontend e2e smoke (no-build SPA)
- **Objective:** first real end-to-end browser tests on the ACTIVE vanilla SPA (`backend/frontend/`); establish a repeatable live-sign-in → create → play smoke.
- **Foundation:** `tests/e2e/` is currently empty; use a browser-based runner (Playwright/pytest-playwright) against the FastAPI app + live PG seed.
- **Impact:** confidence the delivered SPA actually works; blueprints for regression.
- **Tasks:** minimal harness; one smoke scenario; CI job (browser) optional.
- **Dependencies:** none (frontend unchanged).
- **Exit criteria:** one passing e2e smoke; documented run command; mypy/ruff unaffected.
- **Risk:** low-medium.

### WS6 — Verification & release gate (optional consolidation)
- **Purpose:** run the full P4 gate: fast suite, PG suite, e2e, ruff, mypy Δ=0, `alembic current` = 0029+ single head, secret scan, git diff --check, clean tree; produce a P4 completion report (mirroring `P3_PRODUCTION_HARDENING_FOUNDATION_REPORT.md`).
- **Foundation:** `P3_P4_HANDOFF_AUDIT.md` process.

## 7. Dependency graph

```
WS1 (cleanup) ──► WS2 (export)            WS4 (memory)  [independent]
                └──► WS3 (vector RAG)
WS5 (e2e)                               [can start anytime]
WS6 (gate) ──last
```

- WS1 is the true prerequisite for WS2/WS3 (dispatch wiring + cleanup).
- WS4 is orthogonal and can run in parallel.
- WS5 is independent of WS2/WS3 (frontend smoke needs only existing endpoints).
- WS6 aggregates everything.

## 8. Plan by layer

### Database
- Keep `0028` as-is; add **linear** `0029+` only for vector/export needs. Single head must always hold.
- pgvector (if chosen) is a Postgres extension — **constraint: PostgreSQL-only holds**; no new DB engine.

### Backend
- New: export route(s) (WS2), vector-search repository/service (WS3), bounded-cache utility (WS4).
- No changes to the ownership-404 semantics or middleware ordering.

### Frontend
- Incremental vanilla JS only; new export UI = plain fetch + existing patterns (localStorage/authFetch). No framework.

### AI
- Providers unchanged; WS3 adds retrieval layer over existing embeddings.

### Worker
- Celery module path fixed (WS1); export task dispatched (WS2); any new index task (WS3) follows ack-late/DLQ pattern.

### Security
- New routes keep ownership-404 + per-user caps; export files isolated; no secret exposure; CSRF re-eval only if cookie sessions introduced (explicitly out of P4 unless pushed in).

### Observability
- Instrument the new search/export metrics (additive to registry); remove/merge dead registrations (WS1).

## 9. Test strategy

- Unit (SQLite-fast), integration (SQLite+redis/mocked celery), postgres (live PG only for vector/FK/head verification), e2e (browser, WS5).
- Gate commands (mirror P3):
  - `pytest tests -m "not postgres"` → 968+new passing, 12 deselected.
  - `pytest tests/postgres -m postgres` (live PG) → passes.
  - `ruff check app tests scripts --no-fix` → clean.
  - `mypy app` → Δ=0 (≤85 errors allowed if baseline-only; **no new errors**).
  - `git ls-files` secret scan → clean.
  - `alembic current` = single head.

## 10. Regression gates

- No new mypy errors.
- Existing 968+12 tests stay green at every merge point.
- Tree clean between workstream merges; single documentation commit per deliverable allowed.
- No application code in a "docs-only" commit.

## 11. P4 exit criteria

1. WS1–WS5 all closed with the above per-WS exit criteria.
2. Single Alembic head maintained; `alembic current` known.
3. `968+new` fast tests, `12+X` postgres tests, and e2e smoke all pass.
4. No version-boundary breakage: P1/P2/P3 verified behaviors remain covered.
5. Final handoff report (`P4_COMPLETION_REPORT.md` analog) produced, mirroring the P3 foundation-report format.

## 12. Risks / open items

- **pgvector availability** on the target host (P3 uses stock PG image; must confirm extension availability before committing to vector route). Fallback = app-side cosine over stored embeddings (still single-engine).
- **Export file formats** scope creep — constrain to a smallest valuable set.
- **Celery beat / scheduled indexing** activation decisions — keep explicit.
- **Docker/CI unverified** in this checkpoint — re-verify WS1 launch flow when Docker is available.
- `EduVision_AI_Frontend/` orphan is legacy; remove only with explicit approval (tracked in git — treat as sensitive).

## 13. Definition of "complete"

P4 is complete when: deployment-blocking gaps are closed (WS1), export is a live tracked user flow (WS2), retrieval is vector-semantic with fallback (WS3), the process has no unbounded caches (WS4), the active vanilla frontend has at least one passing e2e smoke (WS5), and the whole stack passes the full gate with a clean tree and Δ=0 mypy (WS6). No P4 work is merged into the P3 baseline commit; everything lands on top of `2da2856`.