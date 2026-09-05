# Post-P11 Product & Architecture Audit

**Phase:** P11 (Personalized Study Plans, Learning Goals & Adaptive Learning Paths — audit)
**Type:** Audit + product decision only — NO P12 implementation
**Branch:** `feature/individual-user-foundation`
**Audited HEAD:** `30e3bbd` (`feat(p11): personalized study plans, learning goals and learning paths`)
**Alembic head:** `0031_review_schedule_concept` (verified)
**Date:** 2026-09-05

---

## 1. Executive Summary

P11 is **complete, committed, and verifiable** at HEAD `30e3bbd`. Independent re-verification this pass confirms every P11 release gate: SQLite **1161 passed**, PostgreSQL **15 passed** (testcontainers, `postgres:16-alpine`), browser E2E **13 passed** (real Chrome against a live uvicorn on SQLite), Ruff clean on the whole repo, mypy exactly **83 errors / 24 files** (zero new), a single Alembic head `0031_review_schedule_concept`, a clean working tree, `git diff --check` clean, and a secret scan with no hits. NG-5 (plans / goals / learning paths) is reachable in the browser, deep-linked, learner-scoped, and closed against live mastery/review/session state with zero new migrations.

Beyond re-verification, this audit did two new things:

1. **Re-traced the full learner journey (26 steps), the learning-loop transition map, the capability matrix, the frontend reachability graph, and the AI/RAG/security/infra stacks** (see companion `POST_P11_CAPABILITY_MATRIX.md`).
2. **Empirically verified the ORM/migration drift on the quiz attempt tables against a real `postgres:16-alpine` database.** This produced the single most important finding of the audit:

> **CRITICAL — the live quiz attempt path cannot execute on a migrated PostgreSQL database.** `start_attempt` inserts `QuizAttempt` and `QuestionAttempt` rows whose ORM models contradict migration `0005` (`quiz_attempts.max_score`/`time_spent_seconds` NOT NULL in the schema but nullable in the model and unset at start; `question_attempts.public_id`/`time_spent_seconds` NOT NULL in the schema but **unmapped** in the ORM; `question_attempts.feedback` is `jsonb` in the schema but `Text` in the ORM). All three failure classes were reproduced on a real migrated PG DB. The 15-test PostgreSQL suite never inserts an attempt, so the suite is green while the production quiz flow would 500. The SQLite path (schema built from models via `create_all`) makes the drift invisible to all 1161 SQLite tests.

**Recommended P12: Genuine Adaptive Assessment (NG-4) with a mandatory in-scope prerequisite — the PostgreSQL attempt-path repair.** The last explicitly-deferred NG from the P10/P11 contracts is NG-4, and this audit's empirical drift finding demonstrates *why* attempting NG-4 naively (e.g. "un-sticking" the dead `AdaptiveAssessmentEngine`) is wrong: the entire attempt path must first be production-correct on PostgreSQL. P12 therefore opens with an explicit repair checkpoint (schema-consistency fix + PG behavioral tests that exercise the live attempt flow), then builds the deterministic adaptive delivery MVP on the repaired spine. Scoring table and full rationale in §17–§18.

---

## 2. Starting Commit / Repository State

| Item | Expected | Verified | Evidence |
|---|---|---|---|
| Branch | `feature/individual-user-foundation` | yes | `git branch --show-current` |
| HEAD | `30e3bbd` (`feat(p11): ...`) | yes | `git log --oneline -3` |
| P11 start commit | `92c4522` | yes | `P11_IMPLEMENTATION_REPORT.md` §1 |
| Working tree | clean | yes | `git status --short` = empty |
| Alembic head | single head `0031_review_schedule_concept` | yes | `alembic heads` |
| P11 report/scope docs | present | yes | `P11_IMPLEMENTATION_REPORT.md`, `P11_SCOPE_AND_FOUNDATION.md`, `POST_P10_*` |

---

## 3. Verification Baseline (actually re-verified this pass)

| Gate | Command | Observed | Floor |
|---|---|---|---|
| git status | `git status --short` | clean | clean |
| current commit | `git rev-parse --short HEAD` | `30e3bbd` | `30e3bbd` |
| Alembic heads | `alembic heads` | `0031_review_schedule_concept (head)` | single head |
| SQLite regression | `pytest tests/unit tests/integration -m "not postgres and not e2e"` | **1161 passed**, 0 failed (~542s) | >= 1161 (P11 contract) |
| PostgreSQL | `pytest tests -m postgres` (testcontainers `postgres:16-alpine`, `upgrade head`) | **15 passed**, 1174 deselected | >= 15 |
| Browser E2E | `pytest tests/e2e -m e2e` | **13 passed in 138.53s** (real browser) | 13 passed |
| Ruff | `ruff check .` | **All checks passed** (whole repo) | clean |
| mypy | `mypy app` | **83 errors in 24 files** — exactly the authoritative P11/P10 baseline, zero new | 83/24 |
| git diff --check | `git diff --check` | clean (exit 0) | clean |
| Secret scan | git grep over HEAD for key/secret/password patterns | only legitimate settings-driven provider config references — no committed secrets | none |

Note: the PostgreSQL suite was re-run live this pass *and* extended manually with a scratch attempt-insertion probe (see §12 and the CRITICAL finding) — the probe lives outside the repo (temp scratch script, not committed).

---

## 4. P0–P11 Evolution Summary

| Phase | Focus | Landmark |
|---|---|---|
| P0 | Deep architecture audit | Ground truth, roadmap |
| P1 | Security fast-follow | Quiz IDOR fix, magic-byte validation, fail-fast config, CI |
| P2 | Data/runtime foundation | PostgreSQL parity, commit-before-dispatch, bounded state |
| P3 | Production hardening | N+1 fix, memory bounds, observability, slim image |
| P4 | RAG/export/caching | Semantic RAG infra, exports, E2E infra |
| P5 | Learning sessions/player | SPA player, persistent progress |
| P6 | Interactive assessment | Quiz-taking UI in the vanilla player |
| P7 | Learner intelligence/dashboard | `/me/progress`, mastery, recommendations, dashboard |
| P8 | Mastery-aware AI tutor | Conversational tutor, remediation, session persistence |
| P9 | Tutor hardening & semantic grounding | Real semantic RAG, retention, resume UI, index parity |
| P10 | Adaptive remediation & review engine | Closed loop: next-action CTA, actionable reco, review queue, mastery public-ID keying, decay signal |
| **P11** | **Personalized study plans, goals & learning paths** | **NG-5 closed: dated Today Plan + goals + adaptive path, read-composed from live state, zero migrations** |

---

## 5. Current Product Architecture (evidence-based)

- **Backend**: FastAPI (async), SQLAlchemy 2.x, UoW/repository pattern. `app/main.py:155-177` mounts **23 routers** under `/api/v1` (health, auth, metrics, presentations, storage, folders, player, quiz, visual, simulation, animation, animation-runtime, video, video-runtime, assistant, effectiveness, learner_progress, review, plan, goals, path, exports, tutor).
- **Database**: PostgreSQL (production) + SQLite (test fast path), PortableJSONB dual-dialect, linear Alembic chain (31 migrations; single head `0031_review_schedule_concept`). Auto-migrate on startup behind `AUTO_MIGRATE_ON_STARTUP` (`app/main.py:82-93`).
- **Frontend**: vanilla multi-page SPA in `backend/frontend/` (no framework, no build step), mounted at `/frontend` (`app/main.py:185-189`): `index`, `signin`, `signup`, `upload`, `processing`, `player.html` (slides + 5+ SVG visual strategies + motion/animation engine + video + simulation runtime + quiz overlay), `tutor.html` (RAG-grounded chat, session resume, remediation + practice CTA), `dashboard.html` (stat cards, recommendations, review queue, **P11 Today Plan / Goals / Learning Path panels**, lesson progress, chips, trend).
- **Worker**: Celery + Redis + SafeDispatch/DLQ + idempotency/beat. 16 registered tasks; event-dispatched enqueues all go through `safe_dispatch` (`tasks.py:92-136`); the 8 beat-only tasks are never queued by app code, and **no Celery task exists for vision/TTS/video** — those run synchronously in-process (see §14).
- **AI abstraction**: `AIContentService` (`app/ai/service.py:59-71`) as the mandatory AI path with provider registry `local`/`openai`/`gemini` (`providers/__init__.py:7-9`), retry/timeout/rate-limit/cache/cost accounting; **zero vendor SDK imports anywhere in `app/`**; the raw `get_ai` FastAPI dependency (`core/dependencies.py:43-44`) is dead (no router uses it).
- **RAG**: shared `app.ai.retrieval.semantic_retrieve_chunks` (`retrieval.py:77-131`) — embed query → cosine (null-safe) → threshold → top-k → positional fallback; learner-scoped by the caller (`mastery_tutor_service.py:696-741`). RRF/MMR knobs (`config.py:222-223`) exist but are **inert** (hybrid fusion not implemented).
- **Learner intelligence**: deterministic rule-based (mandate): mastery scalar (`educational_memory_service`, `BoundedCache` 5000/1800s), rule-table recommendations (`recommendation_engine`, thresholds 50/85/95), P10 review scheduler (`review_scheduler.py`, 1/3/7/14-day ladder, decay pressure), `review_schedule_service` (lazy seeding, bounded due queue `MAX_DUE_LIMIT=200`), **P11 plan/goal/path services** (read-compositions, zero AI).
- **Security**: Argon2id, JWT (access + refresh, Redis JTI revocation), httponly/secure/samesite cookies (`auth.py:136-155`), storage proxy (owned-prefix-locked), magic-byte upload validation (`file_helpers.py:32-51`), ownership 404-equalization, per-IP sliding-window rate limit (Redis Lua, `rate_limit.py:277`) with route overrides, request-size + security-headers + trusted-host middleware, fail-fast config guards (`config.py:446-447`).

### Architectural invariants (held as of P11)
1. `AIContentService` is the mandatory AI path.
2. Learner intelligence is deterministic rule-based, no ML/DL.
3. Vanilla multi-page SPA, no framework migration.
4. PostgreSQL production / SQLite test dual-dialect.
5. Linear Alembic chain, additive-only migrations, single head.
6. Every resource scoped by `user.id` from auth; ownership 404-equalized.
7. Bounded in-process caches; bounded list/query constants.
8. **New finding this pass — invariant 4 is violated in practice on the assessment tables (see §12).**

---

## 6. Current User Journey (26 steps, evidence-traced)

| # | Stage | Implemented | Browser | Persisted | User-scoped | Fallback | Evidence |
|---|---|---|---|---|---|---|---|
| 1 | Registration | yes | yes | yes | n/a | — | `signup.html`, `auth.py` |
| 2 | Sign-in / refresh-auth | yes | yes | yes | n/a | Google OAuth | `auth.py`, `signin.html` |
| 3 | Presentation ingestion (upload) | yes | yes | yes | yes | — | `upload.html`, `presentations.py` |
| 4 | Content extraction | yes | via processing | yes | yes | AI retry | `content_extraction_service.py` |
| 5 | Topic outline generation | yes | yes | yes | yes | AI retry | `topic_outline_service.py` |
| 6 | Lesson generation (Celery) | yes | yes | yes | yes | AI retry | `lesson_generation_service.py`, `lessons.generate` |
| 7 | Lesson versioning / publish | yes | yes | yes | yes | — | `generated_lesson_version.py`, `player.py` |
| 8 | Lesson player open / session start | yes | yes | yes | yes | — | `player.html`, `learning_sessions` |
| 9 | Slide / content render | yes | yes | — | yes | — | `player.html` slide engine |
| 10 | Concept learning (mastery seed) | yes | yes | yes | yes | — | `educational_memory_service` |
| 11 | Visual learning (canvases / SVG strategies) | yes | yes | — | yes | visual fallback | `player.html`, `visual_canvases.py` |
| 12 | Animation generation + runtime | PARTIAL | partial (player wires 4 of 15 routes) | — | yes | — | `animation_router`, `animation_runtime_router` |
| 13 | Simulation runtime | PARTIAL | partial | — | yes | — | `simulation_router` |
| 14 | Video generation | PARTIAL | yes (generate) | yes | yes | — | `video_router`, `video_composition_service.py` |
| 15 | Video runtime (bookmark/assessment/tutor-context) | BACKEND-ONLY | no | — | yes | — | `video_runtime_router.py` (not called by frontend) |
| 16 | Learning-session progress save / resume | yes | yes | yes | yes | — | `player.py`, `learning_sessions` |
| 17 | Take checkpoint (attempt start) | yes | yes | yes | yes | — | `player.html` "Take Checkpoint", `quiz_attempt_service.start_attempt` |
| 18 | Answering / single-question grading | yes | yes | yes | yes | deterministic grading | `submit_answer`, `_evaluate_answer` |
| 19 | Assessment scoring / percent | yes | yes | yes | yes | — | `score_summary`, submit path |
| 20 | Mastery update (public-ID keyed) | yes | yes | yes | yes | — | `_update_concept_mastery` (P10), `educational_memory_service` |
| 21 | Recommendation (deterministic next actions) | yes | **actionable** | derived | yes | deterministic | `recommendation_engine.py`, `dashboard.html` `recoAction` |
| 22 | Remediation / RAG tutor chat | yes | yes | yes | yes | deterministic | `mastery_tutor_service.py`, `tutor.html` |
| 23 | Review scheduling (due queue) | yes | yes | yes | yes | deterministic | `review_scheduler.py`, `review_schedule_service.py` |
| 24 | Review completion / interval advance | yes | yes | yes | yes | — | `complete()` routes via P10; plan-item completion reuses it |
| 25 | **Today Plan / Goals / Learning Path (P11)** | yes | yes | yes | yes | deterministic | `study_plan_service.py`, `learning_goal_service.py`, `learning_path_service.py`, `dashboard.html` panels |
| 26 | Cross-user isolation / ownership chain | yes | yes | n/a | yes | 404-equalized | `test_two_user_isolation.py`, `test_p11_api_security.py` |

---

## 7. Learning Loop Transition Map (re-trace, incl. P11)

| # | Transition | Status | Evidence |
|---|---|---|---|
| 1 | assessment → mastery | **CONNECTED** | `submit_quiz` → `_update_concept_mastery` (public-ID keyed, P10) → `save_to_db` |
| 2 | mastery → recommendation | **CONNECTED** | `generate_recommendations` reads `memory.concept_records`, weakest-first |
| 3 | recommendation → action | **CONNECTED** | `learner_progress_service._action_lesson_map` + `recoAction()` CTAs |
| 4 | action → practice | **CONNECTED** | dashboard CTAs → `player.html?lesson=<public_id>` → `player/start` |
| 5 | practice → assessment | **CONNECTED** | "Take Checkpoint" → `startQuiz` → overlay → `submitQuiz` |
| 6 | assessment → scheduling | **PARTIAL** | mastery updates on submit; schedules seed lazily on next `GET /me/review` |
| 7 | scheduling → recommendation | **CONNECTED** | review panel lists due items + Practice deep-link |
| 8 | tutor → remediation | **CONNECTED** | `remediate()` returns structured `next_action` |
| 9 | remediation → practice | **CONNECTED** | `practiceCtaHtml()` player deep-link |
| 10 | review → mastery | **PARTIAL (by design)** | `record_review_activity()` resets review clock; no mastery rewrite |
| 11 | dashboard → lesson | **CONNECTED** | lesson cards → player |
| 12 | dashboard → tutor | **CONNECTED** | weak chips → `tutor.html?concept=` |
| 13 | player → review | **NOT CONNECTED** | no review-queue entry point in `player.html` (unchanged from P10; LOW) |
| 14 | player → assessment | **CONNECTED** | checkpoint → quiz overlay |
| 15 | dashboard → Today Plan | **CONNECTED (P11)** | `#todayPlanBody` renders due reviews + practice + lesson, deep-linked |
| 16 | plan item → review complete | **CONNECTED (P11)** | `plan/items/{key}/complete` routes through `ReviewScheduleService.complete` (E2E-verified) |
| 17 | plan item → lesson/practice | **CONNECTED (P11)** | sticky done-marks in `study_plans.days` JSONB; deep-links to player/tutor |
| 18 | goal → derived progress | **CONNECTED (P11)** | progress always server-derived (mastery/lesson/quiz/streak), never client-typed |
| 19 | path → lesson | **CONNECTED (P11)** | single active path, weakest-first, deep-links to owned player |

**Result:** 17 CONNECTED, 2 PARTIAL, 1 NOT CONNECTED (LOW). No high-severity broken transition in the browser path. **Caveat:** transitions 1/5/14/17's *persistence* legs (attempt INSERT) are broken on a migrated PostgreSQL DB (see §12) — SQLite hides it; the browser E2E runs on SQLite.

---

## 8. Capability Audit

See companion **`POST_P11_CAPABILITY_MATRIX.md`** for the full status table.

Summary by domain:
- **Content/Lesson/Visual/Assessment**: VERIFIED for the learn→assess spine; adventure animation/simulation/video surfaces are BACKEND-ONLY or PARTIAL; **assessment persistence is PG-broken (CRITICAL, §12)**.
- **Learner intelligence**: VERIFIED deterministic stack (mastery, recommendations, review, plans, goals, paths).
- **Review scheduling**: VERIFIED (P10) + **plan integration VERIFIED (P11)**.
- **Study plans / goals / learning paths**: **IMPLEMENTED (P11, NG-5 CLOSED)** — previously the top gap.
- **Genuine adaptive assessment (NG-4)**: **NOT IMPLEMENTED** — dead `AdaptiveAssessmentEngine` (VisualQuestion-based, incompatible with the live quiz path); fixed-order delivery (`quiz_repository.py:151 order_by(Question.position)`); `shuffle_questions` stored but never honored. Remains the last deferred NG.
- **Tutor + RAG**: VERIFIED.
- **Dashboard**: VERIFIED, actionable, now with plan/goals/path panels.
- **Learner analytics**: PARTIAL (dashboard trend only; analytics schema/tables/schemas still orphaned).
- **Teacher/classroom, collaboration, 2D editor, mobile, framework migration**: NOT IMPLEMENTED / OUT OF SCOPE (unchanged).
- **Mastery decay / confidence**: PARTIAL (pressure signal ranking-only; never persisted).

---

## 9. P11 Verification (independent pass)

- **NG-5 (structure layer)**: CLOSED. Live-verified in the browser E2E: Today Plan lists a due review + continue-lesson with real deep-links; completing the review through the plan UI routes through P10 and exits the due queue; completing the lesson through the plan UI is sticky; Learning Path loops the seeded lesson into `player.html`; Goals show derived progress ("in progress", not achieved, then auto-achieves at 100%). All six `/me/*` endpoints learner-scoped; cross-user → 404 (`test_p11_api_security.py`).
- **Composition correctness**: Today Plan is a pure read-composition (`ReviewScheduleService.list_due` capped 100 + weak/developing mastery ∩ not already reviewed + single `LearningPathService.get_path` read); goals derive via aggregate SQL (`COUNT(DISTINCT)`, `func.max`); path ordering key `(tier, mastery asc|101, created_at, public_id)` — deterministic, no AI, no second scheduler, no state drift.
- **No new migrations**: alembic head unchanged `0031_review_schedule_concept`; 0011 tables reused as-is.
- **Regression evidence**: 1161 SQLite (+17 over P10's 1144), 15 PG, 13 E2E, Ruff clean, mypy 83/24 zero-new — all re-verified this pass.

---

## 10. Security Audit

Overall: **strong; no CRITICAL; P11 introduced no new attack surface; one CRITICAL production-availability finding from the migration drift (§12) is a correctness issue, not a confidentiality issue.**

Verified preserved:
- **Authentication** — `get_current_user` on all new/changed endpoints (`/me/plan`, `/me/goals`, `/me/path`); user id never client-supplied.
- **Ownership / user isolation** — `test_p11_api_security.py` (5), `test_two_user_isolation.py` (22), `test_learner_progress_security.py` (5), `test_mastery_tutor_security.py` (7), `test_p6_assessment_security.py` (14), `test_review_api_security.py` (5) all green; cross-user goal/path/plan reads and plan-item completion → 404.
- **Learner-scoped RAG / tutor sessions** — unchanged (P8/P9 chain).
- **Prompt-injection boundary** — unchanged; remediation/RAG stays behind `AIContentService`; learner content treated as data. Pre-existing HIGH (own-learner self-injection window, bounded) carried.
- **XSS protections** — all new dashboard plan/goals/path dynamic content `escHtml`-escaped; CTAs are server-built `deep_link` hrefs (no dead links, no XSS).
- **Storage isolation / upload validation** — unchanged and still green (`test_upload_validation.py` 23).
- **Rate limiting** — global per-IP default 100 req/60s (`config.py:366-367`) + route overrides for quiz/attempt/adaptive-quiz (`config.py:375-379`); AI-call limiter `AI_RATE_LIMIT_RPM=60` (`ai/service.py:186-187,203-204`).

Outstanding (carried, documented — NOT P12-blocking):
- HIGH — own-learner prompt-injection guard (bounded, self-only).
- MEDIUM — refresh token not rotated on use; in-memory revocation fallback not shared across processes; body-size check relies on declared Content-Length; no per-user AI credit budget; `get_ai` dependency dead; no functional Redis/Celery integration test (only mocks).
- LOW — CSRF helpers not enforced on auth POSTs (access token flows via header in the SPA; cookie-only surfaces limited); effectiveness report leaks presentation title (ownerless); SVG innerHTML path in player; duplicated inline `authFetch`/`escHtml` (~5x) and dead `?deck=` param / dead controls div in `player.html`.

---

## 11. AI / RAG Audit

- **Abstraction verified**: `AIContentService` is the single AI entry point; provider wiring 100% config-driven (`ai/service.py:59-71`); registry `local`/`openai`/`gemini` (`providers/__init__.py:7-9`); **zero vendor SDK imports in `app/`** (only HTTP endpoints inside the provider classes); no in-code default provider (operator must set `AI_PROVIDER`; tests pin `local`).
- **Consumers**: `component_discovery_service.py:14,39`, `learning_assistant_service.py:636,638`, `learning_objective_service.py:13,36`, plus lesson/topic-outline generation paths — all through the abstraction. No bypass found. The raw `get_ai` dependency is dead code (minor cleanup).
- **RAG pipeline**: `semantic_retrieve_chunks` (query embed → cosine, null-safe → `TUTOR_RETRIEVAL_SIMILARITY_THRESHOLD` → deterministic sort → top-k → `[]`-on-failure → positional fallback), learner-scoped upstream in the tutor service. Semantic-only; RRF/MMR fusion knobs (60 / 0.7) are **configured but never consumed** (inert; documented).
- **Embeddings**: provider registry incl. deterministic `local` (384-dim); OpenAI `text-embedding-3-small`/1536, Gemini `text-embedding-004`/768. Embedding jobs flow through Celery `embedding.generate`/`embedding.batch` via `safe_dispatch`.
- **Attribution/confidence**: `TutorMessageResponse` (`source_kind`, `confidence`, `attribution`) rendered as chips; P8 E2E asserts the real RAG path.
- **Boundedness**: `TUTOR_MAX_CONTEXT_CHARS` 16000, `TUTOR_MAX_RESPONSE_TOKENS` 1024, `TUTOR_MAX_HISTORY_MESSAGES` 12; assistant hardcodes `limit=20` (LOW consistency).
- **P12 note**: adaptive assessment should be **deterministic** (mastery-tuned question ordering from stored difficulty + mastery), no new AI provider, no RAG change; if any AI summary is ever added it must stay behind `AIContentService`.

---

## 12. Database / Migration Audit — INCLUDING THE NEW CRITICAL FINDING

### 12.1 Baseline (verified)
- Dual-dialect PostgreSQL/SQLite with PortableJSONB; linear Alembic chain, 31 migrations, single head `0031_review_schedule_concept` (verified).
- Migration history carries parity discipline (0030 composite index matches ORM; 0031 adds `concept_id` + `last_reviewed_at` + `(user_id, due_at)` due-queue index).
- P11 added zero migrations; 0011 tables reused as-is.

### 12.2 CRITICAL — ORM/migration drift on the quiz attempt tables breaks the live attempt path on PostgreSQL (empirically verified)

Reproduced on a real `postgres:16-alpine` container via testcontainers with `alembic upgrade head`, then issuing ORM inserts identical to the live service. Three distinct failure classes, in the order a real learner hits them:

| # | Column | Migration `0005` | ORM model (`app/models/`) | Live insert path | Result on migrated PG |
|---|---|---|---|---|---|
| 1 | `quiz_attempts.max_score` | `Numeric(8,2)` **NOT NULL** (line 310) | `QuizAttempt.max_score` **nullable** (`quiz_attempt.py:54`) | `start_attempt` (`quiz_attempt_service.py:182-190`) does **not** set it | `IntegrityError: null value in column "max_score" ... violates not-null constraint` |
| 2 | `quiz_attempts.time_spent_seconds` | `Integer` **NOT NULL** (line 312) | **nullable** (`quiz_attempt.py:56`) | not set at start | same NOT NULL failure (confirmed after fixing #1) |
| 3a | `question_attempts.feedback` | `postgresql.JSONB` (line 375) | mapped as `Text` | `_qa_repo.create` inserts it | `DatatypeMismatchError: column "feedback" is of type jsonb but expression is of type character varying` even with NULL bind (confirmed) |
| 3b | `question_attempts.public_id` | `String(40)` **NOT NULL** (line 364) | **not mapped at all** | row lacks the column value | would fail NOT NULL after #3a is fixed |
| 3c | `question_attempts.time_spent_seconds` | `Integer` **NOT NULL** (line 372) | **not mapped** | row lacks the column value | would fail NOT NULL after #3a/#3b |

- Violated invariant: the schema and the ORM disagree on the two attempt tables; the dual-dialect test strategy (SQLite `create_all` from models) means **no SQLite test can see it**, and the 15-test PostgreSQL suite **never inserts a `QuizAttempt`/`QuestionAttempt`** (it checks FK/unique constraints and `PortableJSONB` round-trips on non-attempt tables; `test_learner_journey.py` only runs learning sessions). Hence 15 "green" PG tests + 1161 green SQLite tests coexist with a **production quiz flow that 500s on a migrated PostgreSQL at attempt start**.
- No later migration touches these columns (0022/0025/0026 and the 0030/0031 parity migrations do not alter them).
- Severity: **CRITICAL** (core assessment flow unusable on the production DB), mitigated only by the fact that there is no live traffic yet. It is a correctness/availability defect, not a confidentiality defect.
- Root cause categories: (a) nullable-in-ORM vs NOT-NULL-in-migration (`max_score`, `time_spent_seconds`, `started_at` — the latter is saved at start so it only breaks rows created without it), (b) NOT-NULL columns absent from the ORM (`question_attempts.public_id`, `question_attempts.time_spent_seconds`), (c) a type divergence (`feedback` JSONB vs Text).
- **Prescribed fix (for the P12 contract, not performed now)**: one additive Alembic migration (nullable or server-defaulted `max_score`/`time_spent_seconds`; backfill; map `public_id`/`time_spent_seconds` on `QuestionAttempt`; align `feedback` typing, e.g. `JSON().with_variant(JSONB())` with matching serialization), **plus PG behavioral tests that run the live `start_attempt`/`submit_answer` flow against the migrated schema** (extending the 15-test suite), keeping SQLite green. See `P12_SCOPE_AND_FOUNDATION.md` §6–§7.

### 12.3 Reusable / orphaned infrastructure (unchanged from P10, now partly wired)
- **Reusable**: `learning_paths`/`learning_goals`/`study_plans` (0011) — now LIVE (P11). `review_schedules` LIVE. `educational_memories` LIVE. `generated_lessons`/`learning_sessions`/`quiz_attempts` LIVE.
- **Orphaned / schema-only** (zero references, verified via git grep): schemas `adaptive.py`, `analytics.py`, `analytics_insights.py`, `director.py`, `teaching_strategy.py`, `student_note.py`, `learning_activity.py`, `bookmark.py`, `search.py`, `visual_personalization.py`; services `adaptive_assessment_engine.py` (built on `schemas/visual_assessment.py` `VisualQuestion` — incompatible with the live quiz path; referenced only by itself + docs), `visual_question_generator.py`, `concept_service.py`; analytics table models still registered in `app/models/__init__.py` but unused in features.

**Decision on the drift finding (required):** In-scope. The P12 recommendation (NG-4 adaptive assessment) makes the attempt-path repair a mandatory C0/C1 checkpoint — deferring it is rejected because (a) it is a verified production blocker on the very spine the phase reinvests in, and (b) it is a bounded, additive, low-risk repair that the existing PG suite simply failed to catch.

---

## 13. Frontend Audit

- **dashboard.html** (~380s of new P11 panel + existing): stat cards, actionable "Next Best Actions", review queue (Practice + Mark reviewed), Today Plan (`#todayPlanBody`), Goals (`#goalsBody`), Learning Path (`#pathBody`), lesson progress, concept chips, trend. All P11 panels present, wired, `escHtml`-escaped, deep-linked. Verified by subagent walk of every anchor/button + E2E.
- **player.html**: slides, thumbnails, learner-journey panel, SVG strategies, motion engine, video, simulation runtime, full quiz overlay. No link to dashboard/review queue/Today Plan (known gap, unchanged); dead `?deck=` param and dead controls div exist (LOW).
- **tutor.html**: weak-concept quick picks, session list/resume, RAG/deterministic badges, remediation + "Practice this" CTA, `?concept=`/`?session=`/`?lesson=`. Verified subagent: no broken navigation.
- **Navigation**: brand/upload/dashboard/tutor nav across pages; `authFetch`/`escHtml` duplicated inline per page (~5x — LOW/MEDIUM maintainability).
- **XSS safety**: `escHtml`/`escSvg` used for all dynamic content (verified).
- **Browser E2E**: 13 tests across 7 files (smoke ×4, learner_journey ×2, p6 full loop ×1, p7 dashboard ×1, p8 mastery tutor ×1, p10 adaptive review ×3, p11 plan/goals/path ×1) — Playwright + system Chrome against a real uvicorn on SQLite.

---

## 14. E2E Product Journey Audit

- **Journey A (signup→signin→content→lesson→learning→assessment→mastery→recommendation)**: CONNECTED (P6/P7 E2E + P10 NG-1). **Caveat:** assessment persistence would fail on PG (see §12) — SQLite run is green.
- **Journey B (weak→recommendation→remediation→practice→assess→mastery→scheduling→changed reco)**: CONNECTED (P10 NG-3 browser-verified).
- **Journey C (tutor→learner question→learner-owned RAG→response→remediation→practice)**: CONNECTED (P8 E2E asserts `rag`; P9 resume; P10 practice CTA).
- **Journey D (dashboard→weak→actionable reco→destination→learning action)**: CONNECTED (P10 NG-2).
- **Journey E (Today Plan→review through plan UI→interval advance; goal creation→derived progress; path→player deep-link)**: CONNECTED (P11 E2E, browser).
- **Journey F (User A/B isolation)**: VERIFIED (`test_two_user_isolation.py` 22 + P11 security 5).
- **Remaining broken transition:** player → review queue (LOW, unchanged); PG attempt-persistence is a journey-blocking environment defect (CRITICAL, §12).

---

## 15. Product Gaps (post-P11)

| ID | Gap | Severity | Status post-P11 | Best evidence |
|---|---|---|---|---|
| G1 | Genuine adaptive assessment (NG-4) | **HIGH** | NOT IMPLEMENTED (dead engine incompatible with live quiz path; fixed-order delivery) | `adaptive_assessment_engine.py` (no live imports); `quiz_repository.py:151` |
| G2 | PG attempt-path ORM/migration drift | **CRITICAL** | CONFIRMED empirically this pass (3 failure classes) | §12.2; scratch PG probe |
| G3 | Learner-facing analytics / insights | MEDIUM | PARTIAL (dashboard trend only; analytics tables/schemas orphaned) | `analytics.py`, `analytics_insights.py` (zero refs) |
| G4 | Persisted mastery decay / confidence | MEDIUM | PARTIAL (P10 pressure signal is ranking-only; score never decays) | `compute_decay_signal` vs `update_concept_mastery` |
| G5 | Animation/video runtime frontend wiring | MEDIUM | PARTIAL — `video_runtime_router.py` backend-only; animation 4 of 15 routes wired | `player.html`, routers |
| G6 | Assessment → immediate scheduling | LOW | PARTIAL (lazy on next dashboard read) | `review_schedule_service._ensure_schedules` |
| G7 | Player → review queue entry point | LOW | NOT CONNECTED | `player.html` has no review link |
| G8 | Retention scheduled/global | MEDIUM | PARTIAL (on-read only; no beat task) | `enforce_retention` in `list_sessions` only |
| G9 | Async/worker hardening | MEDIUM | Video render in request path / fire-and-forget asyncio (`main.py:54-70`); no functional Redis/Celery integration test | §14 infra evidence |

---

## 16. Technical Debt That Actually Matters

| Debt | Severity | Why it matters | P12 impact |
|---|---|---|---|
| ORM/migration drift on `quiz_attempts`/`question_attempts` | **CRITICAL** | Production quiz flow 500s on migrated PG; masked by SQLite create_all + PG-suite gap | **Mandatory P12 C0/C1** (fix + PG behavioral tests) |
| PG test suite never inserts attempts | **HIGH** | The root cause of the suite being green while the flow is broken | Fixed by the new PG behavioral tests |
| Dead engine `adaptive_assessment_engine` + `visual_question_generator` + `concept_service` | MEDIUM | Misleading "infrastructure exists" signal; VisualQuestion-based, incompatible | P12 retires/repurposes explicitly |
| `shuffle_questions` stored but never honored; fixed-order delivery | MEDIUM | Assessment is not adaptive; contradicts brand promise | P12 A2 core |
| Orphaned analytics schemas/tables/models | LOW | Not used | Keep for future analytics phase |
| mypy 83/24 debt | MEDIUM | Held flat by policy; zero-new rule | P12 must add 0 |
| Duplicated inline `authFetch`/`escHtml`; dead `?deck=` param / controls div in `player.html` | LOW | Maintainability | Optional; not required |
| Inert RRF/MMR retrieval knobs; assistant hardcodes `limit=20` | LOW | Inconsistent config | Out of scope |
| `get_ai` dependency dead; beat-only tasks never queued; no Redis/Celery integration test | MEDIUM | Ops robustness gap | Out of P12 MVP (documented; revisit in a hardening phase) |
| Retention not scheduled globally | MEDIUM | Unbounded tutor rows in prod | Out of P12 (documented) |

Do **not** recommend fixing unrelated historical mypy debt — it is gated flat and does not block P12.

---

## 17. Candidate P12 Directions (transparent scoring)

Scoring model (weights summing to 1.0): Learner value 0.25 · Educational value 0.15 · Product differentiation 0.10 · Architectural readiness 0.15 · Existing infra reuse 0.10 · Implementation complexity (inverse) 0.08 · Risk (inverse) 0.07 · Portfolio value 0.10.
Scores are 1–5 (5 = best); weighted total = Σ(weight × score). Candidate set A–J per the audit contract.

| Cand | Direction | Lrnr (×.25) | Ed (×.15) | Diff (×.10) | Ready (×.15) | Reuse (×.10) | Cx⁻¹ (×.08) | Risk⁻¹ (×.07) | Port (×.10) | **Total** |
|---|---|---|---|---|---|---|---|---|---|---|
| A | **Genuine adaptive assessment (NG-4) + PG attempt-path repair** | 4 (1.00) | 5 (0.75) | 5 (0.50) | 3 (0.45) | 3 (0.30) | 2 (0.16) | 2 (0.14) | 4 (0.40) | **3.70** |
| B | Learner analytics / insights | 4 (1.00) | 4 (0.60) | 4 (0.40) | 3 (0.45) | 4 (0.40) | 4 (0.32) | 4 (0.28) | 3 (0.30) | 3.75 |
| C | Mastery-aware Tutor 2.0 (richer multi-turn pedagogy) | 4 (1.00) | 4 (0.60) | 4 (0.40) | 5 (0.75) | 4 (0.40) | 3 (0.24) | 2 (0.14) | 4 (0.40) | **3.93** |
| D | Persisted mastery decay / confidence | 3 (0.75) | 4 (0.60) | 3 (0.30) | 4 (0.60) | 4 (0.40) | 4 (0.32) | 4 (0.28) | 3 (0.30) | 3.55 |
| E | Visual learning runtime completion | 3 (0.75) | 3 (0.45) | 4 (0.40) | 4 (0.60) | 4 (0.40) | 3 (0.24) | 3 (0.21) | 3 (0.30) | 3.35 |
| F | Spaced-repetition 2.0 (richer scheduler) | 3 (0.75) | 4 (0.60) | 3 (0.30) | 4 (0.60) | 5 (0.50) | 4 (0.32) | 3 (0.21) | 3 (0.30) | 3.58 |
| G | Plan/Goal/Path 2.0 (beyond P11 MVP) | 3 (0.75) | 3 (0.45) | 3 (0.30) | 5 (0.75) | 5 (0.50) | 4 (0.32) | 4 (0.28) | 3 (0.30) | 3.65 |
| H | UX completion niche (player→review, dead param cleanup) | 2 (0.50) | 2 (0.30) | 2 (0.20) | 5 (0.75) | 5 (0.50) | 5 (0.40) | 5 (0.35) | 2 (0.20) | 3.20 |
| I | Technical debt / hardening phase | 3 (0.75) | 2 (0.30) | 1 (0.10) | 5 (0.75) | 5 (0.50) | 3 (0.24) | 4 (0.28) | 1 (0.10) | 3.02 |
| J | Other (e.g. PG behavioral coverage CLI / migration-audit tool) | — | — | — | — | — | — | — | — | — |

**Ranked outcome:** C (3.93) > B (3.75) > A (3.70) > G (3.65) > F (3.58) > D (3.55) > E (3.35) > H (3.20) > I (3.02).

**Why the recommendation is A, not the numeric winner C:**
1. **C (Tutor 2.0) wins numerically because the tutor subsystem is architecturally complete** — but it is a *depth* enhancement to an already-working surface, carries the highest AI cost/reliability risk (Risk⁻¹=2, the model's lowest), and does **not** address the CRITICAL drift finding at all. It is the most defensible runner-up, not the best *next phase*.
2. **A closes the last explicitly-deferred NG from the P10/P11 contracts**, and this audit's empirical finding explains exactly *why* it was risky and how to do it safely: the attempt path must first be production-correct on PostgreSQL (P12-C0/C1), which is precisely the drift fix that the PG suite never catches. A thus converts the earlier "touching the attempt path is high risk" objection into the phase's first, bounded, additive work item.
3. **A is deterministic** (mastery-tuned ordering from stored `difficulty`/`bloom` columns + learner mastery budget, no AI) and thereby respects the no-ML mandate and avoids new AI cost.
4. A's repair prerequisite also de-risks the future analytics phase (B), which reads the same attempt rows.
5. **Portfolio value** — "adaptive assessment" is the platform's brand promise and the final closed loop signal a student-built production project can demo; Deterministic E2E-testable in the browser.

---

## 18. Recommended P12

**P12 — Genuine Adaptive Assessment (NG-4), with mandatory prerequisite: PostgreSQL attempt-path repair** (see `P12_SCOPE_AND_FOUNDATION.md`).

MVP shape (summary): (A1) additive schema-consistency migration + backfill for the two attempt tables + question-attempt column mappings + PG behavioral tests exercising the live `start_attempt`/`submit_answer` flow on migrated PG; (A2) deterministic adaptive delivery — mastery-tuned ordering/selection of the existing question bank per attempt (difficulty vs learner mastery budget, bloom-aware, `adaptive:true` metadata, deterministic scoring, optional resume); retire the dead VisualQuestion engine and orphaned schemas. No new AI provider, no RAG change, no framework change, no new scheduler.

---

## 19. Explicitly Rejected for P12

- **B Learner analytics as P12** — 2nd place; depends on the same attempt rows the drift breaks and adds less learner value than closing the last NG; better as the phase after A.
- **C Tutor 2.0 as P12** — highest raw score but depth-over-gap, highest AI cost/reliability risk, does not address the CRITICAL drift. Retained as main follow-up candidate.
- **D Persisted mastery decay** — educational MVP value is real but it mutates the core mastery invariant; prefer deterministic scheduling depth (F) later.
- **E Visual runtime completion** — real but narrow; animation/visual is not the product's highest-leverage gap.
- **F Spaced-repetition 2.0** — the scheduler just shipped (P10) and is integrated (P11); iterate only after adaptive assessment proves the difficulty signal.
- **G Plan/Goal/Path 2.0** — increment on a just-shipped phase; low marginal value now.
- **H UX completion niche** — cheap, useful, fold individual items into other phases; not a phase.
- **I Pure tech-debt/hardening phase** — the highest-urgency piece (drift) is already in-scope as A's C0/C1; a phase of *only* hardening does not advance the product narrative.
- **J Other directions** — none of the discovered extras (async-render offloading, Redis/Celery integration harness, migration-audit tooling) is worth a full phase on its own; the migration-audit/behavioral-coverage idea is subsumed by A1's PG behavioral tests.
- **AG-1..AG-11 (carried)**: React/Next.js migration; 2D content editor; microservices/vector-DB/pgvector; ML/DL learner model; autonomous agents/unrestricted AI chat; multi-tenancy/SSO/teacher platform; social collaboration; mobile app; new AI providers; large-scale infra rewrite; unrelated historical mypy debt — all still rejected unchanged.

---

## 20. Risks (P12)

| Risk | Mitigation |
|---|---|
| Drift fix touches transaction/security-sensitive attempt tables | Additive-only migration; PG behavioral tests as the gate; SQLite parity maintained; no rewrite of the scoring path |
| Adaptive ordering regresses P6 quiz UX | Keep all-question delivery as the default fallback; adaptivity is additive metadata + ordering; P6 full-loop E2E must stay green |
| "Adaptive" drifts into AI content generation (the dead engine's trap) | Deterministic-only MVP: stored difficulty/bloom ordering, no AI, no visual-question regeneration |
| Dead-engine confusion recurs | Explicitly retire `adaptive_assessment_engine.py`/`visual_question_generator.py` + orphaned schemas in scope |
| mypy floor | Zero-new policy; new files typed to match |
| Scope creep into analytics/hardening | Bound MVP to A1+A2; re-defer B/I after |

---

## 21. Final Architectural Decision

Proceed to **P12: Genuine Adaptive Assessment (NG-4) + mandatory PostgreSQL attempt-path repair**. Rationale (evidence): P11 closed NG-5 and is fully verified (1161/15/13, single head, clean tree). The last explicitly-deferred NG is NG-4. This audit empirically proved the assessment path is broken on migrated PostgreSQL (three failure classes, reproduced) — an invisible defect that a naive "un-stick the dead engine" phase would have tripped over. P12 therefore opens by making the drift fix + PG behavioral coverage a first-class checkpoint, then ships deterministic adaptive delivery on the repaired spine. It is additive, deterministic, browser-E2E-testable, and closes the product's core brand promise.