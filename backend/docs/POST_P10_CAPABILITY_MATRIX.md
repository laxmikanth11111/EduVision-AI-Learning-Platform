# Post-P10 Capability Matrix

**Phase:** P10 (Adaptive Remediation & Review Engine — audit)
**Branch:** `feature/individual-user-foundation`
**Audited HEAD:** `aa2da2f`
**Status vocabulary:** COMPLETE / PARTIAL / BACKEND ONLY / FRONTEND ONLY / STUB / UNUSED / BROKEN / DEFERRED / NOT IMPLEMENTED
**Meaning:** **COMPLETE** = directly confirmed end-to-end (backend + frontend + browser where applicable). **PARTIAL** = present but incomplete vs the vision. **BACKEND ONLY** = API/service tested server-side but not wired to a browser surface (or no E2E). **STUB** = container/schema exists but no real behaviour. **UNUSED** = fully implemented but orphaned/dead. **DEFERRED** = planned for a later phase. **NOT IMPLEMENTED** = absent.

Production Confidence: **HIGH** (backend+frontend+browser verified, user-scoped, deterministic fallback), **MED** (backend verified, partial frontend/ops), **LOW** (stub/orphan/missing).

---

## 1. Learner-Facing Capabilities

| Capability | Status | Backend | Frontend | Persistence | Security | Tests | Browser E2E | Production Confidence |
|---|---|---|---|---|---|---|---|---|
| Authentication (email + Google OAuth) | COMPLETE | `auth.py` | `signin.html`/`signup.html` | users | JWT+Argon2+CSRF+rotation-gap(MED) | yes | yes | HIGH |
| Presentation ingestion | COMPLETE | `presentations.py` + magic-byte | `upload.html` | presentations | ownership+size+magic | yes | yes | HIGH |
| Content extraction | COMPLETE | `content_extraction_service.py` | `processing.html` | content_units | ownership | yes | yes | HIGH |
| Lesson generation (AI) | COMPLETE | `lesson_generation_service.py` + Celery | `processing.html` | generated_lessons/blocks | ownership+idempotency | yes | yes | HIGH |
| Lesson player | COMPLETE | `player.py`, `lesson_player_service.py` | `player.html` | learning_sessions | ownership | yes | yes | HIGH |
| Visual learning (canvases/SVG strategies) | COMPLETE | `visual_canvases.py` | `player.html` | visual_* | ownership | yes | yes | HIGH |
| Animation/simulation/video learning | **BACKEND ONLY / PARTIAL** | routers+services (unit-tested) | `player.html` wires 4 of 15 routes | — | ownership | yes (unit) | **no E2E** | MED |
| Learning sessions | COMPLETE | `player.py` | `player.html` | learning_sessions/activities | ownership | yes | yes | HIGH |
| Checkpoints | COMPLETE | `player.py` `/checkpoint` | `player.html` | session events | ownership | yes | yes | HIGH |
| Interactive quiz-taking | COMPLETE | `quiz_attempt_service.py` | `player.html` overlay | quiz_attempts/user_answers | sealed, no key leak | yes | yes | HIGH |
| Assessment / scoring | COMPLETE | `submit_quiz`, `_evaluate_answer` | `player.html` result | score_summaries | server-side grading | yes | yes | HIGH |
| Mastery | **PARTIAL** | `educational_memory_service.py` (public-ID keyed, P10) | dashboard + player sidebar | educational_memories | ownership | yes | yes | MED (scalar, no persisted decay/confidence) |
| Next-action / CTA | **COMPLETE (P10)** | `next_action` computed field + `lesson_id` | `player.html` `lj-take` CTA, quiz result | (derived) | ownership | yes | **yes (NG-1)** | HIGH |
| Recommendations | **COMPLETE (P10)** | `recommendation_engine.py` | dashboard `recoAction` clickable cards | (derived) | ownership | yes | **yes (NG-2)** | HIGH |
| Review scheduling (spaced repetition) | **COMPLETE (P10)** | `review_scheduler.py`, `review_schedule_service.py` | dashboard review panel | review_schedules (0011+0031) | ownership | yes | **yes (NG-2/3)** | HIGH |
| Mastery decay / review-pressure signal | PARTIAL | `compute_decay_signal` (ranking only) | priority badges | no-mutation | owner-scoped | yes (unit) | yes (visual) | MED |
| Educational memory | COMPLETE | `educational_memory_service.py` | dashboard | educational_memories JSONB | ownership+cache | yes | yes | HIGH |
| Learner dashboard | COMPLETE | `learner_progress_service.py` | `dashboard.html` | read | ownership | yes | yes | HIGH |
| Mastery-aware tutor | COMPLETE | `mastery_tutor_service.py` | `tutor.html` | tutor_sessions/convs/messages | ownership, rate-limited | yes | yes | HIGH |
| Semantic RAG | COMPLETE | `app.ai.retrieval` (P9) | tutor chips | chunk_embeddings | sealed ownership | yes (5) | **yes (`rag`)** | HIGH |
| Tutor persistence / session resume | COMPLETE | `tutor.py` (P9 F5) | `tutor.html` resume/`?session=` | tutor_* | ownership | yes | yes | HIGH |
| Remediation + re-practice | **COMPLETE (P10)** | `remediate` + structured `next_action` | `tutor.html` practice CTA | (messages) | ownership | yes | **yes (NG-3)** | HIGH |
| Retention | **PARTIAL (ops)** | `enforce_retention` (on-read only) | — | — | — | yes (3) | no | LOW (unscheduled) |
| Spaced review reachable in browser | **COMPLETE (P10)** | `GET/POST /me/review/*` | dashboard panel | review_schedules | ownership | yes | yes | HIGH |
| Study plans / learning paths / goals | **NOT IMPLEMENTED** | tables(0011)+enums(`shared/constants`)+schemas(`personalization.py`) orphaned; no service/router | — | — | n/a | no | no | LOW |
| Learner progress export | NOT IMPLEMENTED | `export_memory` no route | — | — | — | no | no | LOW |
| Learner-facing analytics / insights | NOT IMPLEMENTED | orphaned `analytics*.py` schemas + unused analytics tables | dashboard trend (quiz only) | — | ownership | partial | partial | MED |

---

## 2. Assessment Subsystem

| Capability | Status | Backend | Frontend | Persistence | Security | Tests | Browser E2E | Production Confidence |
|---|---|---|---|---|---|---|---|---|
| Question generation (AI) | COMPLETE | `quiz_generation_service.py` | player | questions/options/keys | ownership | yes | yes | HIGH |
| Attempt lifecycle (start/list/submit) | COMPLETE | `quiz_attempt_service.py` | player overlay | quiz_attempts | ownership, resume, max-attempt | yes | yes | HIGH |
| Grading (MC/TF/MS/fill/order/match) | COMPLETE | `_evaluate_answer` | player | — | server-side, no key leak | yes | yes | HIGH |
| Duplicate-submit protection | COMPLETE | status guard | — | attempts | yes | yes | n/a | HIGH |
| Adaptive question selection | **NOT IMPLEMENTED** | `AdaptiveAssessmentEngine` UNUSED (dead); delivery fixed-order | — | — | — | no | no | LOW |
| Attempt result → next-action | **COMPLETE (P10)** | `AttemptResult.lesson_id` + `next_action` | `player.html` CTA | — | ownership | yes | yes (NG-1) | HIGH |
| Question-level learner analytics | NOT IMPLEMENTED | QuestionAttempt rows only | — | question_attempts | — | no | no | MED |

---

## 3. Tutor & AI Subsystem

| Capability | Status | Backend | Frontend | Persistence | Security | Tests | Browser E2E | Production Confidence |
|---|---|---|---|---|---|---|---|---|
| Learner-scoped tutor | COMPLETE | `mastery_tutor_service.py` | `tutor.html` | tutor_sessions | ownership | yes | yes | HIGH |
| Semantic RAG grounding | COMPLETE | `app.ai.retrieval` | tutor chips | embeddings | sealed | yes (5) | yes (`rag`) | HIGH |
| Deterministic fallback (cold AI/RAG) | COMPLETE | positional + deterministic | tutor | messages | — | yes | yes | HIGH |
| Session resume / history | COMPLETE | `tutor.py` F5 | resume panel, `?session=` | tutor_* | ownership | yes | yes | HIGH |
| Remediation (structured, re-practice) | **COMPLETE (P10)** | `remediate` + `_remediate_next_action` | practice CTA | messages | ownership | yes | yes (NG-3) | HIGH |
| Mastery-aware grounding | COMPLETE | `_build_context` (+weak picks) | `?concept=` | — | ownership | yes | yes | HIGH |
| Bounded context / history | COMPLETE | F4 (`TUTOR_MAX_HISTORY_MESSAGES`; assistant hardcodes 20 — LOW) | — | messages | bounded | yes | yes | HIGH |
| Retention worker (scheduled/global) | NOT IMPLEMENTED | no beat task | — | — | — | no | no | LOW |

---

## 4. Learner Intelligence

| Capability | Status | Detail |
|---|---|---|
| Mastery scoring | COMPLETE | scalar from quizzes; avg per concept; **public-ID keyed (P10)** |
| Weak/developing/mastered detection | COMPLETE | thresholds 50 / 85 (shared) |
| Review scheduling | **COMPLETE (P10)** | interval ladder 1/3/7/14d; weak starts tightest; success advances; skip-pauses; lazy seeding; due queue indexed |
| Decay / pressure signal | PARTIAL | ranking-only (`compute_decay_signal`); does NOT mutate persisted mastery |
| Confidence score | NOT IMPLEMENTED | field defaults 0.5, never updated |
| Recommendations (actionable) | **COMPLETE (P10)** | rule table + lesson public-id deep-links |
| Study plans / goals / learning paths | **NOT IMPLEMENTED (NG-5)** | tables/enums/schemas present, orphaned |

---

## 5. Cross-Cutting

| Capability | Status | Evidence |
|---|---|---|
| PostgreSQL support | COMPLETE | P10 report: 15 PG tests; PortableJSONB; migrations on real PG |
| SQLite test path | COMPLETE | 1144 passed (re-verified this pass) |
| Security isolation (user) | COMPLETE | ownership chain sealed; no CRITICAL; isolation 22 pass re-verified |
| Rate limiting | COMPLETE | middleware + per-route (tutor 20/60) |
| AI provider abstraction | COMPLETE | `AIContentService` mandatory; registry local/openai/gemini |
| Embedding provider abstraction | COMPLETE | registry incl. local deterministic |
| Observability | PARTIAL | Prometheus metrics, health, logs, masking; no per-route/AI/retention dashboards |
| Browser acceptance (E2E) | COMPLETE | P6/P7/P8/P10 suites (12 tests across 6 files); P10 3 pass re-verified |
| mypy gate | PARTIAL | 83/24 flat (zero-new policy) |
| Alembic single head | COMPLETE | `0031_review_schedule_concept` (re-verified) |
| CI | COMPLETE | GitHub Actions (lint/unit/int/migration/mypy/docker/secret-scan) |
| Animation/video runtime frontend wiring | PARTIAL | video runtime routes backend-only (0/5 wired) |
| Study plans/goals/paths | **NOT IMPLEMENTED** | NG-5 |

---

## 6. Phase-Inheritance Summary

| Earlier phase | Delivered (INHERITED) | Status this audit |
|---|---|---|
| P0–P4 | Stack, RAG vector, AIContentService, caches, CI | INHERITED |
| P5 | Learner-journey panel + per-user progress | INHERITED |
| P6 | Interactive quiz complete loop | INHERITED |
| P7 | Learner progress dashboard + browser E2E | INHERITED |
| P8 | Mastery-aware AI tutor + deterministic remediation | INHERITED |
| P9 | Real semantic RAG, retention, resume UI, index parity | INHERITED |
| **P10** | **Review scheduler, review API/UI, actionable reco + next-action, mastery public-ID keying, decay signal, closed loop** | **COMPLETE (this audit)** |

---

## Summary of Greatest P11-Relevant Deltas
1. **NG-5 (HIGH): Study plans / learning goals / learning paths are not implemented** — the exact tables (migration `0011`), enums (`shared/constants`), and request/response schemas (`personalization.py`) already exist but are orphaned; `review_schedules` is now live (P10) and can anchor a daily plan. Highest-value, most leveraged next capability.
2. **NG-4 (MEDIUM): Genuine adaptive assessment is not implemented** — dead `AdaptiveAssessmentEngine`; question delivery is fixed-order. Strong #2 alternative (difficulty fields already in `quiz`/`quiz_content`).
3. **G7 (MEDIUM): Learner-facing analytics** — orphaned analytic schemas/tables; dashboard trend only.
4. **G6 (MEDIUM): Video runtime wiring** — bookmark/assessment/tutor-context endpoints are backend-only (0/5 wired from `player.html`).
5. **G8 (MEDIUM): Retention not scheduled globally.**
6. **G3/G4/G5 (LOW): persisted mastery never decays; player lacks a review-queue entry point; review scheduling is lazy (not immediate on submit).**