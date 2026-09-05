# Post-P12 Capability Matrix — EduVision AI

**Phase:** Post-P12 audit (HEAD `623c43f`)
**Companion:** `POST_P12_PRODUCT_ARCHITECTURE_AUDIT.md`, `P13_SCOPE_AND_FOUNDATION.md`
**Convention:** COMPLETE (implemented + wired + tested + persisted) · PARTIAL (implemented but incomplete/wiring gap) · MISSING (not implemented / orphaned) · BROKEN (fails at runtime) · DEFERRED (explicitly out of scope)

## CONTENT

| Capability | Status | Evidence | Phase | Remaining Gap | Priority |
|---|---|---|---|---|---|
| Upload (file / topics) | COMPLETE | `upload.html`, `presentations.py`, `_read_upload_bounded`; `test_upload_validation.py` | P1–P4 | — | — |
| Extraction | COMPLETE | `content_extraction_service.py`, processing page | P4 | AI retry | LOW |
| Presentation | COMPLETE | `presentations.py`, folders/tags/versions | P1–P4 | — | — |
| Lesson generation | COMPLETE | `lesson_generation_service.py` + Celery; `lessons.generate` | P4/P5 | — | — |
| Topic structure | COMPLETE | `topic_outline_service.py`; topic outlines | P4 | — | — |
| Visual learning (SVG strategies) | COMPLETE | `visual_canvases.py`; player SVG renderers | P5/P6 | — | — |
| Motion / animation | PARTIAL | player Motion Engine v2 uses `/animations/plan` + `/animations/runtime/sync`; `classify` + 5 GET blueprint routes unwired | P5 | narrow wiring | MEDIUM |
| Simulation | PARTIAL | player uses definitions/start/step; parameters/playback/reset backend-only | P5 | control surface unwired | MEDIUM |
| Video generation | PARTIAL | `video_router`, `video_composition_service`; player `/videos/create` | P5 | render synchronous in request path | HIGH |
| Video runtime | MISSING | `video_runtime_router.py` (bookmark/assessment/tutor-context) in-memory, zero frontend callers | P5 | frontend wiring | MEDIUM |

## LEARNING

| Capability | Status | Evidence | Phase | Remaining Gap | Priority |
|---|---|---|---|---|---|
| Lesson player | COMPLETE | `player.html`, `player.py`; P6/P10 E2E | P5 | player has no exit to dashboard/plan/review (hub dead end) | MEDIUM |
| Learner journey | COMPLETE | `player.html` `#ljPanel`, `learning_sessions`; E2E | P5 | — | — |
| Progress | COMPLETE | `learner_progress_service`, `GET /me/progress`; P7 E2E | P7 | — | — |
| Mastery | COMPLETE | `educational_memory_service` (bands, BoundedCache 5000/1800); P10 NG-3 | P7/P10 | decay not persisted | MEDIUM |
| Recommendations | COMPLETE | `recommendation_engine` (50/85/95); `recoAction()`; P10 NG-2 | P7/P10 | — | — |
| Review scheduling | COMPLETE | `review_scheduler` 1/3/7/14, `review_schedule_service`, due queue ≤200; P10 | P10 | lazy seed / on-read retention | LOW |
| Review queue | COMPLETE | `GET /me/review` + complete/skip; dashboard panel | P10 | player entry missing | LOW |
| Today Plan | COMPLETE | `study_plan_service`, `/me/plan/today`; P11 E2E | P11 | — | — |
| Goals | COMPLETE | `learning_goal_service`, derived progress; P11 E2E | P11 | — | — |
| Learning Path | COMPLETE | `learning_path_service`, `/me/path`; P11 E2E | P11 | — | — |
| Tutor | COMPLETE | `mastery_tutor_service`, multi-turn RAG; P8/P9 | P8/P9 | depth (Tutor 2.0) deferred | LOW |
| RAG | COMPLETE | `semantic_retrieve_chunks`, learner-scoped; P8 | P4/P8/P9 | RRF/MMR fusion inert (DEFERRED) | MEDIUM |
| Remediation | COMPLETE | `remediate()` + next_action; practice CTA; P10 | P8/P10 | CTA suppressed if lesson_id missing | LOW |

## ASSESSMENT

| Capability | Status | Evidence | Phase | Remaining Gap | Priority |
|---|---|---|---|---|---|
| Quizzes | COMPLETE | `quiz` models/repo, versions | P6 | — | — |
| Attempts | COMPLETE (PG-fixed) | `start_attempt`, migrations 0032/0033, PG behavioral suite | P6/P12 | — | — |
| Question attempts | COMPLETE (PG-fixed) | `QuestionAttempt` mapping, PG suite | P6/P12 | `feedback` column never populated by service | LOW |
| Scoring | COMPLETE | `_evaluate_answer`, `ScoreSummary`; P6/P12 | P6 | — | — |
| Adaptive assessment (NG-4) | COMPLETE | `adaptive_assessment.py` deterministic; `adaptive` badge; P12 unit+PG+E2E | P12 | inter-attempt adaptation deferred | MEDIUM |
| Difficulty adaptation | COMPLETE (ordering) | per-band target; within-attempt +1/−1 | P12 | beyond-ordering adaptation deferred | MEDIUM |
| Bloom adaptation | COMPLETE (ordering) | `bloom_rank` tie-break | P12 | — | — |
| Within-attempt adaptation | COMPLETE | `/next` server-chosen; E2E Scenario A/B | P12 | async `/next` player race (flakiness) | MEDIUM |
| Assessment → mastery | COMPLETE | `_update_concept_mastery` public-ID keyed; P10/P12 | P10/P12 | — | — |

## LEARNER INTELLIGENCE

| Capability | Status | Evidence | Phase | Remaining Gap | Priority |
|---|---|---|---|---|---|
| Mastery | COMPLETE | `educational_memory_service` | P7/P10 | decay not persisted | MEDIUM |
| Weak concepts | COMPLETE | mastery bands <50; chips + tutor link | P7/P10 | — | — |
| Strong concepts | COMPLETE | ≥85 bands; pass-through | P7 | — | — |
| Review pressure | COMPLETE | `compute_decay_signal` ranking/annotation | P10 | not persisted | MEDIUM |
| Next action | COMPLETE | next_action + deep-links; P10 | P10 | — | — |
| Remediation | COMPLETE | `remediate()` | P8/P10 | — | — |
| Plans / Goals / Paths | COMPLETE | P11 services + E2E | P11 | — | — |
| Tutor context | COMPLETE | learner-scoped RAG + mastery | P8/P9 | self-only injection guard unconsumed (HIGH carried) | MEDIUM |

## ANALYTICS

| Capability | Status | Evidence | Phase | Remaining Gap | Priority |
|---|---|---|---|---|---|
| Learner progress | COMPLETE | `get_progress` composition; dashboard | P7 | — | — |
| Attempt history | PARTIAL | `_attempt_history` (recent 10) | P7 | shallow; not analytics-grade | MEDIUM |
| Trends | PARTIAL | `_build_trend` (10 pts) on dashboard | P7 | thin trend only | MEDIUM |
| Concept analytics | MISSING | no per-concept trajectory surface | — | G-1 (P13) | HIGH |
| Longitudinal learning analytics | MISSING | analytics models/tables orphaned (`analytics.py`) | — | G-1 (P13) | HIGH |
| Teacher analytics | MISSING | `SystemAnalytics`/creator snapshots orphaned | — | DEFERRED | LOW |

## PLATFORM

| Capability | Status | Evidence | Phase | Remaining Gap | Priority |
|---|---|---|---|---|---|
| PostgreSQL | COMPLETE (assessment spine) | PG 19 passed incl. adaptive persistence | P2/P12 | shallow coverage past assessment tables | LOW |
| SQLite | COMPLETE | 1183 passed | P1+ | — | — |
| Redis | PARTIAL | JTI revoke, rate-limit Lua, OAuth state; mocks-only tests | P2/P3 | no functional integration test | MEDIUM |
| Celery | PARTIAL | export + RAG tasks; mocks-only tests; video render NOT delegated | P4 | functional test; render offload | HIGH |
| Storage | COMPLETE | prefix-locked owned paths, magic-byte validation | P1–P3 | — | — |
| Authentication | COMPLETE | Argon2id, JWT, cookies | P1 | refresh rotation lacks old-token revoke; stateless access (carried) | MEDIUM |
| Authorization | COMPLETE | 404-equalized ownership; isolation suites | P1+ | — | — |
| Observability | COMPLETE | `/api/v1/metrics` incl. `p12_*`, `p11_*` | P3/P10/P11/P12 | — | — |
| Health checks | COMPLETE | `/api/v1/health` | P1 | — | — |
| Migrations | COMPLETE | single head `0033_educational_memories`; additive | P2/P12 | — | — |
| CI | COMPLETE | ruff/mypy/pytest gates | P1 | no live broker test | MEDIUM |
| Security | COMPLETE | authN/Z/ownership/upload/rate-limit | P1+ | `.env` creds + rate-limit whitelist path (carried) | MEDIUM |

## Summary

- **Fully COMPLETE spine (PG-correct after P12):** Learn → Assess (adaptive) → Mastery → Recommend → Review → Plan/Goal/Path → Tutor → Next-action.
- **Largest MISSING capability:** learner analytics / trajectory (concept trajectory, longitudinal learning analytics) — the orphaned `analytics.py` surface. **P13 target.**
- **PARTIAL infrastructure:** video render in request path (HIGH), animation/simulation/video runtime wiring, Redis/Celery functional test, RAG fusion.
- **DEFERRED (carried):** Tutor 2.0, Adaptive 2.0 (inter-attempt/IRT), mastery decay persistence, retention automation, RAG fusion, classroom/teacher platform, framework migration, microservices, vector-DB, ML/DL, mobile, new AI providers.
