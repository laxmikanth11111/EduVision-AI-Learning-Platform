# POST-P5 Product Capability Matrix

**Repository state:** HEAD = `cba306b`, branch `feature/individual-user-foundation`, working tree clean.
**Generated:** 2026-09-03

> Every capability below is evidence-sourced to repository files.
> Classification:
> - **Browser Verified** — demonstrated in a real browser via Playwright E2E
> - **API Verified** — endpoint exists and passes integration/unit tests
> - **Backend Implemented** — service code exists but not exposed via API or UI
> - **Partial** — exists but incomplete or hardcoded
> - **Planned** — documented intent but no implementation
> - **Not Implemented** — no code exists

---

## 1. Authentication & User Management

| Capability | Status | Evidence |
|------------|--------|----------|
| Email/password registration | Browser Verified | E2E `test_smoke.py` signup flow |
| Email/password sign-in | Browser Verified | E2E `test_smoke.py` signin flow |
| Google OAuth sign-in | Browser Verified | `signin.html` Google button + `/api/v1/auth/google` |
| JWT token refresh | Browser Verified | `authFetch()` auto-refresh in player.html |
| Token revocation (Redis) | API Verified | `auth.py` logout endpoint |
| User profile (`/auth/me`) | API Verified | `auth.py` |
| Password hashing (bcrypt) | Backend Implemented | `core/security.py` |
| Fail-fast config (missing secret key) | Backend Implemented | `core/config.py`, P1 verified |

## 2. Content Ingestion

| Capability | Status | Evidence |
|------------|--------|----------|
| File upload (PDF/DOCX/PPTX/TXT) | Browser Verified | E2E `test_smoke.py` upload flow |
| Manual deck creation | Browser Verified | `upload.html` manual form |
| Presentation CRUD | API Verified | `presentations.py` (30+ endpoints) |
| Presentation folders | API Verified | `presentation_folders.py` |
| Content extraction (document parsing) | Backend Implemented | `parsers/document_parser.py` |
| Presentation versions + autosave | API Verified | `presentations.py` |
| Presentation thumbnails | API Verified | `presentations.py` |
| Source upload + processing | Browser Verified | `processing.html` polling |

## 3. AI Content Generation

| Capability | Status | Evidence |
|------------|--------|----------|
| AI lesson generation | Browser Verified | E2E creates lesson via API |
| AI presentation generation | API Verified | `presentations.py` lesson endpoint |
| AI quiz generation | API Verified | `quiz.py` `/quizzes/generate` |
| AI topic outline generation | API Verified | `topic_outline_service.py` |
| AI visual prompts | Backend Implemented | `visual_prompts.py` |
| AI canvas classification | Backend Implemented | `component_discovery_service.py` |
| AI animation planning | API Verified | `animation_router.py` `/animations/plan` |
| AI video scripting | Backend Implemented | `video_script_service.py` |
| AI assistant/tutor | API Verified | `assistant.py` (10 endpoints) |

## 4. Visual Learning

| Capability | Status | Evidence |
|------------|--------|----------|
| Canvas diagram (SVG) | Browser Verified | Player renders canvas via `/visual/canvases` |
| 6 strategy renderers (radial/flowchart/comparison/timeline/hierarchy/cycle) | Browser Verified | `player.html` `renderEducationalVisual` |
| Animation (Motion Engine v2) | Browser Verified | Player renders via `/animations/plan` + runtime |
| Video playback | Browser Verified | Player renders via `/videos/create` |
| Simulation step-through | Browser Verified | Player renders via `/simulations/definitions` |
| Visual canvas CRUD + nodes/edges/components | API Verified | `visual_canvases.py` (10 endpoints) |
| Simulation definitions (5 hardcoded) | API Verified | `simulation.py` (8 endpoints) |
| Animation blueprint + timeline | API Verified | `animation_router.py` + `animation_runtime_router.py` |
| Video composition + rendering | API Verified | `video_router.py` + `video_runtime_router.py` |

## 5. Lesson Player

| Capability | Status | Evidence |
|------------|--------|----------|
| Player loads lesson topics | Browser Verified | E2E `test_smoke.py` player test |
| Concept slide rendering | Browser Verified | `player.html` concept slide |
| Visual slide rendering | Browser Verified | `player.html` visual slide |
| Sidebar thumbnail navigation | Browser Verified | `player.html` thumbnails |
| Present mode (fullscreen) | Browser Verified | `player.html` present mode |
| Keyboard navigation | Browser Verified | `player.html` keydown handler |
| Visual type selector (auto/image/animation/video/sim) | Browser Verified | `player.html` type buttons |
| Visual recommendation chip | Browser Verified | `player.html` reco chip |
| Visual caching (re-render prevention) | Browser Verified | `player.html` `cacheVisual` |

## 6. Learner Journey (P5)

| Capability | Status | Evidence |
|------------|--------|----------|
| Persistent per-user lesson progress | Browser Verified | P5 E2E + `LearningSessionService` |
| Progress bar display | Browser Verified | P5 E2E `test_learner_journey_panel_renders` |
| Assessment checkpoint status | Browser Verified | P5 E2E `test_learner_journey_endpoints_authorized` |
| Mastery summary display | Browser Verified | P5 E2E panel text verification |
| Next-action text display | Browser Verified | P5 E2E panel text verification |
| Progress sync to server | Browser Verified | `player.html` `syncTopic()` |
| Session resume after refresh | Browser Verified | P5 `get_or_create` idempotent resume |
| **Quiz-taking UI** | **NOT IMPLEMENTED** | No quiz UI in `player.html` |
| **Quiz answer submission (browser)** | **NOT IMPLEMENTED** | No answer selection UI |
| **Quiz results display (browser)** | **NOT IMPLEMENTED** | No results rendering |
| **Mastery update from quiz (browser path)** | **NOT IMPLEMENTED** | No browser-triggered mastery flow |

## 7. Quiz System (Backend Complete, Frontend Missing)

| Capability | Status | Evidence |
|------------|--------|----------|
| Quiz generation (AI) | API Verified | `quiz.py` `/quizzes/generate` |
| Quiz metadata retrieval | API Verified | `quiz.py` `/quizzes/{id}` |
| Quiz attempt start/resume | API Verified | `quiz.py` `/quizzes/{id}/attempts` |
| Quiz attempt listing | API Verified | `quiz.py` `/quizzes/{id}/attempts` GET |
| Quiz attempt detail | API Verified | `quiz.py` `/quizzes/{id}/attempts/{id}` |
| Single answer submission | API Verified | `quiz.py` `/quizzes/{id}/attempts/{id}/answers/{qid}` |
| Quiz submit + scoring | API Verified | `quiz.py` `/quizzes/{id}/attempts/{id}/submit` |
| Ownership-404 on quiz endpoints | Backend Implemented | `QuizAttemptService.assert_quiz_ownership` |
| **Quiz-taking UI in SPA** | **NOT IMPLEMENTED** | **Critical gap** |
| **Question display in browser** | **NOT IMPLEMENTED** | **Critical gap** |
| **Answer selection in browser** | **NOT IMPLEMENTED** | **Critical gap** |
| **Submit + results in browser** | **NOT IMPLEMENTED** | **Critical gap** |

## 8. Learner Intelligence

| Capability | Status | Evidence |
|------------|--------|----------|
| Educational memory (concept mastery) | API Verified | `educational_memory_service.py` |
| Mastery categorization (weak/developing/mastered) | Backend Implemented | `educational_memory_service.py` |
| Recommendation engine (deterministic) | API Verified | `recommendation_engine.py` via `/player/mastery` |
| Adaptive assessment engine (difficulty ladder) | Backend Implemented | `adaptive_assessment_engine.py` |
| Learning context service | Backend Implemented | `learning_context_service.py` |
| Learning event service | Backend Implemented | `learning_event_service.py` |
| Effectiveness assessments (baseline/post/retention) | API Verified | `effectiveness.py` |
| **Concept mastery visualization (charts)** | **NOT IMPLEMENTED** | Text only |
| **Learning velocity tracking** | **NOT IMPLEMENTED** | No data |
| **Historical progress dashboard** | **NOT IMPLEMENTED** | Current lesson only |

## 9. RAG / Semantic Retrieval

| Capability | Status | Evidence |
|------------|--------|----------|
| Vector semantic retrieval (cosine) | Backend Implemented | P4 WS3 |
| AI tutor with RAG context | Backend Implemented | `learning_assistant_service.py` |
| Embedding pipeline (batch) | Backend Implemented | `embedding_batch_service.py` |
| Embedding refresh | Backend Implemented | `embedding_refresh_service.py` |
| Embedding cleanup | Backend Implemented | `embedding_cleanup_service.py` |
| Embedding integrity check | Backend Implemented | `embedding_integrity_service.py` |
| Chunk embedding storage | Backend Implemented | `chunk_embedding.py` model |
| RAG indexing (Celery task) | Backend Implemented | `rag_tasks.py` |

## 10. Export

| Capability | Status | Evidence |
|------------|--------|----------|
| PDF export | API Verified | `exports.py` + `pdf_exporter.py` |
| DOCX export | API Verified | `exports.py` + `docx_exporter.py` |
| PPTX export | API Verified | `exports.py` + `pptx_exporter.py` |
| Markdown export | API Verified | `exports.py` + `markdown_exporter.py` |
| HTML export | API Verified | `exports.py` + `html_exporter.py` |
| CSV/TSV export | API Verified | `exports.py` + `csv_exporter.py` |
| JSON bundle export | API Verified | `exports.py` + `json_bundle_exporter.py` |
| Flashcards export | Backend Implemented | `exporter_factory.py` |
| Mindmap export | Backend Implemented | `exporter_factory.py` |
| ZIP export | Backend Implemented | `exporter_factory.py` |
| **Analytics CSV export** | **Partial** | Raises `NotImplementedError` |

## 11. Workers & Async

| Capability | Status | Evidence |
|------------|--------|----------|
| Celery worker | Backend Implemented | `workers/celery_app.py` |
| DLQ + bounded retry | Backend Implemented | P2 verified |
| Idempotency key support | Backend Implemented | `workers/idempotency.py` |
| Export worker task | Backend Implemented | `workers/tasks.py` |
| RAG indexing worker | Backend Implemented | `workers/rag_tasks.py` |
| Beat schedule (health/analytics/cleanup/embeddings) | Backend Implemented | `workers/celery_app.py` |
| Observability (Prometheus metrics) | Backend Implemented | `observability/metrics.py` |

## 12. Infrastructure

| Capability | Status | Evidence |
|------------|--------|----------|
| Docker multi-stage build | Backend Implemented | `Dockerfile`, P4 WS6 verified |
| docker-compose (postgres/redis/minio/backend/worker/beat) | Backend Implemented | `docker-compose.yml` |
| GitHub Actions CI | Backend Implemented | `.github/workflows/ci.yml` |
| Alembic migrations (28, single head) | Backend Implemented | Verified |
| Rate limiting | Backend Implemented | `middleware/rate_limit.py` |
| Request ID tracking | Backend Implemented | `middleware/request_id.py` |
| Security headers | Backend Implemented | `middleware/security.py` |
| Trusted host middleware | Backend Implemented | `middleware/trusted_host.py` |
| Request size limiting | Backend Implemented | `middleware/request_size_limit.py` |

---

## Summary: The Critical Gap

The platform has a complete backend for every stage of the learning loop:
1. Content ingestion → ✅
2. AI generation → ✅
3. Visual learning (canvas/animation/video/simulation) → ✅
4. Lesson player → ✅
5. Persistent progress → ✅ (P5)
6. Quiz system (backend) → ✅
7. Mastery tracking (backend) → ✅
8. Recommendations (backend) → ✅

**But the learner cannot take a quiz through the browser.** This breaks the loop at step 6, which prevents steps 7 and 8 from functioning through the user-facing product. The entire learner intelligence layer (mastery, recommendations, adaptive learning) is orphaned from the user experience because there is no quiz-taking UI to generate the data that drives these systems.

**P6 closes this gap by building the quiz-taking UI in the vanilla SPA player.**
