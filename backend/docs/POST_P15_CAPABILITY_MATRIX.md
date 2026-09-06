# Post-P15 Capability Matrix

**Branch:** `feature/individual-user-foundation` · **Baseline:** `e81a61a` (P15, release-gated)
**Date:** 2026-09-06 · Statuses: `COMPLETE` `PARTIAL` `MISSING` `DEFERRED` `CARRIED`

| # | Capability | Status | Evidence (backend/app unless noted) | Notes / next phase |
|---|------------|--------|-------------------------------------|--------------------|
| 1 | Learner authentication (email + JWT cookies) | COMPLETE | `api/v1/auth.py`; `core/security.py`; `models/user.py` | 15-min access / 7-day refresh, Secure+Lax HttpOnly cookies. Dev signing key is the hardcoded default (CARRIED). |
| 2 | OAuth (Google) sign-in + account linking | COMPLETE | `auth.py:267-352` | Same-email Google identity links onto the existing password account via `users.google_id` (no orphan duplicate). Residual: trusts Google unverified email. |
| 3 | Refresh-token reuse protection | PARTIAL → CARRIED | `auth.py` `_revoked_refresh_jtis`, `core/security.py:112-127` | Logout revocation works; **no rotation/reuse-detection** — un-revoked token valid 7 days. |
| 4 | Rate limiting | PARTIAL → CARRIED | `middleware/rate_limit.py:157-211` | Enabled app-wide incl. auth but **fails open** on Redis outage/exception; loopback whitelisted in dev. |
| 5 | CSRF protection | MISSING → CARRIED | `core/security.py:138-143` (dead helpers), `main.py:117-153` (no middleware) | `generate/validate_csrf_token` and `CSRF_*` settings unconsumed; only SameSite=Lax mitigation. |
| 6 | Content upload / storage | COMPLETE | `api/v1/storage.py`, `presentations.py`, STORAGE_PROVIDER local/S3 seam | Uploads drive presentation/lesson generation. |
| 7 | Presentation/lesson pipeline (slide decks) | COMPLETE | `api/v1/presentations.py`; `services/lesson_generation*` | Learners create decks NA; AI lesson generation backgrounded. |
| 8 | Slide player + resume (P15) | COMPLETE | `api/v1/player.py`; `services/learning_session_service.py`; `frontend/player.html` | `p15_position_updates_total`, `lesson_resume_restored`; dashboard resume links. |
| 9 | Adaptive assessment (P12) | COMPLETE | `services/adaptive_assessment.py`; `api/v1/quiz.py`; migration 0032 | Deterministic selector, persisted banks, in-attempt ±1 reaction, PG/E2E covered. |
| 10 | Assessment 2.0 (skills / early exit / time / confidence) | DEFERRED | `questions.meta` JSONB holds unused `tags`/`knowledge_area` | Matrix-8/Multi-skill, stopping rules, pacing, confidence dial — future phase. |
| 11 | Learner analytics (P13) | COMPLETE | `api/v1/analytics.py`; `services/learner_analytics_service.py`; `frontend/dashboard.html` | On-the-fly; **analytics ORM models have no migration** (CARRIED MED). |
| 12 | Mastery memory (P10) | COMPLETE | `models/educational_memory.py`; `services/educational_memory_service.py`; migration 0033 | Per-concept JSON; single writer = quiz feedback. |
| 13 | Spaced review scheduling (P14) | COMPLETE | `models/review_schedule.py`; `services/review_scheduler.py`, `retention.py`; `api/v1/review.py` | Deterministic ladder (1,3,7,14) + 4-outcome modulation; `review_schedules` durable. |
| 14 | Retention automation (background scheduling/reminders) | MISSING → DEFERRED | beat schedule `workers/celery_app.py:69-106` has no review task | No sweeper, no reminders, no push; learner-driven only. Future phase. |
| 15 | Tutor / RAG (P4/P7/P8) | PARTIAL | `api/v1/tutor.py`; `services/mastery_tutor_service.py`; `ai/retrieval.py` | Persisted sessions + learner-scoped retrieval + offline fallback. See #16–18. |
| 16 | Tutor streaming (SSE) | MISSING → DEFERRED | `ai/service.py:176` stream exists; tutor is request/response | Frontend has no `EventSource`; deferred. |
| 17 | Tutor citations / groundedness metadata | MISSING → DEFERRED | `tutor_citations`-style tables exist schema-only; attribution is free-text | 9 auxiliary tables un-consumed; defer. |
| 18 | Prompt-injection guardrail | MISSING → CARRIED | `TUTOR_INJECTION_FLAG_THRESHOLD` (`core/config.py:238`) zero consumers | Inert since P12; defer (future phase or security sprint). |
| 19 | Tutor session resume (browser) | PARTIAL → BUG | `frontend/tutor.html:resumeSession()` passes session id where conversation id expected | History reload breaks across page loads; fix belongs to Tutor 2.0 phase. |
| 20 | Study plans / goals / paths (P11) | COMPLETE | `api/v1/plan.py`, `goals.py`, `path.py`; `services/study_plan_service.py` | Deterministic Today plan includes due reviews. |
| 21 | Animation / simulation / visual canvases | COMPLETE | `api/v1/animation*.py`, `simulation.py`, `visual_canvases.py` | Isolation-tested domains. |
| 22 | Video project lifecycle (create/render/watch) | **PARTIAL → P16** | `api/v1/video_router.py`; `services/video_renderer_service.py` | **No persistence (in-memory cache), sync blocking render in async handlers, fabricated data on cache miss, zero tests, no browser UI.** See #23–#26. |
| 23 | Async render (off event loop) | MISSING → **P16** | `video_renderer_service.py:119,133,146,170` blocking `subprocess.run` | P16 executor seam (inline/Celery) + Celery task + state machine. |
| 24 | Persistent video projects | MISSING → **P16** | `video_router.py:35-37` BoundedCache only | P16 adds `video_projects` table (migration 0034) + repository + service. |
| 25 | Render concurrency / ownership / timeout control | MISSING → **P16** | no bounds today | P16 per-user cap (409), 404-equalized ownership, terminal statuses + error. |
| 26 | Video browser UI | MISSING → **P16** | no `frontend/videos.html` | P16 vanilla-JS page: list, statuses, render, watch via `/uploads/videos/…`. |
| 27 | Rendering test coverage | MISSING → **P16** | zero renderer tests; 1,257 committed `.mp4` under `uploads/` | P16 unit/integration/PG/E2E coverage; mock render backend for determinism. |
| 28 | Media `/uploads` serving | COMPLETE (deliberately public) | `main.py:181-183`; `tests/integration/test_uploads_mount.py` | Public playable media contract; access policy hardening CARRIED. |
| 29 | Background workers / Celery | COMPLETE | `workers/tasks.py`, `rag_tasks.py`, `celery_app.py` | DLQ + idempotency + beat; tested via `task.run.__func__`. |
| 30 | Observability / metrics | COMPLETE | `observability/metrics.py`, `api/v1/metrics.py` | Counters/gauges/histograms (P11–P15 families live). |
| 31 | Health/readiness | COMPLETE | `api/v1/health.py` | DB + Celery ping + storage checks. |
| 32 | PostgreSQL parity | COMPLETE | `tests/postgres/` + migrations up to 0033 | Fresh-PG parity verified to P15; P16 adds 0034 parity tests. |

**P16 candidate weighted score** (weights: learner value 15, product impact 12, gap
severity 12, loop closure 10, arch readiness 10, data reuse 10, browser 8, prod
readiness 8, security 5, performance 5, AI risk 3, complexity 2):

| Candidate | Score |
|-----------|-------|
| **A — Video Learning Runtime (async/persistent/concurrency-bounded)** | **83** |
| C — Tutor/RAG 2.0 (streaming + citations + guardrail + resume fix) | 77 |
| B — Adaptive Assessment 2.0 (skills / early-exit / time / confidence) | 76 |
| D — Retention Automation (sweeper, reminders) | 63 |
| E — Mastery/Retention Intelligence (adaptive intervals) | 61 |
| H — Production Reliability bundle (CSRF, fail-closed rate limit, JTI reuse) | 57 |
| G — Study Plans / Goals 2.0 | 56 |
| F — Learning Workspace 2.0 (dashboard consolidation) | 49 |
| J — Content Intelligence (multi-format lesson generation) | 44 |

**P16 = A — Video Learning Runtime.** One primary capability per phase; the carried
HIGH (blocking render) and carried MED data-integrity defect are both within its
scope. All other rows remain in the matrix for future phases.