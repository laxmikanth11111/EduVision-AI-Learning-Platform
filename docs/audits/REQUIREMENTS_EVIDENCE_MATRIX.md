# Requirements → Evidence Matrix

How each requirement in the EduVision AI spec is satisfied and where to verify
it. Statuses: ✅ implemented + verified locally, 🟡 implemented, runtime-check
blocked by environment, 📝 works but improvement scoped out of this pass.

| # | Requirement | Where verified | Status |
| -- | ----------- | -------------- | ------ |
| 1 | Backend is Python (FastAPI), no Node | `backend/app/main.py`, `requirements.txt` | ✅ |
| 2 | AI-Powered lesson generation from uploaded content | `app/services/lesson_generation_service.py`; `test_lesson_generation_service.py` | ✅ |
| 3 | Async pipeline (Celery) for generation/embeddings | `app/workers/` (celery_app, tasks, rag_tasks, video_tasks); eager mode in tests | ✅ |
| 4 | Hierarchical topic outline product (C2) | `app/services/topic_outline_service.py`; `TestGenerate`/`TestRegenerate`/`TestGetOutline` | ✅ |
| 5 | Exact source references preserved in structured data | outline slide/range sorting + `test_source_text_passes_slide_positions`, `test_clamps_and_sorts_ranges` | ✅ |
| 6 | Structure-aware chunking / segmentation | `app/ai/embeddings/` + pipeline; RAG tests | ✅ |
| 7 | Semantic retrieval with provenance | `app/ai/retrieval.py` (`semantic_retrieve_chunks_with_meta`); `test_retrieval_provenance.py` (5) | ✅ |
| 8 | AI outputs validated as valid structured data | JAST/schema validation; unparseable-AI → retry then deterministic fallback (`test_retries_with_compact_source_on_unparseable`) | ✅ |
| 9 | Grounding / no hallucination guarantees | `GroundedLessonSafetyValidator` (+ input injection scan, topic non-empty, source-coverage estimate); `test_lesson_prompt_builder.py` TestSafety | ✅ |
| 10 | Persistence for AI outputs/blocks in DB | `GeneratedLesson`/`GeneratedBlock`, outline persist path (`test_happy_path_persists_and_returns_outline`) | ✅ |
| 11 | Vector store / embeddings persisted | `ChunkEmbedding` JSONB rows; embedding pipeline tasks | ✅ |
| 12 | Quiz → Mastery → Recommendation loop | quiz generation + scoring, mastery, recommendation services; deterministic scoring | ✅ |
| 13 | Quiz question types: multiple choice, matching, true/false, AI-generated | quiz schemas/services + tests | ✅ |
| 14 | Interleaved topic → visual → next visual in player | canonical `backend/frontend/player.html`; C3/C4/visual services | ✅ |
| 15 | Image/video simulation generation + optional TTS | C4 animation, simulation, video services + `video_tasks.py` | ✅ |
| 16 | Export capability | `app/api/v1/exports.py`, export services/templates | ✅ |
| 17 | Authentication & authorization (accounts, no anonymous write) | Argon2, JWT aud/iss/jti, per-user scoping; 404-equalized ownership errors | ✅ |
| 18 | Brute-force login protection | per-account lockout + 429, refresh rotation + reuse detection, rate limits; `test_auth_hardening.py` (9) | ✅ |
| 19 | Prompt-injection defense on untrusted data (documents + learner messages) | `app/ai/prompt_injection.py`; wired in lesson, outline, tutor; `test_prompt_injection.py` (16) | ✅ |
| 20 | Deterministic fallbacks when AI/Redis unavailable | local provider, in-memory caches, eager tasks, outline repair/retry | ✅ |
| 21 | Observability: request IDs, timing, metrics, logging, health | middleware package; `app/workers/` Celery signals; retry/ratelimit/cost telemetry | ✅ |
| 22 | Data containment / user ownership privacy | owner_id enforcement, per-user storage keys, RAG scoped to owner's content units | ✅ |
| 23 | CI gates | `.github/workflows/ci.yml`: lint, unit, integration, migration-check, postgres, secret-scan, mypy (−86 budget), docker-build | ✅ |
| 24 | No non-free code/AI in the core loop (local option) | local deterministic provider + local embedding provider | ✅ |
| 25 | Performance: PostgreSQL prod, indexing, caching | docker-compose postgres; app-level caching/ratelimiting; async everywhere | ✅ |
| 26 | Backend-only architecture support (static frontend served by FastAPI) | `app/main.py` mounts `frontend/` | ✅ |
| 27 | PostgreSQL-backed suite | `tests/postgres` (marker `postgres`) + CI job | 🟡 requires Docker |
| 28 | End-to-end browser suite | `tests/e2e` (marker `e2e`) | 🟡 requires running server + browser |
| 29 | Docker compose boot verification | `docker-compose.yml` reviewed; not runtime-verified on this machine | 🟡 |
| 30 | Live paid provider call verification | keys out of quota; deterministic local used in all runs | 🟡 |
| 31 | Full mypy-clean static typing | `mypy app` = 83 errors (≤ 86 CI budget); no growth | 📝 tracked budget |
| 32 | CSRF token middleware | mitigated (SameSite=Lax + HttpOnly + header check); no token middleware | 📝 |
| 33 | `User` model login_attempts/locked_until columns | absent in model (present in 0001); enforcement lives at auth layer instead | 📝 schema drift documented |
| 34 | Orphaned `EduVision_AI_Frontend` removal | DEPRECATED marker added; directory retained for reference | 📝 |

## Quick regression proof (2026-09-15)

| Check | Result |
| ----- | ------ |
| `pytest tests/unit` | 1373 passed |
| `pytest tests/integration` | 204 passed |
| `ruff check app tests scripts --no-fix` | All checks passed |
| `mypy app` | 83 errors (budget 86) |
| `alembic heads` | single head `0036_c4_topic_animation_assets` |