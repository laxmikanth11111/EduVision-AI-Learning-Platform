# Post-P7 Capability Matrix

**Phase:** P7 (Learner Intelligence & Adaptive Progress — audit)
**Branch:** `feature/individual-user-foundation`
**Audited HEAD:** `9b32ecd`
**Status vocabulary:** VERIFIED · INHERITED · PARTIAL · MISSING · NOT VERIFIED · DEFERRED · REGRESSION · OUT OF SCOPE
**Meaning of status codes:** **VERIFIED** = directly confirmed in this phase's audit. **INHERITED** = established in an earlier phase (P0–P6) and unchanged. **PARTIAL** = present but incomplete vs. the product vision. **MISSING** = absent. **NOT VERIFIED** = correctly described but not re-checked this pass. **DEFERRED** = planned for a later phase. **REGRESSION** = previously working, now broken. **OUT OF SCOPE** = explicitly excluded.

---

## 1. Learner Progress & Dashboard

| Capability | Status | Evidence | Gap / P8 relevance |
|---|---|---|---|
| Learner-scoped progress aggregate (`GET /api/v1/me/progress`) | **VERIFIED** | `app/api/v1/learner_progress.py:22`; wired `app/main.py:166` | Foundation of P8; add action surface / remediation links |
| Summary (completed/in-progress/mastery/attempts) | **VERIFIED** | `learner_progress_service.py:81-89`, `Summary` schema | P8 deep-link to practice |
| Lesson progress + resume information | **VERIFIED** | `_lesson_progress:141-188`, `LessonProgressItem` | Return to `player.html` resume |
| Concept mastery (mastered/developing/weak) | **VERIFIED** | `_concept_mastery_summaries:239-262` (85.0/50.0 thresholds) | Primary input to Mastery-Aware Tutor |
| Weak & strong concept chips | **VERIFIED** | `:108-115`; `dashboard.html` renders `.concept:has(.chip.weak)` | P8 "remediate" quick-action source |
| Deterministic recommendations | **VERIFIED** | `generate_recommendations` at `:92` | P8 tutor consumes same engine |
| Recent attempts + trend | **VERIFIED** | `_attempt_history:190-237`, `_build_trend:264-282` (oldest→newest) | Trend depth in a later phase |
| Cross-user isolation / ownership | **VERIFIED** | `research`/`test_learner_progress_security.py` `test_user_b_never_sees_user_a_data` | Lock the P8 chat-session isolation pattern |
| Bounded result sets / no N+1 | **VERIFIED** | `:43-46` caps; `:141-147` join; `:197-215` count+join | Preserve discipline in P8 chat history |
| Auth required (401) / empty state | **VERIFIED** | `test_dashboard_requires_authentication`, `test_empty_state` | Preserve in P8 |

## 2. Assessment & Quiz

| Capability | Status | Evidence | Gap / P8 relevance |
|---|---|---|---|
| Interactive quiz-taking UI with complete loop | **INHERITED** (P6) | `player.html` `#quizOverlay`; P6 commit `8c82a2c` | Feed attempt history into tutor context |
| Deterministic attempt aggregate (passed, percent_score, bounded totals) | **VERIFIED** | `_attempt_history`, `QuizAttempt`/`Quiz` join | Reused for tutor's "recent performance" grounding |
| Structured multi-question exam engine (sections, item ordering, per-item timing) | **MISSING** | no exam engine beyond current quiz flow | **G-2**; candidate E / deferred |
| Adaptive difficulty based on learner state | **PARTIAL** | deterministic adaptation present in P6 quiz flow; not full branching (G-1) | Future candidate A/E |

## 3. Learner Intelligence (Deterministic)

| Capability | Status | Evidence | Gap / P8 relevance |
|---|---|---|---|
| Concept mastery model (educational memory) | **VERIFIED** | `educational_memory_service.py:30` class; `BoundedCache(5000, ttl=1800)`; `load_from_db` used by service `:80` | Core tutor grounding |
| Thresholds shared, not redefined | **VERIFIED** | `learner_progress_service.py:49-52` "do NOT redefine" | Sanity invariant |
| Recommendations deterministic, no rewrite | **VERIFIED** | `:92` reuse engine | Tutor mirrors engine |
| ML/DL / inference-based adaptation | **OUT OF SCOPE** | architecture mandates deterministic learner intelligence | Not in P8 |
| Cache freshness across replicas | **PARTIAL / G-4** | in-memory BoundedCache per-process; TTL 1800s | Accept for single learner; revisit if multi-replica |

## 4. AI / RAG

| Capability | Status | Evidence | Gap / P8 relevance |
|---|---|---|---|
| AIContentService as **mandatory** AI path | **INHERITED** (P0+, kept through P7) | lesson-generation pipeline; no bypass | **P8 tutor MUST route through AIContentService** |
| Vector-based RAG retrieval | **INHERITED** (WS3) | RAG infrastructure (migration `0012_rag_infrastructure`) | Ground tutor answers; fix cold-start with deterministic fallback |
| Positional-only retrieval | **INHERITED** (P0, superseded) | initial approach | Historical; vector now used |
| Tutor grounded in learner's RAG + memory (weak concepts) | **MISSING** | no tutor yet | **Core P8 headline (Candidate C)** |
| Deterministic fallback when RAG/AI cold | **MISSING** | not yet surfaced as a product path | **P8 required fallback** |

## 5. Predictive / Adaptive AI

| Capability | Status | Evidence | Gap / P8 relevance |
|---|---|---|---|
| Deterministic next-best actions | **VERIFIED** | recommendations in P7 | Tutor "remediate" trigger |
| True predictive (ML) models | **OUT OF SCOPE** | architecture forbids ML/DL for learner intelligence | Not in P8 |

## 6. Personalized / Adaptive Learning

| Capability | Status | Evidence | Gap / P8 relevance |
|---|---|---|---|
| Personalized learning infrastructure | **INHERITED** (P5/P6) | `0011_personalized_learning`, learner-journey panel, P5/P6 | P8 builds tutor surface on top |
| Branching / forked lesson paths by mastery | **MISSING / G-1** | linear-block model | Long-term vision gap; tutor partially compensates |
| Actionable "remediate this weak concept" flow | **MISSING** | dashboard shows weaknesses but no deep-link | **P8 second headline** |

## 7. Teacher / Classroom Analytics

| Capability | Status | Evidence | Gap / P8 relevance |
|---|---|---|---|
| Teacher / parent / classroom role | **MISSING / G-5** | single `User` role `USER="user"` in active code | Candidate F blocked; not in P8 |
| Multi-roster/classroom analytics | **MISSING** | no role surface | Deferred until role model exists |

## 8. Visual Learning

| Capability | Status | Evidence | Gap / P8 relevance |
|---|---|---|---|
| Visualization infrastructure | **INHERITED** (P2/P3) | `visual_*`, `animation_*`, `video_*` routers/services | Rich but broad |
| Advanced visual learning upgrade | **DEFERRED** | candidate D | Not the P8 headline |

## 9. Interactive Authoring / Editing

| Capability | Status | Evidence | Gap / P8 relevance |
|---|---|---|---|
| Document upload → AIContentService lesson | **INHERITED** | `upload.html`, `processing.html` | Unchanged; tutor consumes these lessons |
| Interactive 2D lesson editor | **MISSING / G-8** | no editor | Candidate G; deferred |

## 10. Architecture & Infrastructure

| Capability | Status | Evidence | Gap / P8 relevance |
|---|---|---|---|
| PostgreSQL production + SQLite test | **INHERITED** + **VERIFIED** | PG suite 15 passed; SQLite 1103 passed | Locked contract |
| Linear Alembic chain, head `0028_ws10_idempotency_key_index` | **VERIFIED** | migration files (verified chain), no P7 migration | P8 adds ≤1 migration, append chain |
| Vanilla SPA served from `backend/frontend/` | **VERIFIED** | 8 HTML files + assets; no framework/build | P8 stays vanilla |
| Bounded caches | **INHERITED** | `BoundedCache` | Reuse in tutor context |
| Knowledge graph infrastructure | **DEFERRED / G-11-similar** | candidate H infra | Supporting, not headline |

## 11. Security & Ownership

| Capability | Status | Evidence | Gap / P8 relevance |
|---|---|---|---|
| Auth (`get_current_user`) resolves owner; never client-supplied ID | **VERIFIED** | `learner_progress.py:27-32` | P8 chat root must match |
| Cross-user isolation tests | **VERIFIED** | integration suite | P8 isolation pattern |
| 401 on unauthenticated protected path | **VERIFIED** | security test | Preserve |
| OAuth (Google) | **INHERITED** | migration `0017_google_oauth` | Unchanged |
| Secret hygiene | **VERIFIED** | secret scan clean (only dummy test passwords) | Maintain |

## 12. Performance

| Capability | Status | Evidence | Gap / P8 relevance |
|---|---|---|---|
| No N+1 in aggregate | **VERIFIED** | set-based queries (≈4–5 total) | Preserve in P8 chat history |
| Bounded result sets | **VERIFIED** | caps in service | Preserve |
| Response envelope + `authFetch` | **INHERITED** | shared SPA pattern | Reuse in tutor |

## 13. Quality Gates (CI-Relevant)

| Capability | Status | Evidence | Gap / P8 relevance |
|---|---|---|---|
| Fast suite SQLite ≥ 1103 passed | **VERIFIED** | C6 numbers | Regression floor |
| PG suite 15 passed | **VERIFIED** | testcontainer `postgres:16-alpine` | Floor |
| Browser P7 E2E 3/3 | **VERIFIED** | `test_p7_dashboard_e2e.py` | Keep green; add P8 E2E |
| mypy ≤ 83 errors, zero new | **VERIFIED** | `[tool.mypy] exclude=["tests/"]` | Floor |
| ruff clean | **VERIFIED** | `ruff check .` | Floor |
| `git diff --check` clean | **VERIFIED** | clean | Maintain |

## 14. Documentation & Process

| Capability | Status | Evidence | Gap / P8 relevance |
|---|---|---|---|
| Phase plans + reports + audits | **VERIFIED** | P0–P7 docs all present (glob-verified) | P8 continues chain |
| Post-P7 docs (this phase) | **VERIFIED** | this audit + matrix + P8 scope | Companion set |

## 15. Phase-Inheritance Summary

| Earlier phase | Delivered (INHERITED) | Status this audit |
|---|---|---|
| P0 | Stack, linear blocks, AIContentService, initial RAG, `User` role | INHERITED (unchanged) |
| P1–P3 | RAG vector, visual/animation/video, effectiveness | INHERITED |
| P4 | Bounded caches, CI e2e smoke | INHERITED |
| P5 | Learner-journey panel + per-user progress (`LearningSession`) | INHERITED |
| P6 | Interactive quiz complete loop (`8c82a2c`) | INHERITED |
| **P7** | **Learner Progress dashboard aggregate + dashboard + browser E2E** | **VERIFIED (this audit)** |

---

## Summary of Greatest P8-Relevant Deltas
1. No **learner-facing conversational tutor** grounded in real memory + RAG (Core P8 headline).
2. P7 recommendations/weak-chips are **not yet actionable** (no "remediate" deep-link) (P8 second headline).
3. Linear-block, non-branching lesson model (long-term vision gap, mitigated by tutor).
4. No teacher/classroom role; no interactive 2D editor; no frontend framework — all **deferred / out of scope**.