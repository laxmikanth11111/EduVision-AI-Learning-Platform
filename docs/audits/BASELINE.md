# EduVision AI — Engineering Baseline

> Date: 2026-09-15
> Complied from a fresh, read-only audit of the repository *before* the improvement phase.
> This document records what existed, which checks were run, and what the current test/static status was.

---

## 1. Repository Outline

```
EduVision AI — AI-Powered Interactive Learning Platform/
├── backend/                     # FastAPI application (canonical backend)
│   ├── app/
│   │   ├── api/v1/              # 27 routers (auth, presentations, player, quiz, visual,
│   │   │                        #   c3 visual, c4 animation, simulation, video, tutor,
│   │   │                        #   assistant, exports, analytics, path, goals, ...)
│   │   ├── ai/                  # provider abstraction, retry, ratelimit, cache, cost,
│   │   │   │                    #   embeddings (providers + pipeline), retrieval
│   │   ├── core/                # config, security (jwt/argon2), logging, exceptions
│   │   ├── database/            # session, unit_of_work, retry, base model, migrations (Alembic)
│   │   ├── middleware/          # request-id, rate-limit, security-headers, CSP, timing, ...
│   │   ├── models/              # SQLAlchemy models + 0036 migrations
│   │   ├── parsers/             # document_parser (PDF/PPTX/DOCX/TXT)
│   │   ├── repositories/        # repository layer
│   │   ├── schemas/             # Pydantic schemas
│   │   ├── services/            # lesson generation, topic outline, quiz, mastery,
│   │   │                        #   recommendation, tutor, assistant, exports, C3/C4 visuals
│   │   ├── storage/             # S3/MinIO + local adapters
│   │   ├── workers/             # Celery app, tasks, rag_tasks, video_tasks,
│   │   │                        #   idempotency, c3/c4 tasks, redis_client, cache
│   │   └── main.py              # FastAPI app + middleware stack + frontend mount
│   ├── frontend/                # CANONICAL frontend (vanilla JS/HTML served at /frontend)
│   ├── tests/                   # unit/ integration/ postgres/ e2e/
│   ├── docs/                    # phase reports P0–P17 + POST_P* audits
│   └── scripts/                 # verification scripts (browser checks, sample generators)
├── EduVision_AI_Frontend/
│   └── eduvision_frontend/      # ORPHANED static prototype (NOT served, NOT used)
├── .github/workflows/ci.yml     # CI: lint, unit, integration, migration, postgres, secret scan, mypy, docker
├── docker-compose.yml           # postgres + redis + minio + backend + celery-worker + celery-beat
├── .env.example                 # placeholder-only secrets (scrubbed)
├── .gitignore                   # comprehensive
└── MEMORY.md                    # session memory (gitignored)
```

---

## 2. Detected Architecture & Technologies

| Area | Technology |
| ---- | ---------- |
| Backend | Python ≥3.13 (venv on this machine is **3.14.6**), FastAPI, uvicorn |
| ORM | SQLAlchemy 2.x async, asyncpg, aiosqlite (tests), Alembic migrations |
| Queue | **Celery 5.x + Redis** (broker db 1, results db 2), beat scheduler, DLQ option, idempotency layer |
| Cache/rate-limit | Redis (db 0) with in-memory fallbacks |
| Storage | S3-compatible (MinIO) with local adapter; files stored under user-scoped keys |
| AI | Provider abstraction: Gemini, OpenAI, **local deterministic mock**; AIContentService wrapper (retry/timeout/ratelimit/cache/tokens/cost); embedding providers incl. local; telemetry |
| RAG | Structure-aware chunking → JSONB-vector embeddings (app-side cosine) → semantic retrieval + positional fallback |
| Frontend | Vanilla JS/HTML multi-page SPA served by FastAPI as static files |
| TTS | edge-tts / gTTS optional |
| Video | FFmpeg/OpenCV render pipeline with H.264 transcode (imageio-ffmpeg) |
| Tests | pytest (asyncio), 1337 unit + 204 integration green at baseline |

---

## 3. Worker Architecture (Celery)

- `app/workers/celery_app.py` — Celery app + signal-based observability (request-id correlation, task duration metrics).
- Route map: `eduvision.ai.*`→ai, `eduvision.upload.*`→uploads, `eduvision.rag.index`/`eduvision.embedding.*`→embeddings/embedding_batch/analytics, `eduvision.videos.*`→videos, `eduvision.dlq.record`→dead_letter.
- Global task settings: `task_acks_late=True`, `task_reject_on_worker_lost=True`, `worker_prefetch_multiplier=1`, time limits, `task_track_started=True`.
- Beat schedule: health-check, analytics aggregation, draft/archived/soft-delete cleanup, embedding refresh/cleanup/statistics.
- Tasks: `app/workers/tasks.py`, `rag_tasks.py`, `video_tasks.py`, `c3_visual_tasks.py`, `c4_animation_tasks.py`.
- Tests run with `CELERY_TASK_ALWAYS_EAGER=true` so no broker is required in CI/local unit tests.

## 4. AI Provider Architecture

- `app/ai/providers/` — `_base.py`, `gemini.py`, `openai.py`, `local.py`, `_http.py`.
- `app/ai/` — `service.py` (AIContentService), `retry.py` (bounded exponential backoff + jitter), `ratelimit.py`, `cache.py`, `cost.py`, `tokens.py`, `models.py`.
- `app/ai/embeddings/` — base + factory + providers (local/openai/gemini); pipeline workers chunk→embed→persist in `ChunkEmbedding` rows (JSONB vector).
- Local mock provider is deterministic — tests do not require paid APIs.

## 5. Database Architecture

- PostgreSQL default target; tests use SQLite (aiosqlite) unless `-m postgres`.
- Alembic head at baseline: **0036_c4_topic_animation_assets** (single head).
- Ownership: presentations/documents/canvases/permission-scoped services consistently enforce `owner_id` with 404-equalized errors.
- Known item: `User` model has no `login_attempts`/`locked_until` columns (present in 0001 migration; drift) — documented in security findings.

## 6. Frontend Locations

| Path | Role |
| ---- | ---- |
| `backend/frontend/*.html` | **Canonical** — mounted at `/frontend` by `app/main.py` (`_resolve_frontend_dir`, StaticFiles html=True), aliased at `/`, `/login`, `/dashboard`, `/player`, `/tutor`, `/upload`, `/processing`, `/videos` |
| `EduVision_AI_Frontend/eduvision_frontend/` | **Orphaned static prototype** — not mounted, referenced by README only as an old copy |

## 7. Test Locations

| Suite | Location | Baseline result |
| ----- | -------- | --------------- |
| Unit | `backend/tests/unit` | 1337 passed (96.44s) |
| Integration | `backend/tests/integration` | 204 passed (95.80s) |
| Postgres | `backend/tests/postgres` (marker `postgres`) | NOT RUN — requires Docker/testcontainers (unavailable on this machine) |
| E2E (Playwright) | `backend/tests/e2e` (marker `e2e`) | NOT RUN — requires a running server + browser |

## 8. Commands Actually Executed (baseline)

| Command | Result |
| ------- | ------ |
| `.venv\Scripts\python.exe -m pytest tests/unit --no-header -q --tb=short` | **1337 passed** |
| `.venv\Scripts\python.exe -m pytest tests/integration --no-header -q --tb=short` | **204 passed** |
| `.venv\Scripts\python.exe -m ruff check app tests scripts --no-fix` | **1 error** (PT018 in `tests/unit/test_c4_animation_security.py:103`, untracked new file) |
| `.venv\Scripts\python.exe -m mypy app` | **83 errors** (CI budget: 86 baseline; 24 files; no growth) |
| Python interpreter | `backend/.venv` = **Python 3.14.6**; `pyproject.toml` requires **>=3.13**; CI uses **3.13** |

## 9. Docker Status

- `docker-compose.yml` present: postgres, redis, minio, backend, celery-worker, celery-beat; health checks defined; volumes persist data.
- Docker executable **not available** on this machine (`docker --version` does not return within timeout) → Docker runtime verification **BLOCKED** locally; `backend/Dockerfile` exists and CI includes a `docker-build` job.

## 10. Known Blocker / Debt at Baseline

- Local Redis service is frozen/unresponsive on Windows; app tolerates it (in-memory fallbacks) but `/health` reports degraded.
- Local Postgres not present; PostgreSQL-backed test suites need Docker (blocked).
- mypy carries 83 pre-existing errors (tracked against a 86 budget in CI).
- `lesson_safety.py` default validator is a **no-op regardless of configured name** (dead-config: `AI_LESSON_SAFETY_VALIDATOR`, `TUTOR_INJECTION_FLAG_THRESHOLD`, `TUTOR_GROUNDED_*` are all unused).
- Login brute-force lockout config (`MAX_LOGIN_ATTEMPTS`/`LOGIN_LOCKOUT_MINUTES`) is **dead** — no enforcement anywhere.
- No refresh-token rotation on `/auth/refresh`.
- No CSRF middleware (mitigated by SameSite=Lax + HttpOnly cookies).
- Working tree contains uncommitted in-progress C4 animation feature work (branch `feature/individual-user-foundation`).
- `backend/.env` (gitignored) holds live Gemini/Google credentials — must be rotated and kept out of synced/unshared folders.