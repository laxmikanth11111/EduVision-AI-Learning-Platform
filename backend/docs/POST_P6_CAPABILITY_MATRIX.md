# Post-P6 Capability Matrix

Status vocabulary used (no vague terms):
VERIFIED · INHERITED · PARTIAL · NOT VERIFIED · MISSING · DEFERRED · REGRESSION · OUT OF SCOPE

Evidence column cites the file/path or test observed in the repository at the
post-P6 checkpoint (`8c82a2c`). "Browser-verified" means confirmed by the
browser E2E suites (`tests/e2e/`).

---

## A. Lesson / Content

| Capability | Status | Evidence | User Value | Tech Readiness | Security | Persistence | Browser Verified | Missing Pieces | Candidate Phase |
|---|---|---|---|---|---|---|---|---|---|
| Presentation ingestion | VERIFIED | parsers/, uploads/, presentations router | High | High | Ownership | YES | YES | — | — |
| PPT extraction | VERIFIED | parsers/ | High | High | Ownership | YES | YES | — | — |
| Topic generation | VERIFIED | topic_outline_service, lesson_generation | High | High | Ownership | YES | partial | — | — |
| Lesson generation | VERIFIED | lesson_generation_service + worker | High | High | Ownership | YES | YES | — | — |
| Explanation content | VERIFIED | generated_lesson/version/block | High | High | Ownership | YES | YES | — | — |
| Visual content | VERIFIED | visual_* services + routers | High | High | Ownership | YES | partial | richer interactivity | Defer (C) |
| Lesson sequencing | VERIFIED | player slides/topics | High | High | Ownership | YES | YES | — | — |
| Lesson progress | VERIFIED | LearningSession, journey bar | High | High | Ownership | YES | YES | cross-lesson view | **P7** |
| Resume capability | VERIFIED | LearningSession restore; P6 E2E | High | High | Ownership | YES | YES | — | — |

## B. Assessment

| Capability | Status | Evidence | User Value | Tech Readiness | Security | Persistence | Browser Verified | Missing Pieces | Candidate Phase |
|---|---|---|---|---|---|---|---|---|---|
| Quiz generation | VERIFIED | quiz_generation_service, quiz router | High | High | Ownership | YES | partial | — | — |
| Quiz publishing | VERIFIED | quiz_version/content models | High | High | Ownership | YES | — | — | — |
| Quiz checkpoint | VERIFIED | player.py `/checkpoint`; journey chip | High | High | Ownership | YES | YES | — | — |
| Attempt creation | VERIFIED | quiz_attempt_service; P6 result | High | High | Ownership | YES | YES | — | — |
| Answer submission | VERIFIED | submit quiz; P6 E2E | High | High | Ownership | YES | YES | — | — |
| Scoring | VERIFIED | percent_score | High | High | Ownership | YES | YES | — | — |
| Feedback (per-question) | VERIFIED | results review, question_explanation | Medium-High | High | Ownership | YES | YES | — | — |
| Attempt history | VERIFIED | list-attempts user-scoped | Medium-High | High | Ownership | YES | partial | dashboard view | **P7** |
| Retakes | VERIFIED | available_attempts | Medium-High | High | Ownership | YES | YES | — | — |
| Question-level performance | VERIFIED | question_attempt | Medium-High | High | Ownership | YES | NO | surfaced in dashboard | **P7** |
| Mastery update | VERIFIED | educational_memory_service; P6 C4 | High | High | Ownership | YES | YES | — | — |

## C. Learner Intelligence

| Capability | Status | Evidence | User Value | Tech Readiness | Security | Persistence | Browser Verified | Missing Pieces | Candidate Phase |
|---|---|---|---|---|---|---|---|---|---|
| Educational memory | VERIFIED | educational_memory_service + model | High | High | User-scoped | YES | partial | — | current |
| Concept mastery | VERIFIED | ConceptMasteryRecord, update_concept_mastery | High | High | User-scoped | YES | partial | dashboard visualization | **P7** |
| Mastery persistence | VERIFIED | educational_memories table (JSON blob) | High | High | User-scoped | YES | YES (via /mastery) | — | current |
| Recommendation engine | VERIFIED | recommendation_engine.py + tests | High | High | User-scoped | — | partial | full queue surface | **P7** |
| Next-action recommendation | VERIFIED | /mastery next_action (deterministic) | High | High | User-scoped | — | YES | prioritized multi-action | **P7** |
| Weak-concept detection | VERIFIED | effectiveness report weak_concepts | High | High | User-scoped | — | NO | surfaced | **P7** |
| Strong-concept detection | VERIFIED | effectiveness report strong_concepts | High | High | User-scoped | — | NO | surfaced | **P7** |
| Cross-lesson understanding | PARTIAL | data exists; no surfaced aggregate | Medium-High | High | User-scoped | YES | NO | learner aggregate endpoint + page | **P7** |
| Personalization | VERIFIED | mastery-driven actions | High | High | User-scoped | YES | partial | broader exposure | **P7** |

## D. Analytics

| Capability | Status | Evidence | User Value | Tech Readiness | Security | Persistence | Browser Verified | Missing Pieces | Candidate Phase |
|---|---|---|---|---|---|---|---|---|---|
| Learner progress analytics | PARTIAL | learning_analytics_snapshots + data | Medium-High | High | User-scoped | YES | NO | learner dashboard | **P7** |
| Quiz analytics | PARTIAL | quiz_attempts/question_attempts | Medium-High | High | User-scoped | YES | NO | dashboard surface | **P7** |
| Concept mastery visualization | PARTIAL | concept_mastery map (DTO) | Medium-High | High | User-scoped | — | NO | charts in dashboard | **P7** |
| Cross-lesson history | PARTIAL | learning_events, sessions | Medium-High | High | User-scoped | YES | NO | aggregate endpoint + page | **P7** |
| Learning activity history | PARTIAL | learning_events append-only | Medium-High | High | User-scoped | YES | NO | surfaced | **P7** |
| Performance trends | MISSING | data exists, no trend surface | Medium-High | High | User-scoped | YES | NO | trend computation + UI | **P7** |
| Assessment trends | MISSING | data exists, no surface | Medium-High | High | User-scoped | YES | NO | trend computation + UI | **P7** |
| Recommendation effectiveness | NOT VERIFIED | no feedback loop measured | Medium | Medium | User-scoped | — | NO | needs design | Defer |

## E. Visual Learning

| Capability | Status | Evidence | User Value | Tech Readiness | Security | Persistence | Browser Verified | Missing Pieces | Candidate Phase |
|---|---|---|---|---|---|---|---|---|---|
| Visual generation | VERIFIED | visual_* services/routers | High | High | Ownership | YES | partial | — | current |
| Visual persistence | VERIFIED | storage/uploads + visual services | High | High | Ownership | YES | partial | — | current |
| Visual interaction | VERIFIED | player type-selector + Generate | Medium-High | High | Ownership | — | partial | — | current |
| Animation | VERIFIED | animation services/routers | Medium-High | High | Ownership | YES | NO | — | Defer (C) |
| Simulation | VERIFIED | simulation services/routers | Medium-High | High | Ownership | YES | NO | — | Defer (C) |
| Adaptive visual learning | NOT VERIFIED | no adaptive visual loop surfaced | Medium | Medium | Ownership | — | NO | needs design | Defer (C) |

## F. AI Tutor / RAG

| Capability | Status | Evidence | User Value | Tech Readiness | Security | Persistence | Browser Verified | Missing Pieces | Candidate Phase |
|---|---|---|---|---|---|---|---|---|---|
| RAG retrieval | VERIFIED | rag_indexing_service, vector_index | High | High | Ownership | YES | NO | tutor UI wiring | Defer (D) |
| Semantic retrieval | VERIFIED | embeddings/vector_index (P4/WS7) | High | High | Ownership | YES | NO | — | Defer (D) |
| Ownership isolation (RAG) | VERIFIED | per-user docs; P4/WS7 docs | High | High | Ownership | YES | NO | — | current |
| Educational memory context | VERIFIED | educational_memory_service | High | High | User-scoped | YES | partial | tutor use | Defer (D) |
| Mastery-aware tutoring | NOT VERIFIED | no surfaced tutor loop | High | Medium-High | User-scoped | — | NO | needs design | Defer (D) |
| Lesson-aware tutoring | PARTIAL | assistant/learning_assistant services | Medium-High | Medium-High | Ownership | YES | NO | surfaced tutor UI | Defer (D) |

## G. Learner Dashboard

| Capability | Status | Evidence | User Value | Tech Readiness | Security | Persistence | Browser Verified | Missing Pieces | Candidate Phase |
|---|---|---|---|---|---|---|---|---|---|
| Overall progress page | MISSING | no dashboard page in frontend | High | High | — | — | NO | new page + endpoint | **P7** |
| Current-lesson progress | VERIFIED | journey bar (lesson-scoped) | Medium | High | Ownership | YES | YES | — | current |
| Completed lessons list | PARTIAL | data exists; no list surface | Medium-High | High | User-scoped | YES | NO | surfaced | **P7** |
| Assessment performance | PARTIAL | quiz attempt data; no surface | Medium-High | High | User-scoped | YES | NO | surfaced | **P7** |
| Mastery (aggregate) | PARTIAL | /mastery counts (lesson-scoped) | High | High | User-scoped | YES | partial | cross-lesson surface + viz | **P7** |
| Weak/strong concepts | PARTIAL | concept_mastery + effectiveness report | High | High | User-scoped | — | NO | dashboard panels | **P7** |
| Recommendations | PARTIAL | /mastery single next_action | High | High | User-scoped | — | partial | full prioritized queue | **P7** |
| History | MISSING | data exists; no UI | Medium-High | High | User-scoped | YES | NO | surfaced | **P7** |
| Trends | MISSING | data exists; no computation/UI | Medium-High | High | User-scoped | YES | NO | trend computation + UI | **P7** |

## H. Teacher / Instructor

| Capability | Status | Evidence | User Value | Tech Readiness | Security | Persistence | Browser Verified | Missing Pieces | Candidate Phase |
|---|---|---|---|---|---|---|---|---|---|
| Creator analytics | PARTIAL | creator_analytics_snapshots, presentation_analytics | Medium | Medium-High | Creator-scoped | YES | NO | surfaced | Defer (F) |
| Teacher intelligence product | DEFERRED | not required by current single-user focus | Medium | Medium | — | — | NO | needs product decision | Defer (F) |

## I. Architecture / Foundation

| Capability | Status | Evidence | User Value | Tech Readiness | Security | Persistence | Browser Verified | Missing Pieces | Candidate Phase |
|---|---|---|---|---|---|---|---|---|---|
| PostgreSQL prod | VERIFIED | JSONB variants, readiness | — | High | — | YES | — | — | preserve |
| SQLite test path | VERIFIED | tests on SQLite file | — | High | — | YES | — | — | preserve |
| Alembic single head | VERIFIED | `0028_ws10_idempotency_key_index`, 28 migs | — | High | — | YES | — | — | preserve |
| Vanilla SPA frontend | VERIFIED | backend/frontend served | — | High | JWT | — | YES | dashboard page | **P7** |
| Duplicate frontend (EduVision_AI_Frontend/) | INHERITED (inactive) | repo-root dir; NOT served | — | Low | — | — | NO | ignore / do not use | OUT OF SCOPE |
| Bounded caches | VERIFIED | BoundedCache in edumem service | — | High | per-user | — | — | — | preserve |
| Health/readiness | VERIFIED | health.py DB+Redis+storage | — | High | — | — | — | — | preserve |
| CI | VERIFIED | .github/workflows/ci.yml | — | High | — | — | — | — | preserve |

---

## Key cross-cutting conclusion

Every learner-intelligence **data** capability (mastery, recommendation,
weak/strong concepts, attempt history, learning events, learning gain) is
**VERIFIED / PARTIAL** at the backend. The dominant gap is the **learner-facing
surface**: Learner Dashboard capabilities are largely **MISSING/PARTIAL** and
not browser-verified. P7 turns existing intelligence into visible value.
