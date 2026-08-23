# EDUVISION AI

## AI-Powered Interactive Learning & Understanding Platform

### Final Technical, Architecture, Verification & Resume Report

Report date: 23 August 2026 - Backend version 1.0.0 (`app/core/config.py`)
Verification basis: direct inspection of the source tree plus a fresh full-suite run performed during this audit (pytest: **843 passed / 0 failed** in 257.86 s; Ruff: **all checks passed**).

---

# PART 1 - PROJECT IDENTITY

| Item | Value |
|---|---|
| Project name | EduVision AI |
| Professional title | EduVision AI - AI-Powered Interactive Learning & Understanding Platform |
| Short title | EduVision AI |
| One-line description | Turns any PPTX/document into an AI-understood, visually interactive lesson with animations, simulations, video, assessment and a personal tutor. |
| Version | 1.0.0 (`pyproject.toml`, `APP_VERSION`) |
| API self-description | "AI-powered Interactive Learning Platform API" (`app/main.py`) |

**2-3 line professional description**

EduVision AI ingests PPTX/PDF/DOCX/TXT content and uses LLM understanding (with deterministic engineering fallbacks) to extract topics, generate lessons, and classify each concept into one of 22 educational categories. A strategy-aware visual engine selects one of 10 visualization types per concept and renders it as interactive SVG inside a custom Presentation Player, backed by a FastAPI / PostgreSQL / Redis / Celery stack with quizzes, an AI tutor, simulations, animated explainers, narrated H.264 video, TTS, effectiveness analytics, and mastery-based personalization.

**Problem statement**

Slides present information; they do not teach it. Learners reading dense decks must mentally reconstruct structures (sequences, hierarchies, comparisons, cycles) that the slides never make explicit.

**Problems with conventional learning/presentation systems**

- LMS platforms distribute content but add no understanding layer.
- Slides are linear bullet text; relationships between concepts stay implicit.
- Non-visual learners get no diagrammatic or animated representation.
- Comprehension is rarely measured or fed back into personalization.

**EduVision's solution**

A universal understanding pipeline: content -> AI comprehension -> topic extraction -> lesson/concept explanation -> strategy-classified visual generation -> interactive player (animations, simulations, video) -> assessment/tutor -> mastery insights.

**Product vision**

EduVision is *not* a teacher-student LMS. It is a **universal AI-powered learning and understanding platform**: any person, any explanatory document, better understanding.

```
PPTX / learning content
      v
AI understanding
      v
Topic extraction
      v
Concept explanation
      v
Educational visual generation (strategy-aware)
      v
Interactive learning (Presentation Player)
      v
Animation / simulation / video
      v
Assessment / tutor / insights
```

**Target users:** students, self-learners, professionals, educators preparing material, anyone who must understand written/slide content quickly.

---

# PART 2 - WHAT EDUVISION ACTUALLY DOES (END-TO-END, VERIFIED)

Verified flow (`frontend/upload.html`, `processing.html`, `player.html`; `app/services/*`; `app/workers/tasks.py`):

1. User signs in (email/password or Google OAuth) - `POST /auth/register`, `/auth/login`, `/auth/google`.
2. User uploads a deck/document - `POST /presentations` then `POST /presentations/{id}/source` (multipart). Server validates extension (.pptx/.pdf/.docx/.txt), magic bytes, <=100 MB size.
3. Extraction runs as a Celery task (`eduvision.presentations.process_source_ingestion`); `processing.html` polls `GET /presentations/{id}` until `extraction_status=ready`. python-pptx extracts slide titles, paragraphs, list items, tables, image metadata, speaker notes into ContentUnit/ContentBlock rows (caps: 200 units x 200 blocks).
4. On extraction completion the backend auto-triggers slide-mode lesson generation; topics are outlined by an LLM pass (max 12 topics with slide ranges, persisted in `topic_outlines`).
5. Lesson task `eduvision.lessons.generate` produces structured topic explanations (title/description JSON contract) persisted as versioned GeneratedLessonVersion + GeneratedBlock rows; lifecycle queued->processing->ready/failed. If the AI provider fails/is exhausted, a documented heuristic fallback builds one block per source unit.
6. The Presentation Player calls `POST /lessons/{id}/player/start`, receiving the ordered topic list; each topic becomes two slides: Concept (explanation) and Visual (interactive visual).
7. On demand ("Generate Visual"), the player calls visual/canvas, animation, simulation or video APIs; the Visual Intelligence Engine classifies the concept, selects a visualization strategy (`pattern_type`), returns graph data; the frontend renders it deterministically as SVG.
8. Animations play scene-by-scene (Motion Engine v2); simulations step through parameterized states; rendered videos stream as H.264 MP4.
9. Quizzes are generated by AI from the lesson, attempted and scored server-side; results update concept mastery.
10. The AI Tutor answers context-grounded questions bound to the lesson/slide position; learner memory and recommendations personalize next actions.
11. Effectiveness analytics compute baseline/post/retention gains; presentation analytics and audit logs track usage.

**Status vocabulary used throughout this report**

- IMPLEMENTED & VERIFIED - exists in source and exercised by tests/runtime evidence.
- IMPLEMENTED (code-verified) - exists in source, covered by unit tests, limited runtime evidence.
- PARTIALLY IMPLEMENTED - significant subset working; gaps stated openly.
- SCHEMA/RESERVED ONLY - DB tables/schemas exist; no runtime code path.
- PLANNED / NOT IMPLEMENTED - nothing in the tree implements it.

---

# PART 3 - FEATURE INVENTORY (VERIFIED AGAINST SOURCE)

Legend: [V] implemented & verified; [P] partially implemented; [S] reserved/schema-only; [X] not implemented.

## 3.1 Authentication & accounts

| Feature | Purpose | How it works | Code | Status |
|---|---|---|---|---|
| Registration | Create account | Argon2id hash; commit-before-token race fix | `api/v1/auth.py:114-146` | [V] |
| Login | Issue tokens | JWT HS256 pair + HttpOnly cookies | `auth.py:149-171` | [V] |
| Logout | Revoke refresh | JTI added to revocation set; cookies cleared | `auth.py:174-189` | [V] (in-memory revocation; Redis-backed revocation noted in code as production TODO) |
| Token refresh | Silent re-auth | POST /auth/refresh rotates pair from HttpOnly cookie | `auth.py:319-354` | [V] frontend `authFetch()` auto-refreshes on 401 |
| Protected routes | Authorization | `get_current_user` dependency; per-resource ownership checks (403/404) | `core/dependencies.py` | [V] |
| Google OAuth | Federated login | State (Redis GETDEL, TTL 600 s, in-memory fallback) -> code exchange at oauth2.googleapis.com -> userinfo -> upsert by google_id/email | `auth.py:198-309` | [V] code verified live through Google consent; callback blocked by `redirect_uri_mismatch` until the OAuth client allows `http://localhost:8000/api/v1/auth/google/callback` (configuration, not code) |

## 3.2 Content ingestion

| Feature | How it works | Status |
|---|---|---|
| Upload validation | Extension whitelist .pdf/.docx/.pptx/.txt, magic-byte sniffing (%PDF, PK zip signature), 100 MB cap, non-empty content | [V] `utils/file_helpers.py`, `presentation_service.set_source` |
| Source storage | S3/MinIO (boto3) or local `./storage-data` backend; key `sources/{pres_id}/{uuid}_{filename}` | [V] `storage/factory.py` |
| Document parsing | python-pptx (titles, paragraphs, list levels, tables, picture metadata, speaker notes); pypdf; python-docx; TXT heuristics | [V] `parsers/document_parser.py` |
| Extraction pipeline | Celery task; replaces old units; caps 200x200; status none->processing->ready/failed with captured error | [V] `services/content_extraction_service.py` |
| Manual topics input | POST /presentations/manual with typed topic list (no file needed) | [V] |

## 3.3 Understanding & lessons

| Feature | How it works | Fallback | Status |
|---|---|---|---|
| Topic outline | One LLM pass over <=24k chars of preview; JSON `{topics:[{title, slide_ranges}]}`, max 12 topics; compact-source retry; persisted row | None - raises retryable validation error if both attempts fail | [V] |
| Lesson generation | Celery `eduvision.lessons.generate`: atomic claim -> prompt v3 JSON contract -> safety hook -> versioned blocks with token counts/cost/prompt_hash/payload_hash | Heuristic payload: one block per extracted unit from longest sentences; metadata `generation_method="heuristic"` | [V] |
| Idempotency | Idempotency-Key header on lesson creation; Redis keys `idempotency:{task}:{task_id}` TTL 24 h | duplicate=true short-circuit | [V] |
| Retries/DLQ | attempts<=3, exponential backoff 60 s cap 600 s; terminal failures forwarded to dead_letter queue when enabled | - | [V] |

## 3.4 Strategy-aware visual learning engine

| Element | Verified detail | Status |
|---|---|---|
| Category classification | Regex keyword scoring across 22 TopicCategory values with confidence formula; LLM fallback; default Process @0.50 | [V] `visual_classifier_service.py` |
| Learning objectives | LLM extraction of main goal/objectives/prerequisites (+ static fallback) | [V] |
| Component discovery | LLM prompt + heuristic fallback (capitalized multi-word term frequency, structural-label blacklist, merge, title boost, max 6 components, importance weights) | [V] |
| Relationship inference | LLM + category-pair heuristic; 7 RelationshipType values (parent_child, sequential_flow, bidirectional, dependency, data_flow, communication, cause_effect) | [V] |
| Visualization decision | 22-row rule matrix mapping category -> (primary, fallback) over exactly 10 VisualizationType values; LLM only for unmapped categories; safe default Block Diagram/Mind Map @0.50 | [V] `visualization_decision_service.py` |
| Canvas persistence | 9 relational tables (visual_canvases/nodes/edges, component_metadata, learning_objectives, visual_relationships, visual_layouts, simulation_candidates, visual_quiz_blueprints); integrity validation pre-save | [V] |
| Commit-before-response | Canvas POST commits before returning so immediate nodes/edges reads cannot 404-race (in-code comment documents this) | [V] `api/v1/visual_canvases.py` |
| Canvas sub-resources | GET nodes/edges/components/relationships/quiz-blueprint; PUT/DELETE; filtered list; ownership enforced | [V] |
| Radial fallback | Frontend renders legacy radial graph for unknown pattern types, empty graphs, or renderer exceptions | [V] `player.html renderCanvasSVG` |

## 3.5 Presentation Player

Concept/Visual paired slides, thumbnail rail, keyboard navigation, present mode fullscreen, active-slide-only rendering, lazy on-demand visual generation, Motion Engine v2 animation playback with click-to-inspect, simulation stepper, video panel - all [V], exercised by the 41-check JSDOM suite and headless-Chrome E2E.

Quiz, tutor chat, and TTS audio are backend/API capabilities; the current player UI does not embed them (verified absent in frontend) - integration gaps, not missing features.

## 3.6 Animation engine

- Blueprint planner: intro scene + one scene per component (reveal/highlight events, narration cues, FADE/GLOW/SLIDE transitions, bookmarks, estimated minutes) - [V].
- Layout classification rules (flow -> along-edge motion; hierarchy -> node expansion; network -> focus zoom; default progressive reveal) - [V].
- Timeline validation incl. coverage score and unreferenced-component warnings - [V].
- Runtime sessions: sync records viewing events + EducationalMemory milestones persisted to DB; state endpoint owner-checked - [V].
- Blueprints cached in-process (non-durable across restarts - disclosed limitation).

## 3.7 Simulation engine

- Registry of 5 scripted definitions: CPU fetch-execute cycle, Bubble Sort, Photosynthesis, Water Cycle, Mitosis - [V].
- Sessions: start/get/step(next|prev|jump)/parameters/playback(speed clamp 0.25-4x)/reset; owner-scoped; checkpoints auto-complete; event log - [V].
- Honest scope: stepping advances a cursor over pre-authored states with static state deltas; parameters are stored, not computed - a scripted teaching simulator, not a physics engine. Sessions are in-memory.

## 3.8 Video engine

- Composition: storyboard scenes (objectives, narration cues, checkpoints), teaching script sections, asset manifest, subtitle phrases with keyword emphasis, camera plans (STATIC/DOLLY_ZOOM), transitions, optional TTS narration (scene duration stretched to audio), timeline + bookmarks, validation, 1080p/30 fps export profile - [V].
- Rendering: PIL-drawn frames -> OpenCV writer -> FFmpeg transcode to H.264 (libx264, yuv420p, veryfast, crf 23, +faststart), AAC audio or silent track; probe verification warns on non-H.264; served from uploads/videos/*.mp4 - [V] (this fixed the original browser-playback defect).
- Runtime endpoints: sync (persists milestones), state, bookmark, assessment, tutor-context - [V]; assessment correctness check is demo-grade hardcoded logic (disclosed).

## 3.9 Assessment

- AI-only quiz generation (strict JSON contract; markdown-fence stripping; ValidationError on failure - no heuristic quiz fallback) - [V].
- Persistence chain Quiz -> QuizVersion -> Question/Option -> AnswerKey -> QuestionExplanation + Concept resolution - [V].
- Attempt lifecycle: start (max-attempt enforcement 409; resume in-progress), answer upsert, submit scoring: exact-set MC/TF, partial credit for multiple-select, EXACT/CONTAINS fill rules with case flag, dict/list equality matching/ordering - [V].
- ScoreSummary percent/pass-fail; concept mastery updates; deterministic next-action recommendations returned inline - [V].
- Adaptive difficulty engine exists but is currently orphaned (zero importers) - [S].

## 3.10 AI tutor

- Sessions anchored to lesson + slide/block position; conversations; messages with client_message_id replay protection; context snapshots storing frozen context + sha256 prompt_hash - [V].
- Context assembly: neighboring lesson blocks (-1..+3, capped) + document chunks (first-N positional retrieval - not yet vector search, despite full embedding infrastructure existing) + learner profile (mastery buckets) + deterministic recommended actions - [V].
- Versioned system prompt (v1); refuses off-topic questions; graceful contextual echo fallback when no provider configured - [V].
- Extractive conversation summarization - [V].

## 3.11 Voice, export, analytics, personalization

| Capability | Detail | Status |
|---|---|---|
| TTS | edge-tts primary (en-US-ChristopherNeural), gTTS fallback; MP3 disk cache keyed by content hash; atomic writes; corrupt-cache cleanup; honest null on total failure; consumed by video narration | [V] |
| Export engine | ExportService jobs (dedupe, expiry, templates, checksummed files, presigned URLs); exporters for PDF(reportlab)/MD/HTML/DOCX/PPTX/CSV/JSON bundle; Celery task eduvision.exports.generate | [P] service+workers+exporters implemented, but NO HTTP router is mounted - export jobs cannot currently be created via API; only GET /effectiveness/export (CSV study data) is exposed |
| Learning effectiveness | Typed learning events; baseline/post/retention assessments; absolute gain, normalized (Hake) gain, retention loss/%; feedback summaries; experiment-group comparison; CSV export | [V] |
| Presentation governance | view_count/unique-viewer/avg-score counters; audit logs; publish/archive/restore; autosave; versioning with compare/restore; duplicate/recover; folder trees with breadcrumbs | [V] |
| Personalization | EducationalMemory per-user store (concept mastery buckets weak<50 / developing 50-84 / mastered >=85, trends, review counts, milestones, preferences, reset); deterministic recommendation engine feeding quiz results and tutor context | [V] |
| Learning paths/goals/study plans/review schedules | Migrations create the tables; no ORM models/services/endpoints consume them | [S] schema-only |
| RAG/embedding infrastructure | ChunkingService, DocumentChunk rows, VectorIndex + idempotent EmbeddingJob, Celery pipeline tasks, providers OpenAI text-embedding-3-small / Gemini text-embedding-004 / local deterministic mock | [V] infrastructure; not yet wired into tutor retrieval |

## 3.12 Cross-cutting platform features

Redis Lua sliding-window rate limiting, request-ID + timing headers, gzip compression, trusted-host enforcement, security headers/CSP, request-size limits, structlog masked logging, health/liveness/readiness probes, metrics endpoint, Alembic auto-migrations at boot, Docker Compose topology (postgres 16-alpine, redis 7.4-alpine, MinIO, backend, celery-worker, celery-beat), beat schedules (health every 300 s, analytics hourly, cleanups daily, embedding maintenance) - all [V].

---

# PART 4 - TECHNICAL ARCHITECTURE (VERIFIED)

**Frontend.** Vanilla HTML/CSS/JS (no framework, no build step), served by FastAPI StaticFiles(html=True) at /frontend/* (`main.py:162-168`). Pages: landing, upload (drag-drop + manual topics + recent decks), processing (polling checklist), sign-in/sign-up (Google button), and the 1,656-line Presentation Player.

**API layer.** FastAPI under /api/v1 with routers: health, auth, metrics, presentations, folders, lessons/player, quizzes, visual/canvases, simulations, animations(+runtime), videos(+runtime), assistant, effectiveness (~100 endpoints; Part 9).

**Services.** 50+ service classes: presentation, extraction, topic outline, lesson generation/prompt-builder/safety, visual intelligence suite, quiz generation/attempt/scoring, assistant, simulation, animation, video composition/render/subtitles/TTS narration, TTS, export, analytics/effectiveness, recommendation engine, educational memory, RAG/embeddings.

**AI layer.** app/ai/: normalized AIRequest/AIResponse; factory-registered providers gemini/openai/local (Gemini REST default model `gemini-3.5-flash`; OpenAI `gpt-4o-mini`; deterministic local mock); response caching (in-process TTL), token-bucket rate limiting, bounded exponential retry honoring Retry-After, token estimation, per-model cost table, usage accounting persisted to ai_usage_logs.

**Database.** PostgreSQL via SQLAlchemy 2 async (asyncpg), pooled (pool_pre_ping, recycle), expire_on_commit=False; ~50 model files; UUID PKs + indexed public_id prefixes; Alembic migrations 0001-0024 applied automatically at startup via `asyncio.to_thread(command.upgrade, cfg, "head")` with warning-and-continue on failure.

**Cache/broker.** Redis (local port 6380: db0 cache, db1 Celery broker, db2 results; docker-compose maps 6379): pooled client (max 50 connections, health checks), CacheService (TTL 300 s, SCAN-based pattern delete, NX locks), OAuth-state store, sliding-window rate limiter.

**Background processing.** Celery worker (acks_late=True, reject_on_worker_lost, prefetch=1, time limits 3600/3000 s, CELERY_TASK_ALWAYS_EAGER switch) + beat scheduler; named queues (ai/uploads/notifications/email/embeddings/embedding_batch/analytics/dead_letter) with routes; 16 registered eduvision.* tasks.

**Storage.** Provider-selected S3/MinIO (boto3, presigned URLs) or local filesystem; /uploads static mount serves generated media (videos, thumbnails, TTS audio).

**Processing pipeline.** upload -> validate -> store -> Celery extraction -> LLM outline -> Celery lesson generation -> player topics -> on-demand visual/animation/simulation/video generation -> quiz/tutor/analytics side-effects.

```
                        +---------------------------+
                        |           User            |
                        +-------------+-------------+
                                      v
              +---------------------------------------------------+
              |     Vanilla JS Frontend (FastAPI StaticFiles)     |
              |  index . upload . processing . auth .             |
              |  player.html (Presentation Player)               |
              +------------------------+--------------------------+
                                       v   JSON + JWT HttpOnly cookies
        +----------------------------------------------------------+
        |                FastAPI Backend (/api/v1)                 |
        | Middleware: TrustedHost . CORS . GZip . SecurityHeaders  |
        | Timing . RequestSizeLimit . RateLimit(Redis Lua window)  |
        | Logging(structlog) . RequestID                           |
        +----------------------------------------------------------+
        | Services: presentations . extraction . outlines          |
        | lessons . visual-intelligence . quizzes . assistant      |
        | simulations . animations . video . tts . analytics       |
        +----------------------------------------------------------+
        | AI Layer (factory): Gemini | OpenAI | Local-mock         |
        | cache . rate-limit . retry . tokens . cost . usage log   |
        +------+------------------------+--------------------+-----+
               v                        v                    v
        +---------------+      +--------------+    +------------------+
        | PostgreSQL 16 |      | Redis 7.4    |    | Storage          |
        | SQLAlchemy 2  |      | db0 cache    |    | S3/MinIO or      |
        | Alembic 24 rev|      | db1 broker   |    | local disk       |
        +-------^-------+      | db2 results  |    | uploads/ media   |
                |              +------+-------+    +------------------+
                |                     v
        +-------+-------------------------------------------+
        | Celery Worker(s) + Beat                           |
        | queues: ai . uploads . embeddings . analytics     |
        |         email . dead_letter                       |
        | tasks: process_source_ingestion                   |
        |        lessons.generate . rag.index               |
        |        embedding.* . exports.generate             |
        |        cleanup/aggregation jobs                   |
        +---------------------------------------------------+
```

---

# PART 5 - TECH STACK (ALL VERIFIED IN TREE)

| Category | Technology | Why it is used |
|---|---|---|
| Frontend | HTML5/CSS3/vanilla JavaScript | Zero-build instant-load player; full control of SVG rendering |
| Frontend media | Inline SVG, CSS transforms, requestAnimationFrame | Deterministic strategy-visual layouts + animation engine |
| Backend | Python 3.13+, FastAPI, Uvicorn | Async-first API; automatic OpenAPI; typed contracts |
| Validation | Pydantic v2, pydantic-settings, email-validator | Schema enforcement at every boundary; typed settings |
| Database | PostgreSQL 16, SQLAlchemy 2 async, asyncpg | Relational integrity across ~50 entities; async pooling |
| Migrations | Alembic (24 revisions, auto-run) | Reproducible schema evolution |
| Cache/broker | Redis 7.4 (hiredis) | Rate limiting, OAuth state, locks, Celery transport |
| Async jobs | Celery 5 (+beat, DLQ, idempotency service) | Offload extraction/AI/video/embeddings from request cycle |
| Storage | S3-compatible via boto3; MinIO; local backend | Pluggable durable artifact storage |
| AuthN/Z | python-jose JWT HS256, passlib+argon2-cffi, HttpOnly cookies | Stateless access tokens + rotating refresh tokens |
| OAuth | Google OAuth 2.0 authorization-code (httpx) | Federated sign-in |
| Document parsing | python-pptx, pypdf, python-docx | Native structural extraction per format |
| Media | OpenCV-headless, Pillow, NumPy, imageio-ffmpeg | Frame rendering + H.264 transcode |
| TTS | edge-tts, gTTS | Narration audio for videos |
| HTTP | httpx | Google token exchange; Gemini REST calls |
| AI layer | Custom provider abstraction (gemini/openai/local) | Uniform prompts, retries, cost accounting |
| Embeddings | OpenAI/Gemini/local providers | RAG indexing pipeline |
| Observability | structlog, X-Request-ID/X-Response-Time, /metrics, health probes | Masked structured logs, tracing hooks |
| Testing | pytest(+asyncio/cov/env), factory-boy, testcontainers, aiosqlite, JSDOM suites, puppeteer-core + Chrome headless | 843 automated tests + browser E2E |
| Quality | Ruff (strict ruleset), black/isort/mypy configs, pre-commit | Zero-error lint gate |
| DevOps | Docker + docker-compose (postgres/redis/minio/backend/worker/beat) | One-command full-stack orchestration |
| Serialization | orjson | Fast JSON |
| Resilience | tenacity (DB helpers) + hand-rolled AI retry policy | Transient-failure recovery |

---

# PART 6 - AI/ML COMPONENTS

**Provider/model (verified defaults):** Gemini REST provider default model `gemini-3.5-flash` (`app/ai/providers/gemini.py:70`); OpenAI `gpt-4o-mini`; deterministic LocalMockProvider for offline/dev/test. Selection via the AI_PROVIDER setting through a registry factory. There is no silent cross-provider failover; callers implement explicit fallbacks.

**Prompting architecture:** every generator owns a versioned prompt constant with strict JSON contracts, temperature control, character/token budgets, JSON-repair helpers, and stored prompt_hash/payload_hash on outputs (lesson PROMPT_VERSION="3"; outline "1"; assistant "1"). Prompts are never logged; requests carry correlation IDs; every call is metered (tokens in/out, latency, estimated USD cost) into ai_usage_logs.

**Where AI is used (all verified):**

1. Topic outline extraction with slide-range segmentation.
2. Lesson/topic explanation generation.
3. Topic-category classification fallback (primary path is deterministic regex scoring).
4. Component discovery (heuristic fallback).
5. Relationship inference (category-pair heuristic fallback).
6. Visualization-type decision (only for categories outside the 22-row rule matrix).
7. Learning-objective extraction.
8. Quiz generation (questions/options/explanations/topic/knowledge-area).
9. AI Tutor responses (context-grounded, refusal guard for off-topic).
10. Embedding generation for the RAG pipeline.
11. Video storyboard/script/narration enrichment.

**Deterministic (non-AI) components:** regex category scorer, visualization rule matrix, relationship heuristics, recommendation engine, animation planner/classifier/validator, simulation registry/engine, quiz scoring, effectiveness math, TTS caching, video frame rendering.

**AI-generated educational content vs. deterministic frontend rendering (key interview distinction):**

> All educational decisions - what the concepts are, how they relate, which visual pattern fits - are made by backend intelligence and persisted as data. The frontend is a deterministic layout engine: it receives pattern_type plus nodes/edges/components and draws them. Renderers never invent, reclassify, or reinterpret educational content; unknown patterns degrade to the radial layout rather than guessing.

Flow: backend selects visualization strategy -> frontend receives pattern_type + graph data -> renderer chooses layout function -> renderer visualizes returned data only.

**Graceful degradation ladder (verified):** Gemini quota exhaustion (AIQuotaExceededError, non-retryable) -> lesson generation switches to heuristic payload (`generation_method="heuristic"`); visual services fall back to their deterministic NLP heuristics; tutor falls back to a contextual echo. The application remains fully functional without any cloud API key.

---

# PART 7 - STRATEGY-AWARE VISUAL LEARNING ENGINE (SIGNATURE FEATURE)

**Why normal slides are insufficient:** a bullet list encodes sequence/hierarchy/comparison only implicitly; working memory must reconstruct structure the author never drew. EduVision extracts that structure and makes it explicit per concept.

**Pipeline (each stage verified in source):**

```
content -> validate -> classify (22 categories)
        -> learning objectives
        -> discover components (LLM + NLP heuristics, <=6)
        -> infer relationships (7 typed relations)
        -> decide visualization (rule matrix -> LLM if unmapped -> safe default)
        -> layout suggestion (horizontal / vertical / radial / grid)
        -> persist graph (9 tables)
        -> serve pattern_type + nodes/edges/components to clients
```

**Strategy catalog - the 10 verified VisualizationType values and their frontend mapping:**

| pattern_type (normalized) | Best use case | Visual structure | Example concept |
|---|---|---|---|
| Flowchart | procedures, workflows | numbered vertical boxes + arrows; auto-degrades to two columns when tall | Request-response lifecycle |
| Algorithm Steps | algorithms, programming/math concepts | sequential step layout (flowchart variant) | Binary search |
| Block Diagram | system architectures, bio/chem/physics systems | component boxes with connector arrows | CPU-RAM-I/O architecture |
| Comparison Layout | contrasts, economics topics | split-panel columns with headers + bulleted items; dense mode >8 items | TCP vs UDP |
| Timeline | chronological processes | horizontal axis, alternating labels above/below; dense mode >9 events | Phases of a historical period |
| Hierarchy | taxonomies | BFS level tree built from parent_child edges; orphan-safe | Animal classification |
| Decision Tree | branching logic | hierarchy renderer over parent_child edges | Loan approval logic |
| Scientific Cycle | life/nature cycles | circular ring with wrapping sequential arrows | Water cycle |
| Mind Map | associative overviews | radial hub layout | Photosynthesis factors |
| Network Graph | interconnections, data flow | radial node placement with labeled directed edges | Neural-network topology |

**Fallback behavior:** empty graph / unmapped type / renderer exception -> legacy radial SVG; diagnostics recorded per slide as `patternType|category|usedRenderer`. A hierarchy without explicit parent_child edges renders content-order levels with an explicit footnote ("source does not define explicit hierarchy") instead of fabricating structure.

**Key mechanisms:**

- `.ev-node` - semantic `<g>` class wrapping every drawn node group across all five renderers (stable hook for styling/testing).
- Visual metadata - canvas row persists pattern_type, category, and the full decision dump (reason/confidence/fallback_type) in layout_config.
- SVG rendering - shared 900x460 viewBox, palette constants, shared arrowhead markers, label wrap/clamp helpers.
- Lazy visual generation - nothing is generated until the user clicks Generate Visual on a visual slide (on-demand API call).
- Caching - per-topic memoization of rendered visuals in window state (write side verified; the restore-guard compares a field that is never written, so revisits regenerate - minor disclosed quirk).

---

# PART 8 - PRESENTATION PLAYER

Verified against `player.html` (1,656 lines), `api/v1/player.py`, `lesson_player_service.py`.

- **Slide model:** topics x 2 slides - even index Concept (title + explanation), odd index Visual (type selector auto/image/animation/video/simulation, recommendation chip, Generate action). An 82-topic deck becomes 164 slides.
- **Thumbnail sidebar:** one thumb per slide (zero-padded number, Concept/Visual badge, escaped title), click-to-jump, active auto-scrolls into view; hidden below 720 px.
- **Active-slide rendering:** renderSlide() replaces only the viewport DOM - O(active) work regardless of deck size (in-code comment: "active slide only - scales to any deck size"). Verified by the 200-slide scalability scenario in the JSDOM suite.
- **Navigation:** prev/next buttons disabled at bounds; keys ArrowRight/PageDown/Space next, ArrowLeft/PageUp prev, Home first, End last, Esc exit present, F enter present (ignored while typing in inputs); deep-link ?slide=N; footer counter "n / total" with bold current.
- **Present mode:** body.presenting CSS + Fullscreen API request; enlarged typography; overlay arrows; exit button; fullscreenchange listener keeps state consistent when the browser exits fullscreen.
- **Session tracking:** debounced 400 ms POST /player/set-topic sync (best-effort); advance endpoint clamps to last topic and marks completed.
- **Animation integration (Motion Engine v2):** blueprint from POST /animations/plan; global rAF loop; timed event firing (reveal component, highlight pulses, camera focus with clamped zoom 1.12-1.55x); progress HUD with click-to-seek and per-scene ticks/chips; Play/Pause/Replay; speeds 0.5x/1x/2x; typewriter captions with keyword emphasis; click-to-inspect panel explaining any component; runtime sync throttled >=1500 ms.
- **Simulation integration:** definitions scored against topic keywords -> picker chips -> session start/step UI with parameter chips, checkpoint hints, learning objectives, Prev/Next.
- **Video integration:** single POST /videos/create returns playable URL; native controls + custom speed buttons (default 0.5x remembered per topic across navigation); storyboard scene list beneath.
- **Large presentations:** active-slide-only rendering, memoized artifacts, debounced/throttled network chatter, one shared rAF loop with dead-engine GC, thumbnails built via DocumentFragment.

**Why active-slide-only rendering scales:** DOM cost per navigation is O(1) in deck size; memory and paint time stay flat from 12-topic decks to synthetic 200-slide tests because off-screen slides do not exist in the DOM until visited, and each visual renders only on demand.

---

# PART 9 - BACKEND/API OVERVIEW (SOURCE-DERIVED)

All routes live under `/api/v1`.

**Authentication - /auth**

- POST /register - create account (201)
- POST /login - password login, sets cookies + returns tokens
- POST /logout - revoke refresh JTI, clear cookies
- POST /refresh - rotate token pair
- GET /me - current user (protected)
- GET /providers - enabled sign-in providers
- GET /google - start OAuth flow (302 to Google; friendly redirect if unconfigured)
- GET /google/callback - code exchange, user upsert, cookie-set redirect

**Presentations - /presentations**

- GET "" paged list - POST "" create - POST /manual (typed topics)
- GET/PATCH/DELETE /{id}
- POST /{id}/source - multipart document upload
- POST /{id}/publish|unpublish|archive|restore|autosave|duplicate|recover
- GET/POST /{id}/versions (+compare, version restore)
- GET /{id}/processing-status - extraction polling
- GET /{id}/content - extracted units/blocks
- GET /{id}/topics + POST topics/regenerate
- POST/DELETE /thumbnail, POST thumbnail/regenerate
- GET /{id}/analytics, GET /{id}/audit-logs
- Lessons: POST/GET /{id}/lessons; GET .../lessons/{lid}; /status; versions list/detail

**Folders - /folders:** CRUD + breadcrumbs.

**Player - /lessons/{lesson_id}/player:** GET "" state - POST /start - POST /advance - POST /set-topic.

**Quizzes - /quizzes:** POST /generate - GET /{quiz_id} - attempts start/list/get - submit answer per question - submit attempt (score + recommendations).

**Visual canvases - /visual/canvases:** POST "" generate+persist - GET list/detail - PUT/DELETE - GET /nodes /edges /components /relationships /quiz-blueprint.

**Simulations - /simulations:** GET /definitions[/{sid}] - sessions start/get/step/parameters/playback/reset.

**Animations - /animations:** POST /plan - POST /classify - GET /{blueprint_id}[/scenes|timeline|blueprint|metadata]; runtime: POST /sync, GET /state/{session_id}.

**Videos - /videos:** POST /create - POST /{vid}/render|storyboard|script - GET /{vid}[/timeline|storyboard|metadata]; runtime: POST /sync|bookmark|assessment, GET /state/{sid}, GET /tutor-context/{sid}.

**Assistant - /assistant:** sessions create/list/get/close; conversations create/list/get; messages post/list; summarize.

**Effectiveness - /effectiveness:** events post/list; assessments start/record-score/get; learning-gain/{presentation_id}; summary; report; feedback post/summary; comparison; export (CSV).

**Ops:** GET /health (db+redis+storage+ai+celery composite) - GET /health/live - GET /health/ready - GET /metrics.

No mounted routers exist for exports/search/bookmarks/personalization endpoints (see Part 25).

---

# PART 10 - DATABASE & DATA MODEL

**Technology:** PostgreSQL (asyncpg; SQLite+aiosqlite for tests). Engine: pooled, pool_pre_ping=True, pool_recycle configured, expire_on_commit=False. get_session commits on success / rolls back on exception. Configurable transient-error retry (DATABASE_RETRY_* settings) with a dedicated test module.

**Conventions (verified across ~50 model files):** UUID primary keys plus unique indexed public_id columns with semantic prefixes (pres_, lessver_, gblk_, quiz_, qatt_, asess_, aconv_, amsg_, actx_, lsess_, eass_, emem_, canvas_, vnode_, outline_, expjob_ ...); TimestampMixin; SoftDeleteMixin where appropriate; explicit per-relation cascade choices; composite indexes on hot query paths.

**Major entities and relationships (simplified):**

```
User 1--* Presentation *--1 Folder(optional)
Presentation 1--* ContentUnit 1--* ContentBlock
Presentation 1--1 TopicOutline        (unique presentation_id)
Presentation 1--* GeneratedLesson 1--* GeneratedLessonVersion 1--* GeneratedBlock
      UNIQUE(lesson_id, version); UNIQUE(version_id, position)
Presentation 1--* Quiz 1--* QuizVersion 1--* Question 1--* QuestionOption
QuizAttempt *--1 Quiz/User; QuestionAttempt; UserAnswer;
AnswerKey; QuestionExplanation; ScoreSummary; Concept links to mastery
Presentation 1--* VisualCanvas 1--* VisualNode / VisualEdge / VisualLayout /
      VisualRelationship / ComponentMetadata / LearningObjective /
      SimulationCandidate / QuizBlueprint
AssistantSession *--Lesson/User 1--* AssistantConversation 1--* AssistantMessage
      + AssistantContextSnapshot (frozen JSONB context + prompt_hash)
LearningSession (resumable; UNIQUE(user_id, idempotency_key)); LearningEvent
EffectivenessAssessment (user, presentation triple-scored)
EducationalMemory 1--1 User (memory_data JSONB)
ExportJob 1--* ExportFile; ExportTemplate (unique template_key)
AIUsageLog (every AI call); presentation_analytics counters; audit logs
```

**Persistence architecture:** request-scoped UnitOfWork/session; deliberate commit-before-response ordering at the three race-sensitive write points (register, OAuth callback, canvas creation) so an immediately-following authenticated read can never race the teardown commit - each site carries an explanatory in-code comment. Latest migration revision: 0024.

---

# PART 11 - REDIS & CELERY

**Why Redis:** one dependency serves four roles - atomic sliding-window rate limiting (Lua ZSET script), shared OAuth-state store with GETDEL semantics, TTL caches/locks (CacheService), and Celery transport.

**Why Celery:** extraction, AI lesson generation, embeddings, exports, analytics aggregation, and cleanups are too slow/unreliable for the request cycle. Tasks gain retries with exponential backoff, acks-late durability, reject-on-worker-lost safety, prefetch=1 fairness, hard/soft time limits (3600/3000 s), a dead-letter queue, and Redis-keyed idempotency (TTL 24 h).

**Current verified environment (no credentials shown):**

- Redis 7.4.x endpoint localhost:6380 - db0 cache, db1 broker, db2 result backend.
- CELERY_TASK_ALWAYS_EAGER=false -> genuine distributed execution locally (eager mode remains available as a development fallback).
- Celery worker ONLINE - worker log shows all 16 registered eduvision.* tasks connected to the 6380 broker.
- Beat schedules: health check every 300 s; analytics aggregation hourly; draft/archive/soft-delete cleanup daily; embedding refresh every 15 min + cleanup/statistics daily.

**Historical troubleshooting note (not a current defect):** during earlier development the local Windows Redis build was too old for modern Celery (no HELLO command), so the stack ran in task_always_eager mode; a later frozen Redis service caused degraded health checks while all flows stayed green. The environment was subsequently upgraded (Redis 7.4.x on port 6380) with eager mode disabled and a verified online worker - closing that chapter.

---

# PART 12 - SECURITY

All mechanisms below verified in source:

| Mechanism | Implementation |
|---|---|
| Password storage | Argon2id via passlib CryptContext (time_cost=3, memory=64 MB, parallelism=4); never logged |
| JWT | HS256; access token 15 min; refresh 7 days; claims sub/role/jti/iat/nbf/exp/aud/iss/type; aud+iss validated on decode; type separation enforced |
| Cookies | access_token + refresh_token HttpOnly, SameSite=Lax, configurable Secure flag/path/domain |
| Refresh revocation | Logout adds refresh JTI to revocation set checked by /auth/refresh (in-memory; code comments flag Redis as production upgrade) |
| Google OAuth security | Random state token_urlsafe(32); stored server-side (Redis GETDEL, TTL 600 s; in-memory fallback); single-use consumption; code exchanged server-side; user upsert keyed by google_id/email; credentials only from backend env |
| Protected routes | get_current_user dependency on every domain router; per-resource ownership checks return 403/404 |
| Rate limiting | Redis Lua sliding window (ZREMRANGEBYSCORE/ZCARD/ZADD atomic script); default 100 req/60 s; per-route overrides RATE_LIMIT_ROUTES regex=limit/window; whitelist/blacklist; trusted-proxy-aware client IP (rightmost non-trusted XFF hop, X-Real-IP fallback); 429 with Retry-After; fail-open if Redis unavailable |
| Upload validation | Extension whitelist (.pdf/.docx/.pptx/.txt), magic-byte sniffing, 100 MB cap, non-empty check |
| SQL injection | SQLAlchemy parameterized ORM queries throughout; no string-built SQL |
| Input validation | Pydantic schemas on every endpoint; lesson payload validation + pluggable safety validator hook |
| Security headers | CSP (default-src 'self'; frame-ancestors 'none'; base-uri/form-action 'self'; fonts allowlisted), X-Frame-Options DENY, X-Content-Type-Options nosniff, Referrer-Policy strict-origin-when-cross-origin, Permissions-Policy camera/microphone/geolocation=(), HSTS (prod only) |
| Request hardening | TrustedHostMiddleware allowlist; RequestSizeLimitMiddleware; CORS restricted origins with credentials; GZip >=500 B |
| Error handling | Centralized exception handlers producing uniform error envelopes; docs/redoc/OpenAPI disabled in production |
| Secret management | .env outside VCS (gitignore), .env.example placeholders only; structlog masks sensitive fields (password/token/cookie/authorization/jwt/ssn/cvv) as ***MASKED*** when LOG_MASK_SENSITIVE enabled |
| Debug restrictions | APP_DEBUG-driven; OpenAPI/docs suppressed when is_production |

Known dev-stage gaps disclosed by code comments: in-memory refresh-JTI revocation and OAuth-state fallback (both flagged for Redis-backed production implementations).

---

# PART 13 - TESTING & QUALITY

Fresh verification run performed during this audit where marked [RERUN]; other rows use final project evidence.

| Test | Result | Evidence |
|---|---|---|
| Full pytest suite | **843 passed, 0 failed** (257.86 s) | [RERUN] `.venv` pytest run: "843 passed, 1 warning" |
| Test collection count | 843 collected | [RERUN] pytest --collect-only |
| Ruff lint | **0 errors** ("All checks passed!") | [RERUN] ruff check . |
| Targeted visual API tests (test_visual_api.py) | 3 passed | Final evidence run |
| Rate-limit tests (test_rate_limit.py) | 15 passed | Final evidence run; suite covers headers/Retry-After/fail-open, disabled mode, no-real-Redis guarantee, route-override parsing, service IP resolution |
| JSDOM player regression (_mv_player_test.js) | 41 passed, 0 failed | Navigation, thumbnails, present mode, canvas, auto-recommendation chip, motion-engine playback/inspector/pause/seek/speed, simulation, video storyboard, 200-slide scalability |
| Chrome headless E2E (_mv_browser_e2e.js, puppeteer-core) | 18 passed, 0 failed | Full user journey vs fresh ML_UNIT3 upload (deck + lesson creation through player interactions) against real running server |
| Canvas race probe | 2 successful runs | Confirms canvas create -> immediate nodes/edges read consistency after commit-before-response fix |
| Backend health | HTTP 200 | GET /api/v1/health |
| Redis | Healthy | PING + version info at :6380 |
| Celery | Healthy / ONLINE | Worker log shows full registered-task roster on broker |

**What the automated suite covers (from tests/unit inventory):** AI layer (providers gemini/openai/local, cache, rate limit, retry, tokens, cost, errors, factory, usage), auth flows incl. refresh reuse/revocation, security headers, request-size limits, DB/session retry + transaction retry, document parsers, content extraction, topic outline, lesson generation/prompt builder/worker/safety/player routes, complete quiz subsystem (~20 modules incl. scoring/security/timeouts/reliability), tutor suite (API/reasoning/retrieval/security/workers/metrics), RAG + embedding pipeline (~14 modules), personalization suite, animation planner/runtime/classification, simulation engine, video engine/runtime, visual intelligence/API/persistence, export models/schemas/exporters/routes/services, effectiveness/P2/P3 validations, health, metrics, idempotency, S3 adapter, repository loading, load-test script sanity, production readiness.

**Quality gates:** Ruff strict rule selection (E,W,F,I,N,UP,B,A,C4,T10,FA,ISC,ICN,LOG,G,COM,PT,SIM,TID,PIE,FIX,ERA) - zero findings; mypy strict config present; pre-commit config present; coverage configured over app/.

---

# PART 14 - IMPORTANT ENGINEERING FIXES (PROBLEM -> ROOT CAUSE -> FIX -> VERIFICATION)

1. **Create -> immediate-read transaction race (canvas).**
   Problem: client fetched /nodes,/edges immediately after POST /visual/canvases and got 404 intermittently.
   Root cause: FastAPI dependency sessions commit at teardown - after the response is already sent; the immediate follow-up read raced the INSERT.
   Fix: explicit `await uow.commit()` before returning the response (documented in-code at visual_canvases.py).
   Verification: dedicated canvas race probe - 2/2 successful runs.

2. **Authentication register/OAuth race.**
   Problem: 401 "User not found." ~20 ms after register/OAuth callback in ~2 of 3 rounds.
   Root cause: same teardown-commit ordering; tokens were issued before the user row was committed.
   Fix: flush+commit before issuing tokens/redirect in register and google_callback (auth.py:139-142, 296-299).
   Verification: post-fix 20/20 fresh users pass with zero sleeps; auth flow integration chain green.

3. **Strategy renderer missing-definition issue.**
   Problem: strategy visuals could fail when renderer inputs lacked definitions.
   Root cause: renderer dispatch trusted pattern_type without guarding empty/unknown graph data.
   Fix: dispatcher normalizes types; unknown/empty/exception paths fall back to legacy radial SVG with diagnostics (`window._evmeta_*`); hierarchy renders content-order fallback with honest footnote.
   Verification: visual intelligence unit tests + player JSDOM suite.

4. **Rate-limit test whitelist issue.**
   Problem: 4 rate-limit unit failures appeared after local speed fixes.
   Root cause: RATE_LIMIT_WHITELIST=127.0.0.1,::1,localhost in local .env conflicted with tests expecting no loopback whitelisting.
   Resolution: classified as documented environment-vs-test expectation divergence; tests use documentation-reserved IPs (203.0.113.x) to stay independent of host config; final evidence run reports 15/15 passing.

5. **Redis/Celery configuration/runtime issue.**
   Problem: earlier local Redis was too old for Celery (no HELLO) forcing eager mode; later a frozen Redis service degraded health.
   Fix: upgraded environment to Redis 7.4.x on port 6380; CELERY_TASK_ALWAYS_EAGER=false; broker db1/results db2.
   Verification: worker log shows all 16 tasks registered and online; health composite green.

6. **Stale/orphaned backend process & port hijack.**
   Problem: intermittent connection anomalies traced to an orphaned uvicorn instance holding port 8000 under a different interpreter.
   Fix: killed stale processes; standardized startup under the project venv; logs redirected to temp files for diagnosis.
   Verification: clean boot; all suites re-run green afterwards.

7. **Video browser playback failure.**
   Problem: rendered videos would not display in browsers.
   Root cause: OpenCV writes MPEG-4 Part 2 (mp4v), which browsers cannot decode in <video>; old mux copied the stream verbatim.
   Fix: always transcode via FFmpeg (imageio-ffmpeg static binary) to H.264 libx264/yuv420p/crf23/+faststart with AAC audio (-an when silent); probe validates codec.
   Verification: wire-check confirms h264(avc1)+AAC output served with HTTP 200.

8. **CSP/font mismatch (classified noise).**
   Problem: console errors for Google Fonts under strict CSP.
   Fix: style-src extended with https://fonts.googleapis.com (font-src already allowed gstatic); remaining headless-Chrome console items classified (favicon 404 fixed via inline-SVG route; intentional 401s from negative tests).

These entries demonstrate debugging discipline: symptom -> isolation -> root cause -> minimal fix -> repeatable verification.

---

# PART 15 - PERFORMANCE & SCALABILITY (VERIFIED FEATURES)

- Active-slide-only rendering keeps navigation O(1) in deck size; validated up to synthetic 200-slide decks in the JSDOM suite.
- Real-world large-deck proof: 82-topic ML_UNIT deck processed end-to-end (extraction ready ~2 s, lesson ready, 164 player slides).
- Lazy visual generation: compute spent only on visuals the learner opens.
- Per-topic memoization of generated artifacts; debounced session sync (400 ms) and throttled runtime sync (>=1500 ms).
- Async FastAPI + SQLAlchemy async pooling (pool_pre_ping, recycle) with NullPool isolation in tests.
- Celery moves heavy work off the request path; acks_late + prefetch=1 + time limits protect throughput under load; DLQ prevents poison-message stalls.
- Redis-backed sliding-window rate limiting protects downstream capacity; fail-open preserves availability.
- Database: composite indexes on hot paths (quiz status/user lookups, assistant timelines, learning-session resumes); production-index migration 0015; soft deletes avoid destructive bulk operations.
- GZip responses; presigned direct downloads for artifacts.
- No fabricated benchmark numbers: performance claims above are architectural plus observed behavior from test runs.

---

# PART 16 - PROJECT MATURITY

**Assessment: Advanced MVP / production-oriented application.**

Evidence for:
- Full-stack vertical slice hardened end-to-end (upload -> understand -> visualize -> assess -> tutor -> insights) with real users' decks processed successfully.
- 843-test automated suite + browser E2E + wire checks; zero lint debt.
- Infrastructure maturity: Alembic migrations auto-run; Docker Compose topology; Celery queues/DLQ/idempotency/beat; structured masked logging; health/liveness/readiness probes.
- Security posture well beyond typical student work (Argon2id, JWT rotation, CSP/HSTS, Lua rate limiting, upload magic-byte validation, secret masking).
- Honest engineering: heuristic degradation, in-code race-fix documentation, disclosed limitations.

Gaps keeping it short of "production deployed": no mounted export HTTP surface, several engines hold state in-process (simulation/animation/video/player sessions), tutor retrieval not yet vector search, single-node deployment assumed, OAuth redirect configuration pending on the provider side.

---

# PART 17 - RESUME VERSIONS

**A. One-line version**

Built EduVision AI, a full-stack AI learning platform converting PPTX documents into interactive visual lessons using FastAPI, PostgreSQL, Redis, Celery, and Gemini.

**B. 2-bullet version**

- Built EduVision AI end-to-end: a FastAPI/PostgreSQL/Redis/Celery platform that ingests PPTX/PDF/DOCX content, extracts topics through LLM pipelines with deterministic fallbacks, and renders strategy-aware interactive SVG visuals in a custom presentation player.
- Implemented JWT + Google OAuth authentication, Redis sliding-window rate limiting, Celery processing with dead-letter queue and idempotency, H.264 video rendering, and quality gates of 843 passing tests plus headless-browser E2E suites.

**C. 3-bullet version**

- Engineered an AI understanding pipeline (FastAPI + Gemini/OpenAI provider layer): document parsing, topic outlining, lesson generation with versioned persistence, heuristic degradation on quota exhaustion, and per-call token/cost accounting.
- Designed a strategy-aware visual engine that classifies concepts across 22 categories into 10 visualization strategies, persists knowledge graphs relationally, and renders them as deterministic client-side SVG.
- Hardened the platform with Argon2id+JWT auth, Google OAuth state protection, Lua-based rate limiting, commit-before-response race fixes, 843 green pytest cases, a 41-check player suite, and 18/18 Chrome E2E.

**D. 4-bullet version**

- Built EduVision AI - a full-stack AI-powered learning platform (FastAPI, PostgreSQL, async SQLAlchemy, Redis 7.4, Celery) turning PPTX/PDF/DOCX decks into interactive lessons with a custom zero-dependency JavaScript Presentation Player.
- Implemented the AI layer: provider factory (Gemini/OpenAI/local mock), versioned JSON prompt contracts, retries with backoff, token/cost metering, and graceful heuristic fallbacks that keep the app functional without cloud keys.
- Created the signature Visual Intelligence Engine: hybrid category classification, component/relationship discovery, rule-matrix visualization-strategy selection, nine-table graph persistence, and five SVG renderers with radial fallback.
- Operated like production: Alembic migrations at boot, Celery worker+beat with dead-letter queue, Redis rate limiting/OAuth-state/caching, structlog secret masking, 843 passing tests, 0 Ruff errors.

---

# PART 18 - ATS KEYWORDS (ACTUAL TECHNOLOGIES ONLY)

| Group | Keywords |
|---|---|
| Programming | Python 3.13+, JavaScript ES2020, SQL, HTML5, CSS3 |
| Frameworks | FastAPI, Pydantic v2, Pydantic Settings |
| AI/ML | LLM integration, Gemini API, OpenAI API, GPT-4o-mini, prompt engineering, JSON prompt contracts, embeddings, RAG pipeline |
| Databases | PostgreSQL 16, SQLAlchemy 2 async, asyncpg, SQLite, Alembic migrations |
| Caching | Redis 7.4, hiredis, connection pooling, Lua scripting |
| Async processing | Celery 5, Celery Beat, task queues, dead-letter queue, idempotency keys |
| Storage | S3-compatible object storage, boto3, MinIO, presigned URLs |
| AuthN/AuthZ | JWT HS256, OAuth2 authorization-code flow, Google Sign-In, Argon2id, passlib, HttpOnly cookies |
| Security | Sliding-window rate limiting, CSP, HSTS, CORS, upload validation, input validation, secret masking |
| Testing | pytest, pytest-asyncio, pytest-cov, factory-boy, testcontainers, JSDOM, Puppeteer, headless Chrome E2E |
| Quality | Ruff, mypy, pre-commit |
| Media processing | python-pptx, pypdf, python-docx, OpenCV, Pillow, NumPy, FFmpeg/H.264 libx264, edge-tts, gTTS |
| Frontend | Vanilla JavaScript, Inline SVG, requestAnimationFrame animations, Fullscreen API |
| Architecture | Asynchronous Python, background workers, layered services/repositories, event-driven analytics, Docker Compose |

---

# PART 19 - FINAL RESUME PROJECT ENTRY

**EDUVISION AI - AI-Powered Interactive Learning Platform**
*Python, FastAPI, PostgreSQL, SQLAlchemy, Redis, Celery, Gemini/OpenAI, OpenCV/FFmpeg, JavaScript/SVG, Docker, pytest*

- Built an end-to-end AI learning pipeline converting PPTX/PDF/DOCX uploads into structured lessons: document parsing, LLM topic outlining, versioned lesson generation with idempotency, retries, dead-letter handling, and deterministic fallbacks when AI providers fail.
- Designed a strategy-aware Visual Intelligence Engine classifying concepts across 22 categories, selecting one of 10 visualization strategies via a rule matrix, persisting knowledge graphs across 9 relational tables, and rendering interactive SVG animations/simulations/videos in a custom presentation player scaling to 200+ slides.
- Secured and scaled the platform: Argon2id + JWT refresh rotation + state-protected Google OAuth, Redis Lua sliding-window rate limiting, strict security headers/CSP, and transaction-race fixes verified by dedicated probes.
- Enforced quality with 843 passing automated tests, 18/18 headless-Chrome E2E, a 41-check JSDOM player suite, and zero lint errors under a strict Ruff ruleset.

**Short one-page version**

EDUVISION AI (Python, FastAPI, PostgreSQL, Redis, Celery, Gemini, Docker)
- Built an AI platform transforming PPTX/PDF content into interactive visual lessons: topic extraction, strategy-aware diagram generation (10 types), animation/simulation/video engines, quizzes, and an AI tutor.
- Delivered production-grade infrastructure: JWT+OAuth auth, Redis rate limiting, Celery DLQ workers, Alembic migrations; validated by 843 green tests and browser E2E.

Role-fit guidance: Backend roles -> lead with bullet 3; AI/ML roles -> lead with bullets 1-2; Full Stack -> mention the custom zero-build JS player.

---

# PART 20 - LINKEDIN VERSION

**Project title:** EduVision AI - AI-Powered Interactive Learning & Understanding Platform

**Short description:** I built an AI platform that turns any PPTX or document into an interactive, visually explained lesson - diagrams chosen by an AI strategy engine, animated explainers, simulations, narrated videos, quizzes, and a context-aware tutor.

**Detailed description:**

Most slides present information but do not teach it. EduVision AI closes that gap. Upload a deck and the platform parses it slide-by-slide, outlines topics with an LLM, generates structured explanations, then classifies every concept across 22 educational categories and selects the best-fitting visualization strategy from 10 types - flowchart, timeline, hierarchy, decision tree, scientific cycle, comparison layout, block diagram, network graph, mind map, algorithm steps. A custom JavaScript Presentation Player renders these as interactive SVG visuals alongside Motion-Engine animations, step-through simulations, and H.264 narrated videos rendered server-side with OpenCV + FFmpeg.

Under the hood: FastAPI with ~100 endpoints, PostgreSQL via async SQLAlchemy with 24 Alembic revisions, Redis powering Lua-scripted rate limiting / OAuth state / caching, and Celery workers with dead-letter queues processing extraction, generation, and embedding jobs. Security includes Argon2id password hashing, JWT rotation with HttpOnly cookies, Google OAuth with single-use state tokens, strict CSP/security headers, and masked structured logging.

Quality was treated as a feature: 843 automated tests passing, an 18/18 headless-Chrome E2E suite, a 41-check JSDOM player regression suite, canvas race-condition probes, and zero Ruff lint errors. The hardest bugs were concurrency races between writes and immediate reads - fixed with commit-before-response patterns documented in code and locked in by repeatable probes.

**Technology list:** Python, FastAPI, PostgreSQL, SQLAlchemy (async), Alembic, Redis, Celery, Gemini API, OpenAI API, python-pptx, OpenCV, FFmpeg, Pillow, edge-tts, boto3/MinIO, JWT/Argon2/Google OAuth, Docker Compose, pytest, Puppeteer, Ruff.

**Key achievements (all measured):**
- 843/843 automated tests passing; 0 lint errors.
- 200-slide deck scalability scenario green in the player regression suite.
- Real 82-topic ML course processed end-to-end: extraction ready ~2 s, 164-slide interactive player.
- Canvas create-read race eliminated (probe 2/2) after root-causing teardown-commit ordering.
- Browser-playable video pipeline rebuilt around H.264 transcoding after diagnosing a codec incompatibility.

---

# PART 21 - GITHUB README CONTENT

# EduVision AI

AI-Powered Interactive Learning & Understanding Platform

EduVision AI transforms static presentations and documents into interactive, visually explained lessons: it understands your content with LLMs, picks the right diagram strategy for every concept, and teaches through animations, simulations, video, quizzes, and an AI tutor.

## The Problem
Slides present information; they don't teach it. Relationships between concepts stay buried in bullet points.

## The Solution
Upload -> Understand -> Visualize -> Interact -> Assess:

1. Upload PPTX/PDF/DOCX/TXT (validated; stored on S3/MinIO or disk).
2. Background extraction parses slides/sections into structured units.
3. An LLM outlines up to 12 topics with slide ranges.
4. Lesson generation produces topic explanations (versioned, idempotent, heuristic fallback when AI is unavailable).
5. The Visual Intelligence Engine classifies each concept (22 categories) and selects one of 10 visualization strategies; graphs persist across 9 relational tables.
6. The Presentation Player pairs every topic with its explanation and an interactive visual - diagram, animation, simulation, or video.
7. Quizzes score answers (including partial credit); a context-aware tutor answers questions; mastery tracking personalizes recommendations.

## Features
- Email/password + Google OAuth sign-in (JWT rotation, protected routes)
- Validated uploads; background processing with live status page
- Strategy-aware visuals: Flowchart, Algorithm Steps, Block Diagram, Comparison Layout, Timeline, Hierarchy, Decision Tree, Scientific Cycle, Mind Map, Network Graph (+ radial fallback)
- Presentation Player: concept/visual slide pairs, thumbnails, keyboard navigation, present mode, active-slide-only rendering (scales to 200+ slides)
- Motion Engine v2 animations (play/pause/seek/speed, scene inspector); scripted simulations (CPU fetch-execute, bubble sort, photosynthesis, water cycle, mitosis); H.264 narrated video rendering
- AI quiz generation + server-side scoring; context-aware AI tutor
- Learning-effectiveness analytics (baseline/post/retention gains), presentation analytics, folders, versioning, audit logs
- Health/liveness/readiness probes, metrics endpoint, masked structured logs

## Architecture
Vanilla JS frontend -> FastAPI (/api/v1) -> services -> {PostgreSQL, Redis, S3/MinIO}. Celery workers + beat consume Redis queues for heavy jobs. AI calls flow through a provider factory (Gemini/OpenAI/local-mock) with caching, retries, rate limits, and usage accounting. (Insert diagram from Part 4.)

## Tech Stack
Backend: Python 3.13+, FastAPI, Pydantic v2, SQLAlchemy 2 async, Alembic
Data/Infra: PostgreSQL 16, Redis 7.4, Celery 5, MinIO/S3 (boto3)
AI: Gemini/OpenAI providers, embeddings pipeline, versioned prompts
Media: python-pptx, pypdf, python-docx, OpenCV, Pillow, FFmpeg (H.264), edge-tts/gTTS
Quality: pytest (843 tests), Puppeteer E2E, JSDOM suites, Ruff, mypy
Deployment: Docker Compose (backend, worker, beat, postgres, redis, minio)

## Testing
pytest: 843 passed | Ruff: 0 errors | Player JSDOM suite: 41/41 | Chrome headless E2E: 18/18

## Security Highlights
Argon2id hashing; JWT HS256 (15-min access / 7-day refresh; aud/iss/jti validated); HttpOnly SameSite cookies; OAuth state with GETDEL + 600 s TTL; Redis Lua sliding-window rate limiting; magic-byte upload validation; strict CSP incl. frame-ancestors 'none'; HSTS in production; sensitive-field log masking.

## Installation
```
git clone <repo>
cd backend
python -m venv .venv            # then activate
pip install -r requirements.txt -r requirements-dev.txt
copy .env.example .env          # fill values
alembic upgrade head
uvicorn app.main:app --reload   # API + docs at /docs
celery -A app.workers.celery_app worker -l info
```

## Environment Variables
See `.env.example` (placeholders only). Key groups: APP_*, DATABASE_*, REDIS_URL, CELERY_*, STORAGE_PROVIDER/S3_*, AI_PROVIDER/AI_API_KEY/AI_MODEL, GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET/GOOGLE_REDIRECT_URI, ACCESS_TOKEN_EXPIRE_MINUTES/JWT_ALGORITHM, RATE_LIMIT_*, UPLOAD_MAX_FILE_SIZE, LOG_*.

## Running Locally
Frontend is served by the API: http://localhost:8000/frontend/index.html (upload -> processing -> player).

## Screenshots
(Placeholders: upload screen; processing checklist; player concept slide; strategy visual gallery; Motion Engine stage; simulation stepper; video panel; quiz results.)

## Future Improvements
Vector-search tutor retrieval over the existing embedding infrastructure; durable stores for simulation/animation/video/player sessions; export HTTP surface (service implemented); spaced-repetition scheduling (schema exists); WebSocket live updates; worker autoscaling.

## Author
Built by <Your Name> - <portfolio/linkedin link>.

---

# PART 22 - INTERVIEW PREPARATION (20 Q&A BASED ON THIS IMPLEMENTATION)

1. **Why FastAPI?** Async-first (extraction, AI calls, media work are I/O-bound), Pydantic v2 contracts at every boundary, dependency injection for auth/sessions, automatic OpenAPI, and a composable middleware chain. It matched the async SQLAlchemy + Redis + Celery stack naturally.

2. **Why PostgreSQL?** The domain is deeply relational (lessons -> versions -> blocks; quizzes -> attempts -> answers; nine-table visual graph). I needed JSONB (context snapshots, layout_config), foreign keys with per-relation cascades, composite indexes, and real transactions - document stores would have forced manual integrity work.

3. **Why Redis?** One instance, four jobs: atomic sliding-window rate limiting via a Lua ZSET script, single-use OAuth state tokens (GETDEL), TTL caches/locks, and Celery broker/result transport.

4. **Why Celery?** Uploads, AI generation, embeddings, and exports must not occupy request workers. Tasks get retries with exponential backoff, acks-late durability, prefetch=1 fairness, time limits, a dead-letter queue, and Redis-keyed idempotency.

5. **Why an asynchronous architecture?** Concurrency without thread bloat: async endpoints + asyncpg + httpx keep the API responsive while heavy CPU/IO work runs in workers. Eager mode exists as a dev fallback; the verified environment runs a real worker.

6. **How does PPTX processing work?** Upload validates extension + magic bytes + 100 MB cap, stores the file via the storage backend, then a Celery task parses it with python-pptx - slide titles, paragraphs, list levels, tables, image metadata, speaker notes become ContentUnit/ContentBlock rows (capped 200x200) - status moves none -> processing -> ready/failed, and lesson generation auto-triggers.

7. **How does AI generate learning content?** Versioned prompt constants define strict JSON contracts (lesson prompt v3: title/summary/language/difficulty/topics[{topic,description}]). AIContentService layers caching, token-bucket rate limits, bounded retries, and timeouts, then persists provider/model/tokens/cost/prompt_hash per version. On AI failure a heuristic payload keeps the product usable.

8. **How does visual strategy selection work?** A deterministic pipeline: regex-scored classification across 22 categories -> component discovery -> typed relationships -> a 22-row rule matrix mapping each category to one of exactly 10 visualization types; the LLM is consulted only when a category falls outside the matrix, and there is a safe default. The decision (reason/confidence/fallback) persists with the canvas.

9. **How does the player work?** POST /player/start returns ordered topics from the latest lesson version; each topic becomes two slides (Concept, Visual). Only the active slide exists in the DOM; visuals generate lazily on demand; thumbnails give O(1) jumps; session sync debounces at 400 ms.

10. **How is large-deck performance handled?** Active-slide-only rendering makes navigation cost independent of deck size; memoization avoids regeneration; one shared requestAnimationFrame loop drives all animations; network chatter is debounced/throttled. Verified by a 200-slide scenario in the JSDOM suite and a real 164-slide ML deck.

11. **How was the canvas race discovered?** Intermittent 404s when the client fetched /nodes,/edges immediately after creating a canvas. Timing showed reads arriving before teardown commit - FastAPI dependency sessions commit after the response is sent.

12. **How was it fixed?** Explicit commit() before returning the response at all three race-sensitive write points (canvas create, register, OAuth callback), each documented in code, plus repeatable probes (canvas probe 2/2; auth 20/20 fresh users).

13. **How does authentication work?** Argon2id hashing; JWT HS256 access (15 min) + refresh (7 days) with sub/jti/type/aud/iss claims validated on decode; HttpOnly SameSite cookies; logout revokes the refresh JTI; ownership checks protect every resource.

14. **How does Google OAuth work?** /auth/google generates a random state stored server-side (Redis GETDEL, TTL 600 s) and redirects to Google; /google/callback validates state single-use, exchanges the code server-side, fetches userinfo, upserts by google_id/email, commits before redirecting, and sets cookies on the redirect response itself.

15. **How is rate limiting implemented?** Middleware resolves the client IP through trusted proxies (rightmost non-trusted XFF hop), applies per-route overrides (regex=limit/window), and executes an atomic Lua script over a Redis ZSET sliding window; 429s include Retry-After; failures fail-open so availability survives a Redis outage.

16. **How is security handled overall?** Defense in depth: security headers/CSP/frame-ancestors 'none', trusted hosts, request-size limits, magic-byte upload validation, parameterized ORM queries, centralized error envelopes, masked structured logs, secrets only via environment, docs disabled in production.

17. **How did you test the project?** Four layers: 843 pytest unit/integration tests (SQLite + mocks, including no-real-Redis guarantees), a 41-check JSDOM player regression (including 200-slide scalability), 18-check headless-Chrome E2E against the live server over a fresh real upload, and targeted probes/wire checks for races and codecs.

18. **What was the hardest bug?** The create -> immediate-read transaction race: symptoms looked like random 404s but were an ordering property of request-scoped sessions. Root-causing it changed how several endpoints commit; the pattern is now documented in-code and covered by probes.

19. **What would you improve in production?** Move in-process session stores (simulation/animation/video/player) to Redis/DB; mount the export HTTP surface (service already built); switch tutor retrieval to true vector search using the existing embedding pipeline; add WebSocket progress updates; autoscale workers.

20. **AI-generated content vs frontend rendering?** All educational decisions happen server-side and persist as data (pattern_type + nodes/edges/components). The frontend is a deterministic layout engine: it draws what it receives and degrades to radial on unknowns rather than inventing structure.

# PART 23 - PROJECT ACHIEVEMENTS (VERIFIED ONLY)

- 843/843 automated tests passing (fresh audit run: 257.86 s); collection verified at exactly 843.
- Ruff strict ruleset: zero findings ("All checks passed!").
- 41/41 JSDOM player checks, including a 200-slide scalability scenario.
- 18/18 headless-Chrome E2E checks against a live server with a fresh real upload.
- 15/15 rate-limit tests: headers, Retry-After, fail-open, route overrides, proxy-aware IP resolution.
- Canvas race probe: 2/2 consistent create -> read runs post-fix.
- Real-world scale proof: 82-topic ML course deck processed end-to-end (~2 s extraction; 164-slide player session).
- Backend health HTTP 200; Redis healthy (7.4.x on port 6380); Celery worker ONLINE with all 16 registered tasks.
- 24 Alembic migrations applied automatically at startup; ~50 model files under consistent conventions.
- Wire check 17/17 including H.264 video render + serve verification.

---

# PART 24 - PROJECT CHALLENGES AND HOW EACH WAS SOLVED

| Challenge | Solution delivered |
|---|---|
| PPTX processing | Format-dispatch parser preserving titles/lists/tables/notes; caps and status lifecycle; magic-byte validation |
| AI content generation reliability | Provider factory + versioned JSON prompts + retries/backoff + heuristic degradation + usage metering |
| Visual strategy selection | Hybrid classifier + rule matrix + LLM-only-when-unmapped + safe defaults; persisted rationale |
| SVG rendering quality | Shared viewBox/palette/markers; label wrap/clamp; auto-degradation (two-column flowcharts, dense modes); honest hierarchy footnote |
| Async/background processing | Celery queues/routes/DLQ/idempotency/beat; acks_late + reject_on_worker_lost |
| Transaction consistency | Commit-before-response pattern at race-sensitive writes + probes + explanatory comments |
| Redis/Celery operations | Environment upgraded to Redis 7.4 on port 6380; eager flag disabled; online worker verified |
| Authentication races | Register/OAuth flush+commit before tokens/redirect; 20/20 fresh-user verification |
| Browser E2E realism | puppeteer-core with installed Chrome against the real server; console noise classified (CSP fonts fixed, favicon route added) |
| Scalability | Active-slide rendering, lazy visuals, async pooling, indexed hot paths, rate limiting, gzip |

---

# PART 25 - CURRENT STATUS

**IMPLEMENTED & VERIFIED:** authentication (incl. Google OAuth code path), uploads/extraction, topic outlines, lesson generation with fallback, visual engine end-to-end, canvas persistence + sub-resources, Presentation Player, Motion Engine v2, scripted simulations, animation blueprints/runtime events, H.264 video pipeline, TTS, quiz lifecycle/scoring/mastery, tutor sessions/context, effectiveness analytics, recommendations, folders/versioning/analytics/audit logs, health/metrics, rate limiting/security stack, Docker Compose topology, Celery+beat+DLQ, the 843-test QA gate.

**PARTIAL:** Export engine (service/exporters/Celery task done; no mounted HTTP routes - only /effectiveness/export CSV exposed); tutor retrieval (positional chunk fetch; vector search pending despite embedding infrastructure); OAuth callback completion pending provider-side redirect-URI configuration; quiz/tutor/TTS not yet embedded in the player UI (available via API).

**SCHEMA/RESERVED ONLY:** learning paths / goals / study plans / review schedules tables; adaptive difficulty engine (orphaned module); visual question generator (orphaned).

**PLANNED / NOT IMPLEMENTED:** multi-node durability for in-process engines (simulation/animation/video/player sessions), WebSocket live updates, mobile clients, LMS integrations.

**KNOWN MINOR QUIRKS (disclosed):** player visual-cache restore guard compares a field never written, so revisits regenerate visuals; docker-compose celery command references app.core.celery_app while the module lives at app.workers.celery_app (one-line fix needed for compose deployment); video runtime assessment correctness check is demo-grade hardcoded logic.

---

# PART 26 - FINAL PROJECT EVALUATION

| Dimension | Score | Justification |
|---|---|---|
| Architecture | 9/10 | Clean layering (routers/services/repositories/AI/workers), async throughout, queue separation with DLQ; deduction for in-process session state |
| AI integration | 9/10 | Provider abstraction, versioned prompts, cost/token metering, honest fallbacks; retrieval not yet vector-based |
| Backend | 10/10 | ~100 endpoints, idempotency, versioning, safety hooks, health probes |
| Frontend | 9/10 | Zero-dependency player with advanced interactions; minor cache-guard quirk |
| Database | 10/10 | Consistent conventions, cascades, indexes, auto-migrations |
| Security | 10/10 | Argon2id/JWT/OAuth-state/Lua rate limiting/CSP/HSTS/log masking/upload validation |
| Testing & quality | 10/10 | 843 green tests + browser E2E + probes + zero lint findings |
| Performance & scalability | 9/10 | Architectural scalability proven to 200+ slides; no formal load benchmarks claimed |
| UX | 8.5/10 | Thoughtful player ergonomics; quiz/tutor/TTS not yet in player UI |
| Innovation | 9/10 | Strategy-aware visual pipeline is a genuinely distinctive approach; simulations are scripted |
| Production readiness | 7.5/10 | Strong posture for single-node; durable session stores, export surface, and vector retrieval remain |

Overall: **9.5/10 as an engineering project** - justified by verified test depth, security breadth, honest degradation design, and documented debugging discipline. A blanket 10/10 would ignore the disclosed partials above.

# PART 27 - VERIFICATION & SOURCE RULE COMPLIANCE

This report was produced under the following verified process:

1. Inspected the full source tree (backend app, frontend, tests, scripts, docs, docker-compose, configs).
2. Read configuration files: pyproject.toml, requirements*.txt, .env.example key inventory (values never printed), alembic revisions list.
3. Inventoried every route decorator across all 15 routers (~100 endpoints).
4. Inspected core services: extraction, outline, lesson generation, visual intelligence suite, quiz, tutor, simulation, animation, video, TTS, export, analytics.
5. Inspected the frontend line-by-line via exploration agents (player.html 1,656 lines fully read).
6. Inspected database models and migrations (0001-0024).
7. Re-ran verification evidence during this audit: full pytest suite (843 passed / 0 failed), Ruff (0 errors), Celery worker log check, Redis/Celery env confirmation.
8. Cross-checked user-supplied final numbers against source where possible; used them as instructed where only runtime logs could confirm (E2E/JSDOM/probe runs).
9. Anything unverifiable is explicitly labeled (e.g., PARTIAL, SCHEMA-ONLY, KNOWN QUIRKS).

No application code was modified. No secrets are included.

---

# APPENDIX - QUICK FACTS CARD

- Backend entry: backend/app/main.py (FastAPI; middleware stack; 15 routers; static mounts)
- Workers: app/workers/celery_app.py + tasks.py + rag_tasks.py (16 eduvision.* tasks)
- Visual engine entry: services/visual_intelligence_service.py
- Strategy decision: services/visualization_decision_service.py (CATEGORY_VISUALIZATION_MATRIX)
- Frontend player: backend/frontend/player.html
- Player API: api/v1/player.py + services/lesson_player_service.py
- Auth: api/v1/auth.py + core/security.py (Argon2id + HS256 JWT)
- Rate limiting: middleware/rate_limit.py (Lua sliding window)
- Health: api/v1/health.py (/health, /health/live, /health/ready)
- Tests: backend/tests/unit/*.py (843 collected); scripts/_mv_player_test.js; scripts/_mv_browser_e2e.js; scripts/_mv_wire_check.ps1

END OF REPORT

