# Post-P9 Capability Matrix

**Phase:** P9 (Mastery Tutor Hardening & Semantic Grounding -- audit)
**Branch:** `feature/individual-user-foundation`
**Audited HEAD:** `d61da43`
**Status vocabulary:** VERIFIED / PARTIAL / MISSING / NOT VERIFIED / DEFERRED / OUT OF SCOPE
**Meaning:** **VERIFIED** = directly confirmed in this audit. **PARTIAL** = present but incomplete vs the vision. **MISSING** = absent. **NOT VERIFIED** = correctly described but not re-checked this pass. **DEFERRED** = planned for later. **OUT OF SCOPE** = explicitly excluded.

Production Confidence: **HIGH** (backend+frontend+browser verified, user-scoped, deterministic fallback), **MED** (backend verified, partial frontend/ops), **LOW** (stub/schema-only/missing).

---

## 1. Learner-Facing Capabilities

| Capability | Status | Backend | Frontend | Persistence | Security | Tests | Browser E2E | Production Confidence |
|---|---|---|---|---|---|---|---|---|
| Authentication (email + Google OAuth) | VERIFIED | `auth.py` | `signin.html` | users | JWT+Argon2+CSRF+Rotation-gap | yes (unit+int) | partial | HIGH |
| Presentation ingestion | VERIFIED | `presentations.py` + magic bytes | `upload.html` | presentations | ownership + size + magic | yes | yes | HIGH |
| Content extraction | VERIFIED | `content_extraction_service.py` | `processing.html` | content_units | ownership | yes | yes | HIGH |
| Lesson generation (AI) | VERIFIED | `lesson_generation_service.py` + Celery | `processing.html` | generated_lessons/blocks | ownership + idempotency | yes | yes | HIGH |
| Lesson player | VERIFIED | `player.py`, `lesson_player_service.py` | `player.html` | learning_sessions | ownership | yes | yes | HIGH |
| Visual learning (canvases/graph) | VERIFIED | `visual_canvases.py` | `player.html` | visual_* | ownership | yes | yes | HIGH |
| Learning sessions | VERIFIED | `player.py` | `player.html` | learning_sessions/activities | ownership | yes | yes | HIGH |
| Checkpoints | VERIFIED | `player.py` `/checkpoint` | `player.html` | session events | ownership | yes | yes | HIGH |
| Interactive quiz-taking | VERIFIED | `quiz_attempt_service.py` | `player.html` overlay | quiz_attempts/user_answers | sealed, no key leak | yes | yes | HIGH |
| Assessment / scoring | VERIFIED | `submit_quiz`, `_evaluate_answer` | `player.html` result | score_summaries | server-side grading | yes | yes | HIGH |
| Mastery | **PARTIAL** | `educational_memory_service.py` | dashboard + player sidebar | educational_memories | ownership | yes | yes | **MED** (static, no decay) |
| Recommendations | **PARTIAL** | `recommendation_engine.py` | dashboard cards (static) | (derived) | ownership | yes | yes | **MED** (not actionable) |
| Educational memory | VERIFIED | `educational_memory_service.py` | dashboard | educational_memories JSONB | ownership + cache | yes | yes | HIGH |
| Learner dashboard | **PARTIAL** | `learner_progress_service.py` | `dashboard.html` | read | ownership | yes | yes | **MED** (info-heavy) |
| Mastery-aware tutor | VERIFIED | `mastery_tutor_service.py` | `tutor.html` | tutor_sessions/convs/messages | ownership, rate-limited | yes | yes | HIGH |
| Semantic RAG | VERIFIED | `app.ai.retrieval` (P9) | tutor | chunk_embeddings | sealed ownership | yes (5) | **yes (`rag`)** | HIGH |
| Tutor persistence / session resume | VERIFIED | `tutor.py` F5 | `tutor.html` resume | tutor_* | ownership | yes | yes | HIGH |
| Remediation | **PARTIAL** | `tutor.remediate` | `tutor.html` | (reply) | ownership | yes (unit) | text-only | **MED** (stub, no loop) |
| Retention | **PARTIAL (ops)** | `enforce_retention` | -- | -- | -- | yes (3) | no | **LOW** (on-read only, unscheduled) |
| Spaced repetition / review scheduler | **MISSING** | schema/migration only | -- | -- | -- | no | no | **LOW** (unreachable) |
| Study plans / learning paths / goals | **MISSING** | schema/migration only | -- | -- | -- | no | no | **LOW** (unreachable) |
| Learner progress export | **MISSING** | `export_memory` no route | -- | -- | -- | no | no | LOW |
| Learner-facing analytics / trends | **MISSING** | raw data exists | dashboard trend (quiz only) | -- | ownership | partial | partial | MED |

---

## 2. Assessment Subsystem

| Capability | Status | Backend | Frontend | Persistence | Security | Tests | Browser E2E | Production Confidence |
|---|---|---|---|---|---|---|---|---|
| Question generation (AI) | VERIFIED | `quiz_generation_service.py` | player | questions/options/keys | ownership | yes | yes | HIGH |
| Attempt lifecycle | VERIFIED | `quiz_attempt_service.py` | player | quiz_attempts | ownership, resume, max-attempt | yes | yes | HIGH |
| Grading (MC/TF/MS/fill/order/match) | VERIFIED | `_evaluate_answer` | player | -- | server-side, no key leak | yes | yes | HIGH |
| Duplicate-submit protection | VERIFIED | status guard | -- | attempts | yes | yes | n/a | HIGH |
| Adaptive question selection | **MISSING** | `AdaptiveAssessmentEngine` dead code | -- | -- | -- | no | no | LOW |
| Question-level learner analytics | MISSING | QuestionAttempt rows only | -- | question_attempts | -- | no | no | MED |

---

## 3. Tutor & AI Subsystem

| Capability | Status | Backend | Frontend | Persistence | Security | Tests | Browser E2E | Production Confidence |
|---|---|---|---|---|---|---|---|---|
| Learner-scoped tutor | VERIFIED | `mastery_tutor_service.py` | `tutor.html` | tutor_sessions | ownership | yes | yes | HIGH |
| Semantic RAG grounding | VERIFIED | `app.ai.retrieval` | tutor | embeddings | sealed | yes (5) | yes (`rag`) | HIGH |
| Deterministic fallback (cold AI/RAG) | VERIFIED | positional + deterministic | tutor | messages | -- | yes | yes | HIGH |
| Session resume / history | VERIFIED | `tutor.py` F5 | resume panel, `?session=` | tutor_* | ownership | yes | yes | HIGH |
| Remediation (structured, re-practice) | MISSING | text only today | -- | -- | -- | no | no | LOW |
| Mastery-aware grounding (uses memory + weak picks) | VERIFIED | `_build_context` | `?concept=` | -- | ownership | yes | yes | HIGH |
| Bounded context / history | VERIFIED | F4 | -- | messages | bounded | yes | yes | HIGH |

---

## 4. Learner Intelligence

| Capability | Status | Detail |
|---|---|---|
| Mastery scoring | VERIFIED | scalar assigned from quizzes; avg per concept |
| Weak/developing/mastered detection | VERIFIED | thresholds 50 / 85 |
| Mastery decay / review spacing | **MISSING** | no half-life/decay anywhere |
| Confidence score | MISSING | field defaults 0.5, never updated |
| Next-best-action | PARTIAL | rule table; not actionable in UI |

---

## 5. Cross-Cutting

| Capability | Status | Evidence |
|---|---|---|
| PostgreSQL support | VERIFIED | 15 PG tests, PortableJSONB, migrations on real PG |
| Security isolation (user) | VERIFIED | ownership chain sealed; no CRITICAL |
| Rate limiting | VERIFIED | middleware + per-route (tutor 20/60) |
| AI provider abstraction | VERIFIED | `AIContentService` mandatory |
| Embedding provider abstraction | VERIFIED | registry + local provider |
| Observability | PARTIAL | Prometheus metrics, health, logs; no per-route/AI/retention dashboards |
| Browser acceptance (E2E) | VERIFIED | P7 dashboard, P8 tutor, P9 real-RAG |
| mypy gate | PARTIAL | 83 errors flat (zero-new policy) |
| Alembic single head | VERIFIED | `0030_tutor_conversation_index` |
| CI | VERIFIED | GitHub Actions (lint/unit/int/migration/mypy/docker/secret-scan) |
