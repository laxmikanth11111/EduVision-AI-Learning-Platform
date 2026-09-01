# EduVision AI — Phase 0 Deep Architecture Audit

**Date:** 2026-09-01
**Auditor role:** Principal Architect / Staff Backend / Security / AI / DB / Frontend / QA / DevOps
**Basis:** Read-only evidence audit of the live repository (no source modified during audit).
**Branch audited:** `feature/individual-user-foundation` (contains completed Phase 1 hardening; base = `main @ 998ebe1`).

> Every claim below is sourced to a file path or a verified command. Where evidence was insufficient the status is stated **UNKNOWN — NOT VERIFIED** explicitly. Nothing is asserted from filenames alone.

---

## PART A — Executive Summary

EduVision AI is a **FastAPI (Python 3.13, async) + PostgreSQL + Redis + Celery** backend serving a **vanilla-JavaScript multi-page SPA** (`backend/frontend/`) that it hosts itself over StaticFiles. It is an *individual-first*, AI-native visual learning and presentation platform: a single `User` owns presentations → lessons → topics → quizzes, the AI understands documents, and a player renders concept slides with canvas/animation/video/simulation visualizations.

**What is genuinely real (verified):**
- Complete document upload → extraction → lesson generation → player pipeline.
- A deep AI orchestration layer (`AIContentService` + provider abstraction for Gemini/OpenAI/LOCAL, retry/rate-limit/cache/cost).
- A **visual intelligence engine** (classify → objectives → components → relationships → visualization decision → graph persistence) with a 2D SVG knowledge-graph canvas.
- An **animation planner + browser "Motion Engine"** renderer, a **rule-based simulation runtime** (1 definition), a **real H.264 MP4 + TTS narration** video pipeline, and a **heuristic learning-intelligence** layer (mastery/effectiveness/recommendation).
- Strong foundations: Argon2 password hashing, JWT access+refresh with Redis-backed revocation (Phase 1), ownership checks on the dominant resources, bounded uploads, structlog + request-IDs + Prometheus metrics + health/liveness/readiness.

**What is NOT yet real (verified gaps):**
- RAG embedding vectors are generated and stored but **retrieval does not use them** (positional first-N fetch only — no vector/similarity search).
- **No ML/DL** anywhere (all "intelligence" is LLM-API + deterministic heuristics).
- **No CI/CD** at all (no workflow files; all quality gates are manual).
- Lesson/simulation/animation/video quiz content is linear or in-memory; no true 2D slide-element authoring model.
- **A verified quiz-ownership authorization gap (IDOR):** `assert_quiz_ownership` ignores the user and never verifies ownership (see Part M / Risk register).

**Phase note:** Phase 1 (previously completed) hardened security/auth/DB/AI-routing; this audit reflects that improved baseline and is the evidence base for Phases 2+.

---

## PART B — Repository Structure

```
<repo>/
  docker-compose.yml          # 5 services: postgres, redis, minio, backend, celery-worker, celery-beat
  .env.example                # placeholders only (verified clean)
  .gitignore                  # thorough; .env, *.db, dvds, caches, MEMORY.md ignored
  MEMORY.md                   # gitignored session memory (local only)
  EduVision_Final_Report.md   # prior project report (accuracy cross-checked)
  EduVision_AI_Frontend/      # ORPHANED static design mockup (NOT served, no API; see Part C)
  backend/
    Dockerfile                # multi-stage: builder/development/build/production
    pyproject.toml            # python>=3.13, ruff, mypy strict, pytest config
    requirements.txt          # prod deps
    requirements-dev.txt      # dev deps (ruff, mypy, pytest-asyncio, testcontainers, ...)
    alembic.ini
    app/
      main.py                 # app assembly, middleware chain, lifespan runs `alembic upgrade head`
      core/                   # config, dependencies, security, logging, exceptions
      middleware/             # CORS, GZip, Logging, RateLimit, RequestID, RequestSizeLimit, SecurityHeaders, Timing, Exception
      api/v1/                 # 16 routers (auth, presentations, player, quiz, visual, assistant, ...)
      ai/                     # orchestration + providers + embeddings (17 modules)
      services/               # 60 service modules
      models/                 # 61 model files
      repositories/           # 20 repository modules
      schemas/                # 40 schema modules
      database/               # session, unit_of_work, repository, base, migrations/versions (0001..0025)
      workers/                # Celery app, tasks, rag_tasks, idempotency, cache, redis_client
      observability/          # MetricsRegistry
      utils/                  # file_helpers, storage (local/S3), document_parsers, export
      frontend/               # ACTIVE frontend: index/signin/signup/upload/processing/player + assets (vanilla JS)
      docs/                   # phase reports incl. this audit
      scripts/                # E2E/load/diagnostic harnesses (_mv_*.js/.ps1, seed, llm probes)
      tests/                  # unit/ (62 files) + integration/ (11 files, testcontainers)
      uploads/ , storage-data/  # local storage (gitignored)
```

**Generated/local (gitignored):** `backend/.env` (real local secrets, untracked), `*.db`, `celerybeat-schedule`, `dump.rdb`, caches.

---

## PART C — Technology Stack (verified)

**Backend:** Python `>=3.13`, FastAPI `>=0.115`, uvicorn, Pydantic `>=2.9` + pydantic-settings, structlog, tenacity, orjson, python-jose, argon2-cffi + passlib[bcrypt], httpx. Async-only SQLAlchemy `[asyncio]>=2.0.36` + `asyncpg` (`AsyncAdaptedQueuePool`; `NullPool` under tests). Celery `>=5.4` + redis[hiredis]. boto3 (S3), opencv-python-headless, pypdf, python-docx/pptx, gtts/edge-tts, imageio-ffmpeg. Dev: ruff, mypy, pytest, pytest-asyncio, factory-boy, testcontainers[postgres], pre-commit (declared but **no `.pre-commit-config.yaml`**).

**Frontend — ACTIVE (`backend/frontend/`):** **Vanilla JS multi-page SPA, NO build step, NO framework, NO node_modules, NO package.json.** Served by FastAPI `StaticFiles(...)` at `/frontend/*`. Plain `fetch()` (no axios/WS/SSE); `localStorage` tokens; inline page scripts; polling (setTimeout) for progress, no real-time transport.

**Frontend — ORPHANED (`EduVision_AI_Frontend/eduvision_frontend/`):** static design mockup with Bootstrap via CDN; **not served, not referenced**; its README states forms are fake and progress is a timed simulation. Confirmed not mounted in `main.py`.

**Database:** PostgreSQL (16-alpine in compose), but SQLite for unit tests (JSONB compiled to JSON). Alembic head `0025` matches the in-app auto-upgrade.

**Infra:** Redis (rate-limit + cache + queues + auth revocation + OAuth state), MinIO/S3 (optional storage adapter), Docker with compose.

---

## PART D — Feature Truth Table

| Capability | Status | Evidence |
|---|---|---|
| Authentication (register/login/JWT/OAuth) | **IMPLEMENTED** | `app/api/v1/auth.py`; Argon2; JWT access+refresh; Google OAuth w/ state; Redis-backed revoke (Phase 1) |
| Authorization / ownership | **IMPLEMENTED with GAP** | presentation/canvas/player ownership strict; **quiz ownership broken (IDOR)** — `quiz_attempt_service.py:49` |
| Presentation lifecycle (create/rename/dup/delete/restore/versions/autosave) | **IMPLEMENTED** | `presentation_service.py` + version service/model |
| Slide model (2D spatial) | **PARTIAL** | content is linear blocks (`content_block.py`: type/position/content/meta); **no x/y/w/h/rotation/z** in base model |
| Import (PDF/DOCX/PPTX/TXT upload) | **IMPLEMENTED** | document parsers; size+ext validated; magic bytes NOT validated |
| Export (PPTX/PDF etc.) | **IMPLEMENTED** | `export_service.py` + exporters (note: local presigned URL leaks `file://` path) |
| AI generation / orchestration | **IMPLEMENTED** | `AIContentService` + provider factory; retry/rate-limit/cache/cost; all services now route through it (Phase 1) |
| RAG indexing + embeddings generation | **IMPLEMENTED** | `rag_indexing_service.py`, `embedding_service.py`, providers (openai/gemini/local), Celery tasks, persisted chunks+vectors |
| RAG retrieval (vector search) | **MISSING** | `learning_assistant_service._retrieve_relevant_chunks` fetches by `position`; no similarity/pgvector/cosine in repo; confirmed by project report |
| AI tutor | **PARTIAL** | `learning_assistant_service.py` assembles context, falls back to LLM then contextual answer; retrieval not vector-based |
| Visual intelligence | **IMPLEMENTED** | `visual_intelligence_service.py` (11-step pipeline) + classifier/decision/relationship/component/objective services |
| Visual rendering | **IMPLEMENTED** | 2D SVG knowledge-graph canvas persisted (`VisualCanvas`/nodes/edges) + client-side render |
| Animation | **IMPLEMENTED** | planner/classifier/validation + in-browser Motion Engine (rAF loop); blueprint from backend |
| Simulation | **PARTIAL** | generic in-memory runtime, **but only 1 pre-registered definition** (`sim_cpu_fetch_execute`); no persistence |
| Video | **IMPLEMENTED** | real H.264 MP4 (OpenCV+ffmpeg), TTS narration, storyboard/subtitles/validation; in-memory project cache |
| Audio / voice / TTS | **IMPLEMENTED** | `tts_service.py` EdgeTTS/GTTS with cache |
| Knowledge graph | **IMPLEMENTED** (space/limited) | visual knowledge-graph canvas; heuristic mastery memory; no full learner graph |
| Adaptive assessment | **IMPLEMENTED (heuristic)** | `adaptive_assessment_engine.py` difficulty ladder, exact-match eval, no ML |
| Recommendation / personalization | **IMPLEMENTED (heuristic)** | `recommendation_engine.py` deterministic thresholds; no AI |
| ML / DL | **MISSING** | no torch/tf/sklearn/xgboost/lightgbm/transformers; only `numpy`; no model artifacts |
| Analytics | **PARTIAL** | learning events + effectiveness assessment + groups; limited product analytics surface |
| Voice / narration | **IMPLEMENTED** (video narration) | TTS in video pipeline; no standalone voice assistant |
| CI/CD | **MISSING** | no workflows/CI files anywhere |
| Observability | **PARTIAL→GOOD** | structlog, request IDs, Prometheus `/metrics`, health liveness/readiness; **no tracing, no error-tracking service, no alerting, per-process metrics** |
| Security | **PARTIAL** | see Part M; strong auth/ownership on main resources, but quiz IDOR, unvalidated magic bytes, default APP_SECRET_KEY risk |
| Scalability | **PARTIAL** | stateless API, Redis locking/rate-limit, worker scale, but in-memory runtime states (sim/animation/video/lesson) + per-process metrics; no load test certifying a number |

---

## PART E — Individual-First Architecture

**Verdict: the active architecture is individual-first; no teacher/student/classroom hierarchy remains in active code.**

- `UserRole` (`shared/constants/__init__.py`) is a **single value `USER="user"`** with an explicit docstring: *"There is no student/teacher split and no multi-role hierarchy."* (Phase 1 change.)
- `User` model has **no role column**; role is a fixed JWT claim `role="user"` (`auth.py`, `security.py` requires `role` and token carries it). Verified `security.py:94-110` requires `sub, role, type, jti`.
- Migration `0022_terminology_migration.py` renamed `student_answers`→`user_answers`, `student_analytics`→`learning_analytics`, `teacher_analytics`→`creator_analytics`.
- Remaining `student`/`teacher`/`classroom`/`enrollment` occurrences exist only in **migration docstrings/constants** (`0009`,`0011`,`0022`,`0024`) and one test string — not runtime logic. `student_answer.py` is a **backward-compatible alias** of `UserAnswer`.
- Owner columns are `owner_id`/`user_id` (nullable on several tables — see Part L).
- Single-user isolation: `Presentation.owner_id`, `VisualCanvas.user_id`, player walks presentation ownership, attempt reads are user-scoped. **Exception:** quiz ownership (Part M).

---

## PART F — Presentation / PowerPoint Gap Matrix

The base content is **linear, not 2D-authoring**. True spatial layout exists only in the separate visual-knowledge-graph canvas.

| Capability | Status | Evidence |
|---|---|---|
| Text boxes | PARTIAL (linear blocks) | `content_block.py` no geometry |
| Images | PARTIAL (inline) | blocks; not freely placed |
| Shapes | PARTIAL (visual graph only) | canvas nodes |
| Tables | **MISSING** | no table element |
| Charts | **MISSING** | no chart engine |
| Video | IMPLEMENTED (player) | video visual in player |
| Audio | MISSING (editor) | TTS in video only |
| Groups / Layers | **MISSING** | no layer/z-index model |
| Alignment / Snapping / Rotation / Resize | **MISSING** | no geometry |
| Copy/paste | **MISSING** | no clipboard editing |
| Undo / Redo | **MISSING** | no editor undo stack |
| Autosave | IMPLEMENTED | `autosave` in presentation_service |
| Versioning | IMPLEMENTED | `presentation_version` model/service |
| Templates / Themes | **MISSING** | none found |
| Speaker notes | **MISSING** | none found |
| Presenter mode | IMPLEMENTED | player present mode |
| Timer / Keyboard nav | IMPLEMENTED | keyboard nav in player test |
| Pointer / Pen / Highlighter | **MISSING** | none found |
| PPTX import | IMPLEMENTED | python-pptx parser |
| PPTX export | IMPLEMENTED | exporter |
| PDF export | IMPLEMENTED | exporter |

**Conclusion:** EduVision today is a **viewer/generator of linear lessons with rich per-topic visuals**, not yet a PowerPoint-class 2D editor. Phase 3 must introduce the 2D slide element model.

---

## PART G — AI Architecture (verified call flow)

```
API route (e.g. /presentations/{id}/lessons)
  ↓ service (lesson_generation_service, quiz_generation_service, ...)
  ↓ orchestrator AIContentService.generate (app/ai/service.py)
  ↓ provider factory create_ai_provider (app/ai/factory.py)
  ↓ AIProviderType GEMINI | OPENAI | LOCAL (defaults gemini / gemini-1.5-flash)
  ↓ structured response parsed + schema-validated (LessonPayload, etc.)
  ↓ persisted (lesson/topic/quiz/visual records)
```
Resilience: `AsyncRateLimiter` (per-process token bucket), `RetryPolicy` (backoff+jitter, retries `AIError`), `AIResponseCache` (bounded TTL in-process), token/cost estimator, safe metadata logging (prompts never logged).

**Embeddings** are a separate provider (`create_embedding_provider`): openai `text-embedding-3-small`, gemini `text-embedding-004`, local deterministic mock (384-d). Versioned per-chunk publication + content-hash/checksum integrity.

**AI callers (all through orchestrator, Phase 1):** component_discovery, visual_classifier, visualization_decision, learning_objective, relationship_engine, quiz_generation, learning_assistant, lesson_generation, topic_outline; plus `visual_intelligence_service` orchestrating steps 1–11. Workers reach AI indirectly via services (no direct provider import in workers).

**Findings:** No direct-provider bypasses remain after Phase 1 routing. Prompt/cost tracking is per-request; no per-provider latency *metric* (wall-clock only). Providers default to Gemini which is out of quota locally (heuristic fallbacks).

---

## PART H — Visual Intelligence (current state)

- **Understanding:** `visual_classifier_service` (22-category hybrid: rule-based keyword score + LLM fallback); `relationship_engine_service` (LLM + fallback rules); `component_discovery_service` (LLM + heuristic); `learning_objective_service` (LLM + heuristic).
- **Specification:** `visualization_decision_service` maps category → 10 `VisualizationType`s (FLOWCHART, BLOCK_DIAGRAM, TIMELINE, ALGORITHM_STEPS, NETWORK_GRAPH, ...). `visual_intelligence_service` orchestrates classify→objectives→components→relationships→decision→graph layout→sim/quiz focus.
- **Rendering:** persisted `VisualCanvas` + nodes/edges; **client renders SVG from returned nodes/edges** (`player.html`). 2D layout within the graph only.
- **Persistence:** `visual_persistence_service` (canvas/node/edge/layout/relationship/objective/quiz-blueprint repos, Redis cache, JSON validation, versioning). Ownership strict on canvas (Phase 1 fixed null-owner).
- **Assessment visuals:** `visual_question_generator.py` (hotspot/sequencing/matching).

---

## PART I — Animation

**Status: IMPLEMENTED (backend planner + client runtime).**
- Backend: `animation_planner_service` (builds `AnimationBlueprint`: scenes, timeline events like `focus_camera`/`reveal_component`/`highlight_node`, narration sync), `animation_classification_service` (rule-based), `animation_validation_service` (scene ordering, node coverage, coverage_score).
- API: `POST /animations/plan` (blueprint cached in-memory), `POST /animations/runtime/sync` (`_RUNTIME_STATES` in-memory, logs learning events).
- Frontend Motion Engine v2 in `player.html` (rAF loop, SVG createElementNS, `generateAnimation` → plan → play/pause/seek/speed).
- **Both** generic object animation and concept-specific visualization animation exist (backend is concept-driven; player drives timeline events).
- **Caveat:** runtime state in-memory only (lost on restart, not shared across replicas).

---

## PART J — Simulation

**Status: PARTIAL.**
- `simulation_registry_service`: **one** pre-registered definition (`sim_cpu_fetch_execute`, params clock_frequency_mhz/register_a_value/alu_mode).
- `simulation_engine_service`: generic stateful runtime — `_sessions`, `_definitions`, `_session_owners` (all **in-memory**); start/set-params/step/playback/reset; event logs, checkpoints, owner validation.
- Router: `/simulations/definitions|start|get|step|update-parameters|playback|reset`. Frontend wired.
- **Caveat:** single definition; no persistence; not a real DSA/algorithm curriculum.

---

## PART K — ML / DL

**Status: MISSING (no ML/DL).**
- No torch/tensorflow/sklearn/xgboost/lightgbm/transformers in `requirements.txt`/`requirements-dev.txt`. Only `import numpy` (video renderer).
- No committed model artifacts (`.pth/.pkl` are `.venv` noise).
- All intelligence = LLM API (OpenAI/Gemini/local) + deterministic heuristics.

**ML/DL readiness matrix**

| Element | Status |
|---|---|
| Data available | Learning events, attempts, effectiveness, mastery, chunks, embeddings (rich, individual-first) |
| Candidate problems | difficulty prediction, visual recommendation, next-step recommendation, mastery modeling |
| Current implementation | None (heuristics + LLM) |
| Missing infrastructure | Feature store, experiment framework, eval sets, model registry, GPU/no-GPU serving |
| Evaluation requirements | Bootstrap baselines vs current heuristics first; only adopt where measurable lift |
| Privacy | Individual-first → learner data must be anonymizable; embeddings of user content are PII-adjacent |

Recommendation: **do not** build ML until an evaluation harness against the heuristic baselines exists; heuristic accuracy should be the floor.

---

## PART L — Database

- **61 model files** via mixins (`UUIDMixin`, `TimestampMixin`, `AuditMixin`, `SoftDeleteMixin`, `SoftDeletableBaseModel`). Tables include users, presentations(+version/tag/analytics/audit_log/folder), content_unit/block, generated_lesson(+version)/block, topic_outline, quiz(+version/content/attempts/answers/answer_key/explanations/score), visual_knowledge_graph(canvas/node), RAG (chunk/section/embedding/vector_index(+version)/embedding_job/batch/metadata/statistics/concept), assistants, learning (session/event/activity/effectiveness/educational_memory/user_feedback/analytics/ai_usage), export (job/file/template).
- **Ownership:** `Presentation.owner_id`, `PresentationFolder.owner_id`, `VisualCanvas.user_id`, `GeneratedLesson.user_id`, `ContentUnit/ContentBlock`, `Quiz.*` — **nullable** (SET NULL on delete); production enforces ownership at the service layer (404 on null/mismatch via `assert_ownership`).
- **Indexes vs FKs:** Phase 1 added the 4 missing FK indexes via migration `0025_fk_indexes` (question_attempts.question_id, quiz_attempts.quiz_version_id, quizzes.lesson_version_id, user_answers.question_attempt_id); other FKs covered by unique constraints or composite indexes.
- **Migrations:** `app/database/migrations/versions/0001..0025`; head `0025` = `0025_fk_indexes`, `down_revision 0024`; linear, no branches, matches the in-app `alembic upgrade head` at `main.py` lifespan. Note: legacy `role`/`student`/`teacher` columns exist in `0001` but are superseded/dropped by `0020`+`0022`; historical chain documented as fragile on real Postgres (0021 in particular) — not repaired in-phase.
- **Soft delete:** `SoftDeleteMixin` present; base `delete(hard=False)` now hard-deletes non-soft-deletable models instead of silent no-op (Phase 1).

---

## PART M — Security

**Auth — good:** Argon2 (argon2id) hashing; JWT HS256 access+refresh with `aud`/`iss`/`type`/claims enforced; revocation Redis-backed with in-memory fallback (Phase 1); Google OAuth with state verification, race-free commit; cookies + Bearer.

**IDOR — one real gap (verified):**
- `quiz_attempt_service.assert_quiz_ownership(quiz_public_id, user_id)` (line 49) claims to verify ownership but **only fetches by public_id and returns it, ignoring `user_id` entirely**. Used by `GET /quizzes/{id}`, `POST /quizzes/{id}/attempts`, `GET /quizzes/{id}/attempts`. → Any authenticated user with a quiz `public_id` can read quiz metadata and create/list attempts on a quiz owned by **anyone**. Attempt *content* stays user-scoped (`get_attempt`/`submit_answer` re-check `attempt.user_id`), so the exposure is metadata + unauthorized attempt creation, not reading another user's answers. **Severity: HIGH (P1).** Not fixed in Phase 1.
- Presentation/canvas/player ownership verified strict (Phase 1 added null-owner canvas fix).

**Uploads — strong, one gap:**
- Size: bounded twice (request-size middleware `Content-Length` + `_read_upload_bounded` hard cap on actual body, 413) (Phase 1).
- Extension allowlist (`.pdf/.docx/.pptx/.txt` sources; thumbnails restricted), `safe_filename` sanitization, path-traversal blocked via `is_relative_to`, storage isolation.
- **Gap:** `validate_magic_bytes` (`utils/file_helpers.py:32`) is **defined but never called** — content is not validated (only extension + size + client `content_type`). A same-extension file with wrong bytes passes. Severity: MEDIUM.
- **SSRF:** no user-controlled URL-fetch endpoint (only outbound = Google OAuth + AI providers). **No SSRF surface.**
- `/uploads` static mount public at a dir separate from local storage — verify intended.

**Config:** `backend/.env` holds **live** Google AI key + OAuth client id/secret (this file is **untracked + gitignored** — verified: `git ls-files` refuses it and `git grep GOCSPX` returns nothing across all history → **no secrets in git**). `APP_SECRET_KEY`/`CSRF_SECRET` are not set locally → fall back to `CHANGE-ME-*` defaults in compose (insecure for any non-local deploys). **Recommend: rotate those 3 live creds + set real APP_SECRET_KEY/CSRF_SECRET.**

**XSS/CSP:** security headers middleware sets CSP, X-Frame-Options DENY, nosniff, HSTS (prod). Frontend uses inline scripts — rely on CSP config.

---

## PART N — Testing (verified)

- **Unit: 753 passing** (739 baseline + 14 Phase-1 integrity), 0 failures this baseline, run with SQLite. 62 files covering AI providers/orchestration/resilience, RAG chunking/embeddings/indexing/migrations, presentations, lessons, quizzes, visual, animation, video, simulation, export, player, security, rate-limit, db-retry, health, metrics, idempotency, analytics, S3, recommendation, document parsing, component discovery, phase integrity.
- **Integration: 11 files** (testcontainers Postgres with fallback to SQLite). Not run here (no Docker) — **UNKNOWN** for Postgres-specific behavior in this run; covered structurally.
- **E2E harnesses:** `_mv_player_test.js` (jsdom), `_mv_browser_e2e.js` (puppeteer+Chrome), `_mv_wire_check.ps1`, `_mv_mlunit3_test.ps1`, load probes. Require a live backend + real JWT; previously all reported passing.
- **Known pre-existing:** rate-limit tests expected no whitelist (env side effect). Google OAuth callback, SMTP, real Celery execution, CSRF token rotation, cookie handling lack dedicated unit tests.

---

## PART O — Type/Lint (verified)

- **Ruff:** clean on `app/`, `tests/`, `scripts/` (Phase 1 run). Config: line-length 100, many rule sets selected.
- **mypy:** configured **strict** but **NOT a clean gate** — 66 pre-existing errors across untouched files (workers/tasks, rag_tasks, presentation_service, rag_indexing_service, topic_outline_service, untouched line ranges in partially edited services). **Phase 1 introduced zero new errors.** Tests + migrations excluded from mypy.

---

## PART P — Build / Deployment (verified)

- `backend/Dockerfile`: multi-stage (builder/development/build/production); production stage runs **Gunicorn with 4 uvicorn workers as non-root**, healthcheck `curl /api/v1/health`; ffmpeg etc. installed.
- `docker-compose.yml`: postgres/redis/minio/backend(development target)/celery-worker/celery-beat, health checks + `service_healthy` dependency ordering, named volumes, env from `.env` with defaults.
- Migrations auto-run at startup in `main.py` lifespan (`alembic upgrade head`) — **no migration sidecar; multi-replica startup race risk**.
- Compose uses the **development** Docker target (no production compose variant).
- No frontend build (static files). Deploy **not actually executed/verified in this environment** (no Docker) → runtime container behavior **UNKNOWN — NOT VERIFIED**; config is internally consistent.

---

## PART Q — Performance

Segregated:
- **Observed:** no N+1 audit performed; visual/canvas queries cached via Redis; bounded uploads prevent memory blowups; requests are async-first; rate limiter + response cache bound AI traffic.
- **Needs profiling (not confirmed by load test):** AI heavy synchronous calls in request path (lesson generation is Celery-dispatched; some services sync), RAG positional retrieval, CSV export, per-request AI latency lacks a histogram.
- **No load test certifies a throughput/scale number.** Load-probe scripts exist but are smoke-level.

---

## PART R — Scalability

- **Stateless API:** yes (JWT stateless, Redis centralized) → horizontal API scaling feasible.
- **Workers scale:** yes (Celery + queues + idempotency + DLQ).
- **Blockers to scale:** (1) in-memory runtime state for simulation/animation/video-collab/lesson (not shared across replicas → must become Redis/DB-backed for HA); (2) per-process Prometheus metrics (each replica must be scraped); (3) positional RAG retrieval (no vector index); (4) startup-run migrations create replica race; (5) no object-storage default (local disk) in prod.
- **No scale number is claimed** (no measurement).

---

## PART S — Technical Debt / Risk Register (P0–P3)

| # | Sev | Risk / Evidence | Impact | Probability | Solution |
|---|---|---|---|---|---|
| S1 | **P1/HIGH** | Quiz IDOR — `assert_quiz_ownership` ignores user (`quiz_attempt_service.py:49`); quiz read/attempt-create not owner-scoped | Cross-user quiz metadata exposure + unauthorized attempts | High | Enforce ownership (walk quiz→presentation→owner) like presentation; add regression tests |
| M1 | **MED** | `validate_magic_bytes` never called; uploads trust extension+declared content_type | Malformed/mismatched files persisted; defense-in-depth gap | Medium | Invoke magic-byte check in `set_source`/`set_thumbnail` |
| M2 | **MED** | In-memory runtime states (sim/animation/video/lesson) lost on restart, not shared | HA/scale limitation; UX surprise | Medium | Persist/back with Redis for multi-replica |
| M3 | **MED** | `APP_SECRET_KEY`/`CSRF_SECRET` unset → CHANGE-ME defaults (compose) | Weak signing/CSRF in non-local deploys | Medium | Require env at startup (fail-fast) |
| M4 | **MED** | `/uploads` static mount public, separate dir from storage path | Potential unintended public files | Low-Med | Verify intent; bound & audit content |
| M5 | **MED** | Local presigned URL returns `file://` absolute path (`storage/local.py:87`) | FS path leak in exports | Medium | Return server-relative/download URL |
| P2 | **MED** | **No CI/CD** (no workflows) | No automated gates; regression risk | Certain | Add GitHub Actions: lint, mypy, unit, integration, build |
| P2 | **MED** | No tracing, no error-tracking service, no alerting; per-process metrics | Blind spots in prod | Medium | Add OTEL (config exists), error tracker, scrape all replicas |
| P2 | **MED** | RAG vectors unused in retrieval (positional only) | Tutor answers ungrounded to relevant chunks | High (feature) | Implement similarity/vector search over stored embeddings |
| M6 | **LOW** | Nullable `owner_id`/`user_id` can orphan; enforcement 404s null owners | Orphaned data; deletion gaps | Low | Backfill ownership + cascade policy |
| P3 | **LOW** | Legacy role columns in 0001 (superseded), `student_answer.py` alias, dead `app/schemas/user.py` | Cleanup debt | Low | Docs + optional cleanup migrations |
| P3 | **LOW** | pre-commit declared but no `.pre-commit-config.yaml`; no package.json for JS harnesses | Tooling gap | Low | Add config / lockfile |

---

## PART T — Target Architecture (evidence-based, evolutionary)

Preserve the working core; evolve, don't rewrite.

```
                EduVision
      ┌──────────┼──────────┐
      ▼          ▼          ▼
 Presentation  AI Learning  Visual
 Engine        Engine       Engine
 (2D model)    (orchestrator)(intelligence)
      └──────────┼──────────┘
                 ▼
        Interaction Engine (player/motion)
                 ▼
        Learning Intelligence (mastery/events)
        ┌────────┴────────┐
        ▼                 ▼
   Knowledge Graph     ML/DL (later, eval-gated)
```
**Immediate structural upgrades (in priority order the repository evidence demands):**
1. Fix the quiz IDOR (S1) — must precede any shared-quiz feature.
2. Add CI/CD to make all quality gates enforced (currently manual).
3. Introduce the **2D slide-element model** for PowerPoint-class editing (the single biggest gap vs. the product vision; currently linear).
4. Repoint RAG retrieval to the stored vectors (close the "infrastructure without use" gap).
5. Back simulation/animation runtime with Redis/DB for HA.

---

## PART U — Dependency-Aware Roadmap

| Phase | Output | Prereqs / inputs | DB | API | FE | Tests | Notes |
|---|---|---|---|---|---|---|---|
| **1 (done)** | Foundation/security/correctness | — | 0025 (+4 FK idx) | auth revoke, upload bound, AI routing | — | 14 new | Complete |
| **2** | Production frontend (framework, routing, state, error/loading) | stable API contract | — | versioning/pagination/error schema first | team | E2E | Precedes editor work; remove orphaned mock |
| **3** | PowerPoint-class engine (2D element model, editor, undo/redo, layers, thematic states, import/export parity) | Phase 2 FE | new slide/element/layer/theme tables + migrations | editor CRUD | editor | editor + export golden | Biggest product gap; needs new 2D schema |
| **4** | AI-native generation onto 2D model + RAG vector retrieval | Phase 3 model; fix RAG retrieval | reuse | generation→2D | UI | gen+retrieval | Wire stored embeddings to tutor/retrieval |
| **5** | Visual intelligence breadth (more visual types, accessibility) | Phases 3–4 | extend canvas | spec | renderer | visual golden | Extend existing engine |
| **6** | Advanced visual rendering (WebGL/SVG/DOM, interactive, responsive) | Phase 5 | — | runtime | renderer | perf | — |
| **7** | Animation engine hardening (persist timelines, multi-object, state-driven) | Phase 5/3 | persist runtime | plan/runtime API | motion | runtime | Move in-memory runtime → Redis/DB |
| **8** | Simulation engine (registry + DSA/algorithm curricula, persistence, sandbox) | Phase 7 infra | defs/sessions tables | sim CRUD | sim | sim | Expand from 1 def |
| **9** | Knowledge graph + learning events | existing events | graph tables | events API | graph | — | Build on visual + learning events |
| **10** | ML/DL learner intelligence | Phases 9 data + eval harness vs heuristics | features store | — | — | eval | Eval-gated; do not skip baselines |
| **11** | Adaptive learning | Phase 10 | — | adaptive | — | — | — |
| **12** | AI tutor 2.0 (vector-grounded) | Phase 4 RAG + 9 KG | — | tutor | chat | — | — |
| **13** | Multimodal voice/video | existing TTS/video | — | media | — | — | Extend narration |
| **14** | Performance/security/scale + CI gates | all | — | — | — | CI/CD enforced | Add tracing/alerting/HA runtime |

**Ordering rationale vs. the original list (changes):**
- Phase 3 (editor) is moved **before** visual/animation breadth because the current content model is linear; building richer visuals on a linear model would be rework. Additive 2D schema is low-risk (new tables).
- RAG vector retrieval is pulled into Phase 4 (AI generation) because the tutor and generation both need it, and the vectors already exist.
- ML/DL (10) stays late and is gated on an evaluation harness; it is explicitly not worth building until baseline accuracy of the current heuristics is measured.

---

## PART V — Phase 1 Recommendation (what changes next)

Already executed as a separate working session (branch `feature/individual-user-foundation`, 6 commits). Immediate next engineering actions after this audit, in order:
1. **Fix the quiz ownership IDOR (P1)** — enforce ownership in `assert_quiz_ownership` + regression tests. **Highest urgency.**
2. **Enable magic-byte validation** on uploads (small, closes M1).
3. **Add CI/CD** (lint, mypy, unit, integration) — currently the only path to making the quality gate real (P2).
4. **Harden config**: fail-fast on unset APP_SECRET_KEY/CSRF_SECRET; rotate live creds in `backend/.env`.
5. Begin Phase 3 design (2D slide-element model) — the single biggest product-direction gap.

---

## FINAL COMMANDMENT

### What I would refuse to build on top of until fixed
1. **Any shared/collaborative or exposure of quizzes** while the quiz-ownership IDOR (S1) is open — a cross-user authorization hole at the resource boundary.
2. **A production deployment** while `APP_SECRET_KEY`/`CSRF_SECRET` can silently fall back to `CHANGE-ME-*` and while uploads accept unverified file contents and `/uploads` is served publicly.
3. **Scaled/multi-replica deployment** while simulation/animation/video/lesson runtime state lives only in in-memory dicts (data loss + split-brain across replicas) and migrations run at startup on every replica.
4. **Putting AI tutor / RAG features on the roadmap as "done"** while retrieval ignores the generated embeddings (positional fetch only) — the tutor would be ungrounded.
5. **Enforcing any quality gate via CI** (there is none) until CI/CD exists; today, "tests pass" is a manual/local claim.

### What is valuable enough to preserve and extend
- **The AI orchestration layer** (`AIContentService`, provider factory, retry/rate-limit/cache/cost) — clean abstraction; extend with new providers/features on it.
- **The visual-intelligence engine** (classifier → decision → relationship → persistence) — a real, working pipeline worth building visual types on.
- **The animation planner + Motion Engine** and the **video/TTS pipeline** (real H.264 + narration) — preserve and harden.
- **The individual-first ownership model** on presentations/canvases/players and the **auth stack** (Argon2 + JWT + Redis revocation) — the correct foundation for a single-user product.
- **The 61-model domain and migrations** up to head `0025` — a coherent, ownership-aware schema to extend, not rewrite.
- **The E2E harnesses** (`_mv_*`) — genuine regression value for the player.

### The single highest-leverage architectural change
**Introduce a true 2D slide-element model (geometry, z-order, layers, element types, undo/redo) and build the presentation editor on it** — because today the product can generate lessons and rich visuals but cannot express them as PowerPoint-class editable slides (the content model is linear blocks). Every later capability (AI-native slide authoring, animation on real objects, import/export parity, a full editor) depends on that 2D representation. It is additive (new tables), low-migration-risk, and unlocks the entire editor/product surface — **after** the P1 quiz IDOR and CI/CD are fixed.
