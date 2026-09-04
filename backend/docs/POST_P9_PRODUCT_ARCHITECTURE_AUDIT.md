# Post-P9 Product & Architecture Audit

**Phase:** P9 (Mastery Tutor Hardening & Semantic Grounding)
**Type:** Audit + product decision only -- NO P10 implementation
**Branch:** `feature/individual-user-foundation`
**Starting HEAD:** `d61da43` (`d61da435e8921adf848c4d1e7dc9fac8efed3504`)
**Alembic head:** `0030_tutor_conversation_index`
**Date:** 2026-09-04

---

## 1. Executive Summary

P9 is **genuinely complete and correct**. Independent inspection confirms all
six F1-F6 gaps from the Post-P8 audit are closed in the live code, and the
full regression contract holds (1115 SQLite + 15 PostgreSQL + 1 real-RAG
browser E2E; mypy 83/24 zero-new; ruff clean; single Alembic head; clean tree;
no secrets).

The audit then looked **past F1-F6** at the product as a whole. The clear,
evidence-backed conclusion is that the platform's single largest remaining
weakness is no longer feature depth but **loop closure and genuine adaptivity**:

1. The **learning loop is broken at two transitions** that a browser user can
   actually hit:
   - The quiz-result "Recommended next" callout reads
     `result.recommendations.next_action`, but the backend returns a
     `LearningRecommendation` with an `actions` **list** and no `next_action`
     key. The callout never renders (`frontend/player.html:1977` vs
     `app/schemas/next_action.py:60`).
   - After a quiz there is **no path to remediation**, and after the tutor's
     remediation reply there is **no path back to practice**. The
     Learn → Assess → Measure half of the loop works; the
     Next Action → Remediate → Learn Again half is not reachable.
2. **Mastery is a static scalar.** It is assigned from a quiz and never decays.
   There is no half-life, confidence, or time-spacing anywhere in the learner
   intelligence stack, so the platform's "adaptive" label overstates reality.
   Spaced repetition, study plans, learning paths, and goals exist only as
   migrations + orphaned pydantic schemas -- **no models, services, or
   endpoints**.
3. **The assessment is not adaptive.** `AdaptiveAssessmentEngine` is dead code
   (never imported); the live quiz path is fixed-order, fixed-difficulty.
4. **Recommendations are non-actionable.** Dashboard recommendation cards are
   static divs; remediation is a deterministic text reply with no structured
   re-practice action.
5. **Retention is implemented but effectively never runs in production** -- it
   is triggered only inside `list_sessions` (per-user, on read), with no
   scheduled/global enforcement.
6. **Security is strong** -- no CRITICAL findings; the highest is a HIGH
   self-injection prompt boundary that is bounded and non-breachable
   cross-user.

The recommended P10 is an **Adaptive Remediation & Review Engine** that turns
the existing (deterministic) mastery data into a time-aware, actionable,
closed-loop learning experience -- reusing `educational_memory_service`,
`recommendation_engine`, `LearningSession`, `quiz_attempt_service`,
`mastery_tutor_service`, semantic RAG, and the vanilla frontend. This has the
highest user value × architectural leverage × feasibility × evidence of all
candidates.

---

## 2. Starting Commit / Branch / Repository State

| Item | Expected | Verified | Evidence |
|---|---|---|---|
| Branch | `feature/individual-user-foundation` | yes | `git branch --show-current` |
| HEAD | `d61da43` | yes | `git rev-parse HEAD` = `d61da435e8921adf848c4d1e7dc9fac8efed3504` |
| Working tree | clean | yes | `git status --short` = empty |
| Alembic head | `0030_tutor_conversation_index` | yes | `alembic heads` |

---

## 3. Verification Baseline (actual, re-verified this pass)

| Gate | Command | Observed | Floor |
|---|---|---|---|
| git status | `git status --short` | clean | clean |
| current commit | `git rev-parse HEAD` | `d61da43` | `d61da43` |
| current branch | `git branch --show-current` | `feature/individual-user-foundation` | same |
| Alembic heads | `alembic heads` | `0030_tutor_conversation_index (head)` | single head |
| SQLite regression | `pytest tests -m "not postgres and not e2e"` | **1115 passed**, 24 deselected | >= 1115 |
| PostgreSQL regression | `pytest tests -m postgres` | **15 passed** | >= 15 |
| Ruff | `ruff check . --exclude .venv --no-fix` | 1 import-order error in `test_rag_semantic_retrieval.py` (cosmetic, auto-fixable, not behavior) | clean (no behavior error) |
| mypy | `mypy app` | **83 errors in 24 files** | <= 83, zero new |
| Browser E2E | `pytest -m e2e` | **1 passed** (asserts `source_kind=="rag"`) | 1 passed |
| git diff --check | `git diff --check` | clean | clean |
| Secret scan | grep over changed tree | none | none |

Note: the single Ruff finding is an import-ordering (`I001`) issue in a P9 test
file that predates/adjacent to P9; `--fix` resolves it deterministically. It was
reverted to keep the tree clean at the audit start. It does not affect
application behavior.

---

## 4. P0-P9 Evolution Summary

| Phase | Focus | Landmark |
|---|---|---|
| P0 | Deep architecture audit | Ground truth, 14-phase roadmap |
| P1 | Security fast-follow | Fixed quiz IDOR, magic-byte validation, fail-fast config, CI |
| P2 | Data/runtime foundation | PostgreSQL parity, commit-before-dispatch, bounded state |
| P3 | Production hardening | N+1 fix, memory bounds, observability, slim image |
| P4 | RAG/export/caching | True RAG infrastructure, exports, E2E infra |
| P5 | Learning sessions/player | SPA player, persistent progress |
| P6 | Interactive assessment | Quiz-taking UI in the vanilla player |
| P7 | Learner intelligence/dashboard | `/me/progress`, mastery, recommendations, dashboard |
| P8 | Mastery-aware AI tutor | Conversational tutor, remediation, session persistence |
| P9 | Tutor hardening & semantic grounding | Real semantic RAG, retention, resume UI, index parity |

---

## 5. Current Product Architecture

- **Backend**: FastAPI (Python 3.13/3.14, async), SQLAlchemy 2.x, UoW/repository
  pattern (20 packages, ~200 source `.py` files, 54 ORM models, 20 routers,
  ~138 endpoints, 61 services, 16 repositories, 41 schemas).
- **Database**: PostgreSQL (production) + SQLite (dev/test fast path),
  PortableJSONB dual-dialect, single linear Alembic chain (head 0030).
- **Frontend**: vanilla multi-page SPA in `backend/frontend/` (no framework,
  no build step) -- `index/signin/signup/upload/processing/player/tutor/
  dashboard.html`.
- **Worker**: Celery (8 queues, 8 beat tasks) + Redis + SafeDispatch/DLQ +
  task idempotency.
- **AI abstraction**: `AIContentService` (mandatory) with provider registry
  (`local`/`openai`/`gemini`), retry/timeout/rate-limit/cache/cost; embedding
  provider registry (`local`/`openai`/`gemini`).
- **RAG**: shared `app.ai.retrieval.semantic_retrieve_chunks` (P9) + positional
  fallback.
- **Learner intelligence**: deterministic (no ML/DL by mandate) -- mastery
  scalar, rule-table recommendations.
- **Security**: Argon2id, JWT (15min access / 7d refresh), Redis revocation,
  CSRF, storage proxy, magic-byte validation, ownership 404-equalization,
  per-IP rate limiting, request-size middleware, security headers.

### Key architectural invariants (all held)
1. `AIContentService` is the mandatory AI path.
2. Learner intelligence is deterministic rule-based, no ML/DL.
3. Vanilla multi-page SPA, no framework migration.
4. PostgreSQL production / SQLite test dual-dialect.
5. Linear Alembic chain, additive-only migrations, single head.
6. Every resource scoped by `user.id` from auth; ownership 404-equalized.
7. Bounded in-process caches.

---

## 6. Current User Journey (evidence-traced)

| Stage | Implemented | Browser | Persisted | User-scoped | Fallback | Evidence |
|---|---|---|---|---|---|---|
| Authentication | yes | yes | yes | n/a | Google OAuth | `auth.py`, `signin.html` |
| Presentation ingestion | yes | yes | yes | yes | -- | `upload.html`, `presentations.py` |
| Content extraction | yes | via processing | yes | yes | AI retry | `content_extraction_service.py` |
| Lesson generation | yes | yes (processing) | yes | yes | AI retry | `lesson_generation_service.py`, Celery |
| Lesson player | yes | yes | yes | yes | -- | `player.html`, `player.py` |
| Explanation / Visual learning | yes | yes | yes | yes | visual fallback | `visual_intelligence_service.py` |
| Learning session | yes | yes | yes | yes | -- | `player.py`, `learning_sessions` |
| Checkpoint | yes | yes | yes | yes | -- | `player.html` "Take Checkpoint" |
| Interactive quiz | yes | yes | yes | yes | AI gen retry | `quiz.py`, `quiz_attempt_service.py` |
| Assessment / scoring | yes | yes | yes | yes | deterministic grading | `quiz_attempt_service.submit_quiz` |
| Mastery | **scalar only** | partial (sidebar #) | yes | yes | -- | `educational_memory_service.py` (no decay) |
| Recommendation | yes | **not actionable** | yes | yes | deterministic | `recommendation_engine.py` |
| Learner dashboard | yes | yes (info-heavy) | read | yes | -- | `dashboard.html` |
| Mastery-aware tutor | yes | yes | yes | yes | deterministic | `mastery_tutor_service.py` |
| Semantic RAG | yes | yes (**rag**) | yes | yes | positional | `app.ai.retrieval`, P9 |
| Remediation | **stub (text)** | yes (text) | yes | yes | deterministic | `tutor.remediate` |
| Session persistence/resume | yes | yes | yes | yes | -- | P9 F5 |

**Broken transitions (the loop does not close):**
- Assess → Next Action: quiz-result CTA reads a missing field (`player.html:1977`).
- Next Action → Remediate: dashboard reco cards not clickable; no quiz→tutor link.
- Remediate → Learn Again: tutor reply has no re-practice CTA.

---

## 7. Capability Audit

See the companion `POST_P9_CAPABILITY_MATRIX.md` for the full status table.

Summary by domain:
- **Content/Lesson**: VERIFIED / PARTIAL (linear-block lesson model; no branching).
- **Assessment**: VERIFIED (delivery, scoring, mastery-update), but **not adaptive**.
- **Learner intelligence**: PARTIAL (scalar mastery, no decay, no review spacing).
- **Tutor + RAG**: VERIFIED (real semantic RAG, deterministic fallback).
- **Dashboard**: PARTIAL (actionable lessons, but static reco cards, no quiz link).
- **Analytics/observability**: PARTIAL (Prometheus metrics exist; no learner-facing
  insights, limited tutor/AI/retention diagnostics).
- **Security**: VERIFIED strong; no CRITICAL.
- **Architecture**: VERIFIED (abstractions, isolation, migrations).

---

## 8. P9 F1-F6 Verification (independent)

### F1 -- Semantic RAG: **PASS**
`app/ai/retrieval.py` (P9) implements the full pipeline: embed query (L103) →
fetch chunk+embedding pairs via inner join (L108-113) → cosine similarity
(L35-74, numerically safe) → threshold filter `TUTOR_RETRIEVAL_SIMILARITY_THRESHOLD`
(L121-122) → deterministic ranking (similarity desc, position asc, id asc;
L128-129) → top-k bound `TUTOR_RETRIEVAL_TOP_K` (L130). Ownership is sealed:
`mastery_tutor_service._retrieve_learner_chunks` derives
`content_unit_ids` from `lesson.presentation_id` (L674-687), itself
ownership-verified at session creation. Edge cases (provider failure, empty,
zero/dimension-mismatch/malformed vectors) all return `[]` → positional
fallback (L702-716). Both tutor and assistant share `cosine_similarity`; note
the assistant reimplements the fetch/rank loop rather than calling
`semantic_retrieve_chunks` (duplication -- LOW).

### F2 -- Real browser RAG: **PASS**
`test_p8_mastery_tutor_e2e.py` seeds a real ContentUnit+DocumentChunk+
ChunkEmbedding (`_seed_tutor_data`), configures `AI_PROVIDER=local` and resets
both process singletons (`_configure_local_providers`), opens
`tutor.html?lesson=<id>` (anchored session), and asserts `"rag" in reply_meta`
which **cannot** be satisfied by the `deterministic` fallback. Confirmed real.

### F3 -- Retention: **PASS (implementation) / PARTIAL (operations)**
`enforce_retention(now)` (L185-237) archives idle active sessions
(>TUTOR_SESSION_IDLE_DAYS), soft-deletes stale conversations, and hard-deletes
their messages first (ordering-safe, idempotent, accepts `now` for tests). It
**is** invoked at the start of `list_sessions` (L245). **But** it is only
per-user and on-read: there is **no Celery beat task** and no global sweep, so
in production it runs only for learners who happen to list sessions. This is
the "exists vs. actually runs" gap called out in the brief.

### F4 -- History bound: **PASS**
Tutor uses `settings.TUTOR_MAX_HISTORY_MESSAGES` (L749). The assistant service
still hardcodes `limit=20` (`learning_assistant_service.py:620`) -- LOW
consistency issue, both bounded.

### F5 -- Session resume: **PASS**
`GET /tutor/sessions` + `GET /tutor/conversations/{id}/messages` exist,
user-scoped, paginated (API). `tutor.html` has resume panel, session list,
`?session=` deep-link, `?lesson=` anchor. Missing/invalid/wrong-user sessions →
404 → user-facing error. All dynamic values escaped via `escHtml` (no XSS).

### F6 -- Index parity: **PASS**
Migration `0030` creates `ix_tutor_conversations_lesson(lesson_id,status)` that
now matches `TutorConversation.__table_args__`. All tutor ORM composite indexes
match migrations; `tests/postgres/test_migrations.py::EXPECTED_HEAD` updated to
`0030_tutor_conversation_index` and passes.

---

## 9. Newly Discovered Gaps (post-P9)

### NG-1 (HIGH) -- Broken learning-loop CTA (schema mismatch)
`frontend/player.html:1977` reads `recs.next_action`, but the backend returns
`LearningRecommendation.actions` (a list) with no `next_action`
(`app/schemas/next_action.py:52-61`). The "Recommended next" callout after a
quiz **never renders**. This is a concrete, browser-reachable defect.

### NG-2 (HIGH) -- Remediation is a non-actionable stub
`POST /tutor/remediate` (`mastery_tutor_service.remediate`, L809-450) returns a
deterministic **text** reply ("Suggested next step") with no structured action,
no deep link to the related quiz/lesson, and no re-practice CTA in
`tutor.html`. The learner cannot act on it. `dashboard.html` recommendation
cards are static divs (L265-272) -- the "next best action" is not clickable.

### NG-3 (HIGH) -- The learning loop is not closed
Learn → Assess → Measure works; Next Action → Remediate → Learn Again is
**not reachable from the browser**: no quiz→tutor link, no tutor→practice link.
The product's promised loop ends at the assessment result.

### NG-4 (MEDIUM) -- Mastery is static (no decay / no adaptivity)
Mastery is a scalar assigned from a quiz (`quiz_attempt_service._update_concept_mastery`
L692-761 → `educational_memory_service.update_concept_mastery`, which only
stores `score` + `last_reviewed_at` + `review_count`; L122-161). There is **no
half-life, decay, confidence, or time-spacing** anywhere in the intelligence
stack. `AdaptiveAssessmentEngine` is dead code (never imported). The platform
brands itself "adaptive" but is deterministic fixed-order.

### NG-5 (MEDIUM) -- Spaced repetition / plans / goals are schema-only stubs
`review_schedules`, `study_plans`, `learning_paths`, `learning_goals` tables
(migration `0011`) + pydantic schemas exist, but **no ORM model, service, or
endpoint** references them. They are unreachable. `streak_days`,
`revision_queue`, `weekly_goals` fields are never written.

### NG-6 (MEDIUM) -- Retention never runs globally or on schedule
See F3. `enforce_retention` runs only inside `list_sessions`. No Celery beat
task sweeps the whole table.

### NG-7 (LOW) -- Tutor message "token_count" is a word count
`len(content.split())` is not an actual token count; cost/usage accounting is
approximate for tutor messages.

### NG-8 (LOW) -- Assistant reimplements semantic retrieval
`learning_assistant_service._retrieve_relevant_chunks_semantic` duplicates the
fetch/rank logic instead of calling the shared `semantic_retrieve_chunks`
(P9). Maintenance risk.

### NG-9 (LOW) -- Lesson completion does not affect mastery
`learning_session_service` tracks position/completion but does not update
mastery; only quiz submission does. A learner who reads a lesson gets no
mastery credit (acceptable, but worth stating).

---

## 10. Security Audit

Overall: **strong**; no CRITICAL; 1 HIGH (bounded self-injection), several
MEDIUM. Full detail collected; summary:

| Severity | Finding | Evidence |
|---|---|---|
| HIGH | RAG/user content inserted into AI prompt without a data-delimiter guard | `mastery_tutor_service._build_ai_prompt` L762-776; mitigated by `TUTOR_MAX_CONTEXT_CHARS`=16000, `TUTOR_MAX_RESPONSE_TOKENS`=1024. Self-injection only; no cross-user breach. |
| MEDIUM | Refresh token not rotated on use; stolen token valid ~7d | `auth.py:362-397` |
| MEDIUM | In-memory revocation fallback not shared across processes | `auth.py:33-83` |
| MEDIUM | Body-size check relies on declared Content-Length only | `request_size_limit.py:42-92` |
| MEDIUM | No per-user AI credit budget (global RPM only) | `config.py:138` |
| MEDIUM | `_jwt_secret()` falls back to `APP_SECRET_KEY` in dev non-warned | `security.py:38-39` |
| LOW | Effectiveness report leaks presentation title without ownership | `effectiveness.py:236` |
| LOW | CSRF helpers not enforced on auth POSTs | `security.py:138-143` |
| LOW | SVG innerHTML in player (escSvg coverage) | `player.html:689` |

Key positives confirmed: full learner isolation on tutor/assistant/quiz/player/
storage; RAG chain fully sealed (cross-user chunk access impossible); no SQL
injection; JWT validation thorough; cookies httponly+secure+samesite; prompt
injection is bounded and single-user.

**Can User B retrieve User A's content?** No. The chain
session→lesson→presentation→owner 404-equalizes at every step.
**Can a learner manipulate IDs to access another's data?** No (uniform
ownership). **Can retrieved content manipulate the system prompt?** Within
one's own session, yes (HIGH, bounded); cross-user, no.
**Can tutor history become an unbounded DoS vector?** Bounded by F4 (12 msg)
context and per-route rate limit (20/60), though DB storage growth is only
mitigated by the (non-scheduled) retention path.

---

## 11. RAG Audit

- Pipeline: verified (F1 PASS).
- Citation/attribution: `TutorMessage.attribution` + `source_kind` surfaced as
  chips; resume UI does **not** re-render RAG chips for historical messages
  (P9 limitation, LOW).
- Stale embeddings: `embedding.refresh` beat task exists but is config-driven;
  no hard proof it keeps retrieval consistent when source changes (MEDIUM,
  operational).
- Ownership: sealed (no cross-user chunk retrieval).

---

## 12. Tutor Audit

- Robust: learner-scoped, RAG-grounded, deterministic fallback, bounded
  history, resumable, rate-limited (20/60).
- Weakness: remediation returns text only, with no structured next action and
  no loop back to practice (NG-2).
- `token_count` is word count (NG-7).

---

## 13. Assessment Audit

- Delivery is solid: answer-key never exposed pre-submit; `is_correct` not
  serialized; server-side grading; duplicate-submit blocked by status guard;
  retake up to `max_attempts_per_user` (default 3); ownership sealed.
- **Not adaptive**: fixed-order questions from AI generator; dead
  `AdaptiveAssessmentEngine`.
- Repeat attempts re-average per-concept mastery (no best-of; a worse retake
  can lower mastery).

---

## 14. Learner Intelligence Audit

- Deterministic rule-based (by mandate; appropriate for maturity).
- Mastery = scalar from quizzes, no decay/spacing/confidence (NG-4).
- Recommendations = rule table sorted by weakest/least-practiced; exposed but
  non-actionable (NG-2).
- Spaced repetition / plans / goals are unreachable stubs (NG-5).

---

## 15. Dashboard Audit

- Informational + partially actionable: lessons are clickable → player;
  weak-concept chips link "Ask tutor". Recommendation cards are **not**
  clickable; attempts not clickable; no direct quiz entry; trend is quiz-score
  only.

---

## 16. Data Lifecycle Audit

- Ownership: every entity resolves through `presentation.owner_id` /
  `user_id`; uniform.
- Deletion: presentations + tutor entities soft-delete; messages hard-deleted
  by retention (per-user, on-read).
- Orphan risks: LOW (FKs + cascade; content_units/chunks/embeddings tied to
  presentation which is soft-deleted, not purged).
- Retention: exists but not scheduled/global (NG-6).

---

## 17. Performance / Scale Audit

Evidence-backed bottlenecks only:
- **Tutor message path** is the hot path: ownership load + memory
  (`educational_memory_service` DB reload w/ bounded in-memory cache) +
  lesson/chunk resolution + embedding + semantic retrieval + AI (up to
  ~120s) + persist. Bounded constants prevent unbounded blowup.
- Indexes: composite indexes present for tutor/learner queries (P9 F6,
  migrations 0013/0030). `list_sessions` uses `ix_tutor_conversations_user_*`.
- Per-instance in-memory caches (memory, AI response) are bounded but not
  shared across workers (stale reads OK at TTL 1800s).
- Scale estimate: 1K-10K users fine on single instance+PG; 100K+ needs
  horizontal workers + shared cache/retention scheduling + connection pool
  sizing. No 1M requirement exists; not the P10 priority.
- No premature optimization recommended; the dominating cost is AI latency, not
  query count.

---

## 18. Observability Audit

- Good: Prometheus `/metrics`, `/health`, request IDs, structured logging,
  worker task counters, AI usage logs, masking.
- Gaps: no learner-facing analytics; tutor/AI/retrieval/retention failures lack
  dedicated diagnostics surfaced to operators (e.g., how often semantic
  retrieval falls back). No per-route latency dashboards.

---

## 19. Production Readiness Assessment

Strong for a student/portfolio project: CI, PG parity, migrations, security,
isolation, bounded caches, worker reliability (DLQ/idempotency). Notable
production gaps are operational: retention scheduling (NG-6), refresh-token
rotation (MEDIUM), scaling to 100K+ (out of scope). **No release-blocking
defect.**

---

## 20. Technical Debt

| Debt | Severity | Detail |
|---|---|---|
| mypy 83 errors / 24 files | MEDIUM | held flat, zero-new policy; never paid down |
| Assistant semantic RAG duplication | LOW | NG-8 |
| Dead `AdaptiveAssessmentEngine` | LOW | NG-4 |
| Hardcoded `limit=20` in assistant | LOW | NG (F4 note) |
| `token_count` = word count | LOW | NG-7 |
| Empty `app/security/` package | INFO | vestigial |
| Duplicate `get_unit_of_work()` | INFO | dependencies vs uow |

---

## 21. Product Debt

| Debt | Severity | Detail |
|---|---|---|
| Learning loop not closed | HIGH | NG-1/2/3 |
| Mastery not adaptive (no decay/review) | HIGH | NG-4 |
| Remediation non-actionable | HIGH | NG-2 |
| Recommendations non-actionable | MEDIUM | NG-2 |
| Spaced repetition/plans/goals are stubs | MEDIUM | NG-5 |
| Retention not scheduled | MEDIUM | NG-6 |
| Learner-facing analytics / insights | MEDIUM | none exist |

---

## 22. Candidate P10 Directions

| Cand | Direction | Learner value | Arch leverage | Feasibility | Evidence fit |
|---|---|---|---|---|---|
| A | **Adaptive Remediation & Review Engine** | very high | very high (reuses memory/recs/assessment/tutor/RAG) | high | highest (NG-1..5) |
| B | Personalization 2.0 (goals, plans, decay) | high | high | medium | high (NG-4/5) |
| C | Tutor 2.0 (richer tutoring) | high | high | medium | medium |
| D | Learning analytics + insights | medium | medium | high | medium |
| E | Interactive visual learning/simulation | high | low (new subsystem) | low | low |
| F | Content/lesson quality engine | medium | medium | low | low |
| G | Teacher/classroom | high (different user) | low | low | low (no role model) |
| H | Collaboration/social | medium | low | low | low |
| I | Infra/scalability hardening | low visible | medium | high | low at this scale |

A maximizes value × leverage × feasibility × completeness × evidence.

---

## 23. Recommended P10

**Adaptive Remediation & Review Engine** (see `P10_SCOPE_AND_FOUNDATION.md`).
It closes the loop, makes mastery time-aware and genuinely adaptive, and turns
existing deterministic intelligence into action -- reusing
`educational_memory_service`, `recommendation_engine`, `LearningSession`,
`quiz_attempt_service`, `mastery_tutor_service`, semantic RAG, and the vanilla
frontend. No vector DB, no ML, no framework migration, no new AI provider.

---

## 24. Explicitly Rejected Directions

Rejected for P10 (evidence: premature or wrong priority at this maturity):
- React/Next.js migration (vanilla SPA is fine; no framework tax justified).
- 2D lesson editor (large new subsystem; loop/debt comes first).
- Mobile application.
- Teacher/classroom platform (no role model exists; different product).
- Collaboration / social learning.
- Microservices (no scale evidence to justify).
- Vector-database / pgvector migration (P9 RAG works; no bottleneck).
- ML/DL learner model (violates architectural mandate; deterministic is right
  at this maturity).
- Multi-tenancy / enterprise SSO.
- Advanced knowledge graph surface.
- Autonomous agents.
- Unrestricted AI chat (already bounded deliberately).
- New AI providers (no architectural need).

---

## 25. Risks

| Risk | Mitigation |
|---|---|
| Loop-closure work touches quiz/tutor frontend + backend | Keep additive; preserve P8/P9 E2E |
| Adding decay changes mastery semantics | Deterministic, additive (keep current score; add retention/review model) |
| Spaced-repetition scope creep | Bound to MVP in P10 scope; exclude plans/goals |
| Migration needed for review data | Additive-only (see section below) |
| mypy floor | Keep zero-new policy |

---

## 26. Final Architectural Decision

Proceed to **P10: Adaptive Remediation & Review Engine**. Rationale (evidence):
the platform's intelligence data is complete and backend-robust, but it is
(1) not decaying (NG-4), (2) not actionable (NG-2), and (3) not loop-closed
(NG-1/3) in the browser. P10 converts latent intelligence into a closed,
time-aware, actionable experience by reusing the existing deterministic
subsystems -- the highest-value, best-leverage, most feasible next step.
