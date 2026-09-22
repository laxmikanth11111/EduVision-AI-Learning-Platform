# EduVision AI — Architecture

> Status: current as of 2026-09-15. Supplements
> `docs/audits/BASELINE.md` (pre-improvement snapshot) with a component-level
> view, including the hardening added in this pass (grounded safety, prompt-injection
> defense, auth hardening, RAG provenance).

## 1. System context

```
                    Browser (canonical UI served by FastAPI at /frontend)
                                   |
                                   v
            ┌──────────────────────────────────────────────┐
            │                FastAPI (app.main)             │
            │  middleware: request-id, rate-limit, security  │
            │  headers/CSP, timing, ...                     │
            │  routers under app/api/v1 (27 routers)         │
            └───────────┬──────────────┬───────────────────┘
                        │              │
                  ┌─────▼─────┐  ┌─────▼──────────────────────────────┐
                  │  DB       │  │  Services layer (app/services)      │
                  │  SQLite   │  │  lesson/topic/quiz/tutor/visual...  │
                  │  (tests)  │  │            │                        │
                  │  Postgres │  │  ┌─────────▼─────────┐              │
                  │  (prod,   │  │  │  AI (app/ai)       │              │
                  │  asyncpg) │  │  │  provider factory   │              │
                  └─────┬─────┘  │  │  Gemini/OpenAI/local │              │
                        │        │  └─────────┬─────────┘              │
                  ┌─────▼─────┐  ┌─────▼─────┐  ┌──────────────────┐
                  │ Celery    │  │ Redis     │  │ Storage (S3/local) │
                  │ workers   │  │ (cache,   │  │ files/renders     │
                  │ (broker=   │  │  rate-    │  └──────────────────┘
                  │  redis db1)│  │  limit,   │
                  └───────────┘  │  lockout) │
                                 └──────────┘
```

Producer functions: each AI call goes through `AIContentService`
(`app/ai/service.py`) which composes retry, rate-limit, cache, token/cost
accounting, and structured-output validation.

## 2. Data model (core entities)

| Entity | Model | Notes |
| ------ | ----- | ----- |
| User | `app/models/user.py` | login_attempts / locked_until present in 0001 but absent in model |
| Presentation | `presentation.py` | owner-scoped, soft-delete, archived state |
| ContentUnit / DocumentChunk | `content_unit.py`, `document_chunk.py` | source structure after extraction |
| ChunkEmbedding | `chunk_embedding.py` | JSONB vector, chunk-scoped similarity |
| GeneratedLesson / GeneratedBlock | `generated_lesson.py`, `generated_block.py` | validated structured AI output |
| LessonOutline / Topic / Slide | `topic_outline` models | hierarchical, range-sorted slides |
| Quiz attempts / Mastery / Recommendations | `quiz_attempt`, `mastery`, `recommendation` | deterministic scoring loop |
| Visual learning | C3 visual frontends, C4 animation assets, simulation, video records | file-backed |

Alembic head at time of writing: `0036_c4_topic_animation_assets` (single head).

## 3. Request → generation flow (lesson generation)

1. Upload/extraction: `app/parsers/document_parser.py` → content units.
2. Async pipeline (`app/workers/rag_tasks.py`, `app/workers/tasks.py`):
   structure-aware chunking → embeddings persisted as `ChunkEmbedding`.
3. Topic outline (C2): `app/services/topic_outline_service.py` builds a deep
   outline with exact source refs. `_assert_no_injection` (new) rejects
   document-controlled source text that lexically matches prompt-injection
   signatures; `regenerate()` falls back to a deterministic outline when AI
   output is unparseable or unsafe.
4. Lesson generation: `app/services/lesson_generation_service.py` runs a
   RAG-grounded prompt, validates the model reply against a Pydantic schema,
   and runs the configured **safety validator** before persisting.
5. Safety validator (`app/services/lesson_safety.py`): default `grounded`
   validator (a) refuses empty input and blocks `is_reliably_flagged`
   prompt-injection input, (b) rejects outputs with no topics, and (c) records
   a **source-coverage estimate** from the RAG context. `Noop` validator
   remains for opt-out.
6. Quiz/mastery: quiz generation service → deterministic scoring →
   mastery state → recommendations. Mastery tutor (`mastery_tutor_service.py`)
   answers with RAG and a deterministic refusal path for injected requests.

## 4. Prompt-injection defense (new)

- Scanner: `app/ai/prompt_injection.py`
  - `scan_for_prompt_injection(text, threshold=3.0)` → `InjectionScanResult`
    with per-rule matches, matched rule weights, and a combined score.
  - Decision helper: `is_reliably_flagged(result)` — true when any matched rule
    has weight ≥ 2.0 (strong/critical signature) independent of the soft-flag
    threshold. Single strong rules (e.g. "Print your system prompt." →
    `reveal_system_prompt` 2.0) gate blocking even below the 3.0 soft threshold;
    `tool_invoke` sits at 1.5 so coding questions about tool calls are not blocked.
- Enforced at every untrusted-data boundary:
  - `lesson_safety.validate_input` (pre-prompt),
  - `topic_outline_service._assert_no_injection` (pre-prompt, document text),
  - `mastery_tutor_service._produce_answer` (learner messages → deterministic refusal).
- Config: `AI_PROMPT_INJECTION_ENABLED`, `AI_PROMPT_INJECTION_THRESHOLD`,
  `AI_PROMPT_INJECTION_REFUSAL`.

## 5. Authentication & session hardening (new)

- Hashing: Argon2-ID via `app/core/security.py`.
- JWT access tokens carry `aud`/`iss`/`jti`; refresh tokens in HttpOnly cookies
  (SameSite=Lax; CSRF mitigated by header check).
- **Brute-force lockout** (`app/api/v1/auth.py`): per-account counter keyed
  `eduvision:auth:login_failures:<account>` in Redis with in-memory fallback;
  `_lockout_window_seconds()` wraps `MAX_LOGIN_ATTEMPTS`/`LOGIN_LOCKOUT_MINUTES`
  (5 attempts / 15 minutes). Locked login returns **429**; success clears counters.
- **Refresh rotation**: `/auth/refresh` revokes the presented JTI and issues a
  new pair; replay of a revoked JTI → 401 and logs `refresh_token_reuse_detected`.
- Rate limits: `^/api/v1/auth/login$` and `^/api/v1/auth/register$` = 10 per 60s.

## 6. RAG provenance (new)

- `app/ai/retrieval.py`:
  - `semantic_retrieve_chunks_with_meta(embedding_service, db, content_unit_ids, query, top_k=3)`
    covers unit store → embed query → similarity sort → top-k `RetrievedChunk`
    (chunk_id, content_unit_id, position, similarity, content, snippet).
  - Content-only wrapper `semantic_retrieve_chunks` is preserved for existing
    callers.
- Tutor/lesson prompts now include per-chunk provenance attributes so answers
  can be attributed to source (`docs/evaluation/` records an example trace).

## 7. Async / worker architecture

- Celery 5.x + Redis broker (db 1), results (db 2); `task_acks_late=True`,
  `task_reject_on_worker_lost=True`, `prefetch=1`, DLQ route, idempotency layer.
- Beat schedule: health-check, analytics aggregation, soft-delete/draft cleanup,
  embedding refresh/cleanup/statistics.
- Tests run `CELERY_TASK_ALWAYS_EAGER=true`; Redis is not required locally
  (in-memory fallbacks everywhere).

## 8. Storage & observability

- Storage adapter: S3/MinIO with a local filesystem adapter; per-user keys.
- Middleware: request-id correlation, rate limiting (in-memory/Redis), security
  headers + CSP, timing logs. `/health` reports provider/db/redis/workers state.

## 9. Frontend

- Canonical: `backend/frontend/*.html` served by FastAPI at `/frontend`
  (aliases `/`, `/login`, `/dashboard`, `/player`, `/tutor`, `/upload`,
  `/processing`, `/videos`).
- `EduVision_AI_Frontend/eduvision_frontend/` is a **DEPRECATED** static
  prototype (marked read-only) — not mounted anywhere.

## 10. Test strategy

| Layer | Where | Notes |
| ----- | ----- | ----- |
| Unit | `tests/unit` (1373 tests) | injection defense, grounded validator, auth hardening, provenance, schema validation, seeding, API behavior |
| Integration | `tests/integration` (204 tests) | full app wiring on SQLite aiosqlite |
| Postgres | `tests/postgres` (marker `postgres`) | needs Docker/testcontainers — not run locally |
| e2e | `tests/e2e` (marker `e2e`) | needs running server + browser — not run locally |

Test commands (all green locally):

```
pytest tests/unit --no-header -q --tb=line            # 1373 passed
pytest tests/integration --no-header -q --tb=line     # 204 passed
ruff check app tests scripts --no-fix                 # all checks passed
mypy app                                              # 83 errors (budget 86)
```

## 11. Configuration surface

`.env.example` documents: auth JWT/refresh, `MAX_LOGIN_ATTEMPTS`,
`LOGIN_LOCKOUT_MINUTES`, RATE_LIMIT_ROUTES and auth-route overrides,
`AI_PROMPT_INJECTION_ENABLED/THRESHOLD/REFUSAL`,
`AI_LESSON_SAFETY_VALIDATOR=grounded` (lesson + quiz defaults), grounding
tolerances (`AI_MAX_EMPTY_TOPIC_RATIO`, etc.), Redis URLs, storage provider,
and AI provider keys (placeholder-only).

## 12. Deployment topologies

- **docker-compose.yml**: postgres, redis, minio, backend, celery-worker,
  celery-beat with health checks and volumes.
- CI runs the same gates (lint, unit, integration, migration-check, postgres,
  secret-scan, mypy-gate with explicit budget, docker-build) — see
  `.github/workflows/ci.yml`.