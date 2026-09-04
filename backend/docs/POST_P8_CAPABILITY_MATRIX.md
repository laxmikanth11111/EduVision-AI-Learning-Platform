# Post-P8 Capability Matrix

**Phase:** P8 (Mastery-Aware AI Tutor — audit)
**Branch:** `feature/individual-user-foundation`
**Audited HEAD:** `ea9e10e`
**Status vocabulary:** VERIFIED · INHERITED · PARTIAL · MISSING · NOT VERIFIED · DEFERRED · REGRESSION · OUT OF SCOPE
**Meaning of status codes:** **VERIFIED** = directly confirmed in this phase's audit. **INHERITED** = established in an earlier phase (P0–P7) and unchanged. **PARTIAL** = present but incomplete vs. the product vision. **MISSING** = absent. **NOT VERIFIED** = correctly described but not re-checked this pass. **DEFERRED** = planned for a later phase. **REGRESSION** = previously working, now broken. **OUT OF SCOPE** = explicitly excluded.

---

## 1. Mastery Tutor (P8 headline)

| Capability | Status | Evidence | Gap / P9 relevance |
|---|---|---|---|
| Learner-scoped conversational tutor (`tutor.html`) | **VERIFIED** | `frontend/tutor.html`; `app/api/v1/tutor.py`; wired `app/main.py:169` under `/api/v1` | Core P8 deliverable, shipped |
| Weak-concept quick-picks → ask | **VERIFIED** | `tutor.html` `loadPicks()` calls `GET /api/v1/me/progress`, filters `status==='weak'` | Remediation entry point |
| "Remediate my weak concept" quick-action | **VERIFIED** | `POST /api/v1/tutor/remediate`; `remediate()` in `tutor.html`; deep-link from `dashboard.html` "Ask tutor" (`?concept=…`) | **F1 headline resolved** (deterministic engine reused) |
| Deterministic remediation via `recommendation_engine` | **VERIFIED** | `mastery_tutor_service.py:555` `generate_recommendations(..., max_actions=3)`; `_deterministic_explanation` fallback | No ML/DL introduced |
| Grounded answer with `source_kind` / `confidence` / `attribution` chips | **VERIFIED** | `TutorMessageResponse`; `tutor.html` renders `badge rag/deterministic` + confidence + `· source:` | Shape/contract correct |
| **Semantic RAG grounding (query-embedding + cosine + threshold)** | **PARTIAL** | `mastery_tutor_service.py:623-636` retrieves chunks **in positional/pairs order** — no query embedding, no cosine, no `TUTOR_RETRIEVAL_SIMILARITY_THRESHOLD`, no ranking; contrast `learning_assistant_service._retrieve_relevant_chunks_semantic:598-635` (true semantic path) | **F1 — highest-severity gap**; claim overstates implementation |
| Deterministic fallback on cold AI/RAG | **VERIFIED** | `_deterministic_explanation`; RAG "cold" path; `tutor.html` deterministic badge | Required fallback present and exercised |
| Persistence of sessions/messages (DB) | **VERIFIED** | `0013` schema; `0029` additive columns; `tutor_sessions`, `tutor_conversations`, `tutor_messages` | Stored correctly |
| Session resume / history replay UI | **MISSING** | `GET /sessions` + `GET /conversations/{id}/messages` exist but `tutor.html` never calls them; always creates a new session | **F5 — product gap**; backend ready, UI not wired |
| Bounded AI context window | **VERIFIED** | `_load_history(..., limit=20)` + `TUTOR_MAX_CONTEXT_CHARS` | Constant `20` ≠ `TUTOR_MAX_HISTORY_MESSAGES=12` (**F4**) |
| Bounded DB growth / retention policy | **MISSING** | `TUTOR_CONVERSATION_CLEANUP_DAYS=90`/`TUTOR_SESSION_IDLE_DAYS=30` defined, **never enforced**; messages accumulate unbounded | **F3** |
| AI path exclusively via `AIContentService` | **VERIFIED** | `mastery_tutor_service.py:421-452` `get_ai_content_service()…service.generate(...)`; no direct SDK in service | Mandated abstraction holds |
| Deterministic `LocalMockProvider` (no source echo) | **INHERITED** | `app/ai/providers/local.py` | Attribution added separately as `_Source` |

## 2. Learner Progress & Dashboard

| Capability | Status | Evidence | Gap / P9 relevance |
|---|---|---|---|
| Learner-scoped progress aggregate (`GET /api/v1/me/progress`) | **VERIFIED** | `app/api/v1/learner_progress.py`; wired `app/main.py:167` | **Unchanged** in P8; tutor consumes it |
| Concept mastery (mastered/developing/weak) + weak chips | **INHERITED** (P7) | dashboard renders weak chips | Now **actionable** via "Ask tutor" deep-link |
| Deterministic recommendations reuse | **INHERITED** (P7) | dashboard → tutor `remediate` | Shared engine reused by tutor (**F1 headline**) |
| Dashboard afforway: "Ask tutor" link on weak concepts | **VERIFIED** (new in P8) | `dashboard.html:304-305` `?concept=` deep-link | P7 gap → **resolved** |

## 3. Assessment & Quiz

| Capability | Status | Evidence | Gap / P9 relevance |
|---|---|---|---|
| Interactive quiz-taking loop | **INHERITED** (P6) | `player.html` `#quizOverlay` | Unchanged in P8 |
| Quiz attempts feed tutor "recent performance" grounding | **VERIFIED** | `_load_recent_attempts` (`QuizAttempt`⋈`Quiz`) feeds prompt context | Tutor uses it |
| Exam-grade / branching engine | **MISSING / G-1** | linear-block model | Long-term vision; out of P8 |

## 4. Learner Intelligence (Deterministic)

| Capability | Status | Evidence | Gap / P9 relevance |
|---|---|---|---|
| Concept mastery model (`educational_memory_service`, `BoundedCache(5000, ttl=1800)`) | **INHERITED** / **VERIFIED** | tutor reads weak/developing concepts into context | Core tutor grounding |
| Thresholds shared, not redefined | **INHERITED** | mastery thresholds centralized | Preserved |
| ML/DL / inference-based adaptation | **OUT OF SCOPE** | architecture mandates deterministic | Not in P8 (**F1 is deterministic-scoped**) |

## 5. AI / RAG

| Capability | Status | Evidence | Gap / P9 relevance |
|---|---|---|---|
| `AIContentService` as **mandatory** AI path | **VERIFIED** | tutor routes exclusively through it | **Held** |
| Vector embedding infrastructure (`ChunkEmbedding`) | **INHERITED** (WS3) | `app/ai/embeddings/factory.py` registers Gemini/Local/OpenAI providers | Present |
| **Semantic (cosine, thresholded, ranked) retrieval** | **PARTIAL** | `learning_assistant_service` does it; **tutor does NOT** | **F1 — see §1**; reuse the semantic path |
| Positional-only retrieval | **INHERITED** (historical) | tutor currently behaves as positional/bounded grab | Mitigated by fallback but not semantic |
| Deterministic fallback when RAG/AI cold | **VERIFIED** | tutor cold-path + deterministic badge | Required and shipped |

## 6. Architecture & Infrastructure

| Capability | Status | Evidence | Gap / P9 relevance |
|---|---|---|---|
| PostgreSQL production + SQLite test | **VERIFIED** | PG suite **15 passed**; SQLite **1107 passed** | **Locked contract** |
| Linear Alembic chain, single head `0029_tutor_sessions` | **VERIFIED** | `alembic heads` → `0029`; linear `0001→…→0029` | Contract keeps (P9 adds ≤1 add) |
| `0029_tutor_sessions` additive + idempotent | **VERIFIED** | adds `target_concept_id`, `source_kind`, `attribution`, `confidence`, `ix_tutor_messages_source_kind`; guards `_columns`/`_index_exists` | Clean append |
| ORM ↔ migration index parity | **PARTIAL** | **F6:** ORM `ix_tutor_conversations_lesson` (composite) vs migration `ix_tutor_conversations_lesson_id` (single) — SQLite `create_all` vs PG migration asymmetry | Align in cleanup |
| Vanilla SPA served from `backend/frontend/` | **VERIFIED** | `tutor.html` vanilla; no framework/build | Held |
| Bounded caches | **INHERITED** | `BoundedCache` (memory) | Held |

## 7. Security & Ownership

| Capability | Status | Evidence | Gap / P9 relevance |
|---|---|---|---|
| `user_id` from `get_current_user`, never client-supplied | **VERIFIED** | all six tutor endpoints; `tutor.py` docstring | Root requirement met |
| Server-verified ownership (sessions, lessons, presentations, concepts) | **VERIFIED** | service checks before any state read/write | **Held** |
| Cross-user isolation (B never sees A) | **VERIFIED** | `test_mastery_tutor_security.py`: 401, cross-user 404-equalization, malformed/nonexistent IDs | **Held** |
| XSS-safe rendering (`escHtml`, `encodeURIComponent`) | **VERIFIED** | `tutor.html`/`dashboard.html` escape all content | **Held** |
| `authFetch` 401→refresh→retry→signin | **VERIFIED** | `tutor.html` `authFetch`/`authHeaders` | **Held** (inline, not shared — drift risk) |
| OAuth / auth infrastructure | **INHERITED** | `0017_google_oauth` | Unchanged |
| Secret hygiene | **VERIFIED** | scan clean; only CI regex self-reference | Maintain |

## 8. Performance

| Capability | Status | Evidence | Gap / P9 relevance |
|---|---|---|---|
| Bounded AI context (prompt) | **VERIFIED** | `limit=20` + char cap | Held (F4 constant) |
| Bounded DB storage | **MISSING / F3** | no retention; unbounded message/session growth | Add policy |
| Paginated tutor endpoints | **VERIFIED** | `GET /sessions`, `GET /conversations/{id}/messages` paginated | Backend ready (UI unused) |

## 9. Quality Gates (CI-Relevant)

| Capability | Status | Evidence | Gap / P9 relevance |
|---|---|---|---|
| Fast suite SQLite ≥ 1103 passed | **VERIFIED** | **1107 passed** re-run | Floor |
| PG suite 15 passed | **VERIFIED** | **15 passed** re-run | Floor |
| Browser P8 E2E 1/1 | **VERIFIED** | **1 passed** re-run | Note: deterministic fallback only (**F2**) |
| Browser P7 E2E 1/1 (pattern kept) | **VERIFIED** | **1 passed** re-run | 3x not re-run in P8 (1x confirmed) |
| mypy ≤ 83 errors, zero new | **VERIFIED** | **83 in 24 files**; none in tutor modules | Floor |
| ruff clean | **VERIFIED** | `ruff check .` → all passed | Floor |
| `git diff --check` clean | **VERIFIED** | exit 0 | Maintain |
| Alembic single linear head | **VERIFIED** | `0029` unique | Contract |

## 10. Documentation & Process

| Capability | Status | Evidence | Gap / P9 relevance |
|---|---|---|---|
| Phase plans + reports + audits chain | **VERIFIED** | P0–P8 docs present | P9 continues chain |
| Post-P8 docs (this phase) | **VERIFIED** | this audit + matrix + P9 scope | Companion set |

## 11. Phase-Inheritance Summary

| Earlier phase | Delivered (INHERITED) | Status this audit |
|---|---|---|
| P0–P4 | Stack, RAG vector, AIContentService, caches, CI | INHERITED |
| P5 | Learner-journey panel + per-user progress | INHERITED |
| P6 | Interactive quiz complete loop | INHERITED |
| P7 | Learner progress dashboard + browser E2E | INHERITED (unchanged) |
| **P8** | **Mastery-Aware AI Tutor (API + vanilla UI + deterministic remediation)** | **VERIFIED (this audit)** |

---

## Summary of Greatest P9-Relevant Deltas
1. **F1 (High):** Tutor retrieval is **positional/bounded**, not true semantic RAG — no query-embedding, cosine, or `TUTOR_RETRIEVAL_SIMILARITY_THRESHOLD`. The "RAG grounded" claim overstates the implementation; reuse `learning_assistant_service`'s semantic path or re-scope.
2. **F5 (Medium):** Persistence exists (sessions/messages) but there is **no UI resume / session list / history replay** — backend endpoints unused by `tutor.html`.
3. **F3 (Medium):** `tutor_messages`/`tutor_sessions` **grow unbounded**; retention settings defined but unenforced.
4. **F2 (Medium):** P8 browser E2E seeds no `DocumentChunk`/`ContentUnit`, so it exercises **only the deterministic fallback** — the real AI+RAG prompt path is not browser-verified.
5. **F6/F4 (Low):** ORM↔migration index drift; history constant `20` ≠ setting `12`.
6. No teacher/classroom role, no interactive 2D editor, no frontend framework, no branching lesson model — all **deferred / out of scope** (unchanged).
