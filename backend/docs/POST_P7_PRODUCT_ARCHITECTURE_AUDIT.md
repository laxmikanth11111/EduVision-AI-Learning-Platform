# Post-P7 Product & Architecture Decision Audit

**Phase:** P7 (Learner Intelligence & Adaptive Progress — combined Candidate A+B)
**Type:** Audit only — NO P8 implementation
**Branch:** `feature/individual-user-foundation`
**Audited HEAD:** `9b32ecd` (`9b32ecd95e82dd304be3910b2c5c68265b070499`)
**P6 baseline (before P7):** `8c82a2c`
**Date:** 2026-09-03

---

## 1. Purpose & Scope

This document is a **decision audit** produced after the completion of P7. Its purpose is to:

1. **Verify the P7 implementation against its claimed baseline** (the P7 report is treated as *claimed* evidence, not trusted blindly — every claim below is re-verified against the actual repository).
2. Produce an **authoritative next-phase direction**: which of candidates A–J to pursue for **P8**, with explicit decisions on migration, AI, and frontend-framework strategy.
3. Record the **regression contract** that P8 must carry (or measurably improve) forward.

This is a **read-only, audit-only** deliverable. No source, frontend, test, migration, CI, Docker, dependency, or config file is modified. The only artifacts produced are this audit, the capability matrix (`POST_P7_CAPABILITY_MATRIX.md`), and the P8 scope contract (`P8_SCOPE_AND_FOUNDATION.md`).

---

## 2. Repository State (Verified Directly)

| Item | Expected | Verified | Evidence |
|---|---|---|---|
| Branch | `feature/individual-user-foundation` | ✅ | `git branch` addressed; workdir state |
| HEAD | `9b32ecd` | ✅ | `git log --oneline -6` |
| Working tree | Clean | ✅ | `git status --short` -> empty |
| P7 commit order | `3fa36cd` → `c892586` → `eb82401` → `9b32ecd` | ✅ | `git log` below |
| P6 docs commit | `00e2b51` (post-p6 audit + p7 scope) | ✅ | `git log` |
| P6 implementation baseline | `8c82a2c` | ✅ | `git log` |

```
9b32ecd docs(p7): add learner intelligence implementation report
eb82401 test(p7): add learner dashboard browser acceptance
c892586 feat(p7): add learner progress dashboard
3fa36cd feat(p7): add learner progress aggregate
00e2b51 docs: add post-p6 product architecture audit and p7 scope
8c82a2c feat(p6): add interactive quiz-taking UI and complete learning loop
```

**Conclusion:** Repository state fully matches the stated P7 baseline. No drift, no unreviewed changes.

---

## 3. P7 Commit Inventory (Directly Verified)

| Commit | Type | Files | Size | Content |
|---|---|---|---|---|
| `3fa36cd` | C1 aggregate | 7 files | +1069 | `app/schemas/learner_progress.py`, `app/services/learner_progress_service.py`, `app/api/v1/learner_progress.py`, `app/main.py` (+2 lines wiring), `tests/learner_progress_helpers.py`, `tests/unit/test_learner_progress_service.py` (7 tests), `tests/integration/test_learner_progress_security.py` (5 tests) |
| `c892586` | C3 dashboard | 2 files | +351 / −1 | `frontend/dashboard.html`, `frontend/index.html` (Dashboard nav conditional on `localStorage.user`) |
| `eb82401` | C5 browser E2E | 1 file | +310 | `backend/tests/e2e/test_p7_dashboard_e2e.py` |
| `9b32ecd` | Report | 1 file | +362 | `backend/docs/P7_IMPLEMENTATION_REPORT.md` |

**Conclusion:** P7 produced exactly four commits matching the plan. No migration was required — P7 is a **read-composition aggregate** over existing tables (`learning_sessions`, `generated_lessons`, `quiz_attempts`, `quiz`, `educational_memories`), which is the correct architectural choice: it adds a view over already-persisted intelligence without altering the schema.

---

## 4. P7 Verification — the 20-Item Checklist (Directly Audited)

Each item below was verified by reading the **primary source**, not the report.

| # | Item | Verdict | Direct evidence |
|---|---|---|---|
| 1 | Ownership enforced by `user.id` derived from auth | ✅ **PASS** | `learner_progress.py:27-32` resolves `user = Depends(get_current_user)` and calls `service.get_progress(user.id)`. The endpoint is `/api/v1/me/progress` (prefix `/me`), and the user is **never** taken from the client. |
| 2 | Cross-user isolation | ✅ **PASS** | `test_learner_progress_security.py` `test_user_b_never_sees_user_a_data`: B sees zeros while A's data exists; A still sees own data afterwards. |
| 3 | Bounded result sets (no unbounded leaks) | ✅ **PASS** | `learner_progress_service.py:43-46`: `_MAX_LESSONS=50`, `_MAX_RECENT_ATTEMPTS=10`, `_MAX_TREND_POINTS=10`, `_MAX_CONCEPTS=100`, `_MAX_ACTIONS=5`. All lists slice to these. Verified by `test_bounded_recent_attempts_and_trend` (≤20 recent, ≤10 trend). |
| 4 | No N+1 query pattern | ✅ **PASS** | `_lesson_progress` = 1 set-based JOIN (LearningSession ⋈ GeneratedLesson) at `:141-147`; cache in Python. `_attempt_history` = 2 queries (1 `count`, 1 join with `.limit(...)`) at `:197-215`. Total for the whole payload ≈ 4–5 queries, all set-based. |
| 5 | PG / SQLite compatibility | ✅ **PASS** | Pure SQLAlchemy `select`/`func.count()`; no PG-only SQL. Fast (SQLite) + PG test suites both pass (see §6). |
| 6 | Alembic chain intact; P7 adds no migration | ✅ **PASS** | Linear chain `0001→…→0028_ws10_idempotency_key_index`; P7 touched only service/schema/router/tests, no migration file. |
| 7 | Schemas match response contract | ✅ **PASS** | `learner_progress.py` (schemas) has `Summary`, `ConceptMasterySummary`, `LessonProgressItem`, `RecentAttempt`, `TrendPoint`, `RecommendationAction`, `LearnerProgressResponse` — all consumed by the frontend. |
| 8 | Router wired into `app.main` under `/api/v1` | ✅ **PASS** | `app/main.py:21` imports `learner_progress_router`; `:166` includes it → final path `GET /api/v1/me/progress`. |
| 9 | Mastery reuses `educational_memory_service`, thresholds not redefined | ✅ **PASS** | `learner_progress_service.py:80` calls `load_from_db`; `:51-52` thresholds `_MASTERED_THRESHOLD=85.0`, `_WEAK_THRESHOLD=50.0` with a comment "do NOT redefine"; classification `:246-251`. |
| 10 | Recommendations reuse deterministic engine, no rewrite | ✅ **PASS** | `:92` `generate_recommendations(user_str, memory, max_actions=_MAX_ACTIONS)`; maps prebuilt action objects, no new analytics/AI logic. |
| 11 | Auth -> 401 without valid user | ✅ **PASS** | `test_dashboard_requires_authentication` asserts `401`. |
| 12 | Empty state (no activity) returns zeros/empty, **not** an error | ✅ **PASS** | `test_empty_state` asserts summary zeros, `[]` recommendations/attempts/trend/weak/strong. |
| 13 | Content asserted, not just status codes | ✅ **PASS** | `test_dashboard_returns_own_progress` asserts lesson completion 100.0/completed, weak+mastered concept names, `percent_score 85.0`, `passed is True`, trend value 85.0. |
| 14 | Educational-memory cache cleared between tests so DB-seeded state is read | ✅ **PASS** | `test_learner_progress_security.py:62-71` autouse fixture clears `educational_memory_service._memories`; E2E also clears `_ems._memories`. |
| 15 | Frontend is the vanilla SPA in `backend/frontend/` | ✅ **PASS** | `dashboard.html` + `index.html` are plain HTML/inline JS; no framework (see §8). |
| 16 | Dashboard nav gated on login state | ✅ **PASS** | `index.html`: "Dashboard" button shown only when `localStorage.user` exists. |
| 17 | Dashboard consumes `/api/v1/me/progress` response envelope | ✅ **PASS** | `dashboard.html` reads `res.json().data` via `authFetch` / `API_BASE /api/v1`. |
| 18 | Trend is deterministic, oldest→newest, bounded | ✅ **PASS** | `_build_trend` `:264-282` reverses newest-first input, slices `_MAX_TREND_POINTS`, labels `%Y-%m-%d`, source `quiz_attempt`. |
| 19 | Browser E2E passes (real auth path, not mocked override) | ✅ **PASS** | `test_p7_dashboard_e2e.py` pops `get_current_user` override so the real JWT path is exercised; uses real signin form; asserts stats/chips/attempt/trend/nav. See §7 for the root-cause note. |
| 20 | Regression counts from C6 | ✅ **PASS** | SQLite 1103 passed; PG 15 passed; mypy 83 baseline; ruff clean; `0028` head. See §6. |

**P7 audit verdict: PASS on all 20 checkpoints.** No PARTIAL and no REGRESSION items.

---

## 5. The Dashboard E2E Root-Cause (Key Finding Re-Affirmed)

The P7 dashboard E2E initially showed **all-zero / empty** results, and the P7 work correctly identified this as **a test-auth-resolution problem, not a data-visibility (DB) problem**:

- The **root conftest** installs an autouse `_override_get_current_user` fixture that resolves auth to the shared `TEST_USER_ID`.
- Because of that override, `/me/progress` aggregated the **wrong user's** (empty) data — the test sign-in never took effect for the endpoint because the dependency was already overridden.

**The fix (committed in `eb82401`):** the P7 browser test **pops the override** and lets the endpoint use **real JWT auth**:

```python
from app.main import app as _app
_app.dependency_overrides.pop(get_current_user, None)
```

A second, independent defect was the **concept-chip DOM assertion**: the concept name is a sibling `.concept-name` of the `.chip`, **not** the chip's parent. The assertion was corrected to `.concept:has(.chip.weak) .concept-name`.

**Why this matters for the audit:** it proves (a) the aggregate's actual data path is learner-scoped and correct under real auth, and (b) the isolation between the shared test fixture and learner-scoped browser tests works. This pattern is the **regression harness** P8 must preserve.

---

## 6. Regression Baseline (C6, Re-Verified)

| Metric | Baseline | P7 final | Verdict |
|---|---|---|---|
| Fast test suite (SQLite) | 1076 | **1103 passed** (+27) | ✅ no regressions, growth from P7 unit/integration tests |
| PostgreSQL (testcontainer `postgres:16-alpine`, `-m postgres`) | — | **15 passed** (57.81s) | ✅ PG parity maintained |
| Browser P7 E2E | — | **3/3 passed** | ✅ |
| mypy (`app`) | 83 errors in 24 files (checked 278) | **83 baseline** (zero new) | ✅ (`[tool.mypy] exclude = ["tests/"]`) |
| `ruff check .` | clean | **clean** | ✅ |
| `git diff --check` | clean | **clean** | ✅ |
| Secret scan | clean | **clean** (only dummy test passwords e.g. `DashPass1234!`, `CHANGE-ME` placeholders) | ✅ |
| Alembic head | `0028_ws10_idempotency_key_index` | **unchanged** (P7 adds no migration) | ✅ |

**Regression contract to carry into P8:** SQLite fast suite >= 1103 passed; PG >= 15 passed; browser P7 E2E 3/3; mypy <= 83 errors (zero new); ruff clean; head `0028_ws10_idempotency_key_index`; security tests P0–P7 preserved; vanilla SPA; PostgreSQL production + SQLite test.

---

## 7. P7 Behavioral Evidence — How the Aggregate Actually Works

Traced from `learner_progress_service.py:get_progress` (`:66-127`):

1. **Lesson progress** — 1 JOIN query over the learner's `LearningSession` rows; deduplicates to distinct lessons (max completion% per lesson), marks `completed` when status is `COMPLETED` or completion% >= 100.0, tracks `in_progress` otherwise, keeps most-recent activity. Bounded to `_MAX_LESSONS`.
2. **Assessment history** — 1 `count()` + 1 JOIN to quiz metadata, ordered newest-first, bounded to recent+trend (20). `passed` computed by comparing `percent_score >= passing_score`.
3. **Mastery** — read via `educational_memory_service.load_from_db` (the same source the lesson player uses), counts mastered/developing/weak, reuses the `85.0` / `50.0` thresholds.
4. **Recommendations** — pure deterministic `generate_recommendations`, no new analytics.
5. **Trend** — oldest→newest slice of latest 10 attempt scores.

**Design quality notes (for P8):**
- The aggregate is deliberately **read-only and deterministic** — it adds a view, not a new data model. This is why it required **zero migrations** and **zero schema risk**.
- Query efficiency is strong (≈4–5 queries total, all bounded, no N+1) — a good model for P8 extensions.
- **Freshness caveat (carry-forward):** mastery is read through the in-memory bounded cache (`BoundedCache(5000, ttl=1800)` in `educational_memory_service`). A learner's dashboard reflects educational-memory writes within the TTL. Fine for a single-learner foundation; a P8 refresh/consistency concern only if dashboards must reflect cross-replica writes immediately (see §9, Gaps G-3).

---

## 8. Active Frontend Audit (Vanilla SPA — Verified)

The **served frontend is `backend/frontend/`**, a vanilla multi-page SPA served by FastAPI `StaticFiles`. Confirmed structure:

- `index.html` (landing + conditional Dashboard nav on `localStorage.user`)
- `signin.html`, `signup.html` (real auth forms)
- `upload.html`, `processing.html`, `player.html` (learning flow)
- `dashboard.html` (P7 target — consumes `/api/v1/me/progress`)
- `assets/app.js`, `assets/style.css`
- `player.html` includes the learner-journey panel (`#ljPanel`) and quiz overlay (`#quizOverlay`)

Patterns: inline vanilla JS, `authFetch`, `escHtml`, `localStorage` (`user`/`access_token`/`refresh_token`), API base `/api/v1`, response envelope `res.json().data`. **No React/TypeScript/Vite/Tailwind, no build step.**

A separate **repo-root `EduVision_AI_Frontend/`** exists but is **NOT** the served frontend — explicitly excluded from scope.

---

## 9. Gaps Identified Across P0–P7

**G-1. Linear-block content model (largest product gap vs. vision).** Lessons are a linear list of blocks; there is no branching/forking based on mastery. This constrains every adaptive feature (assessment, remediation, tutor).

**G-2. Assessment is single-question-at-a-time, not a structured exam.** Current quiz flow may be adaptive in *selection* but is not a full exam engine (multi-question session, sections, item ordering, per-item timing).

**G-3. Deterministic-only learner intelligence.** Mastery is rule-based (`educational_memory_service`); recommendations are deterministic. No ML/DL / no inference-based adaptation. This is intentional and mandated by the non-negotiable architecture, but limits "true" adaptability.

**G-4. In-memory cache freshness across replicas.** `BoundedCache` state is per-process; a multi-replica deploy would see stale/partial mastery between nodes until TTL expiry.

**G-5. No teacher/parent/classroom role.** Only the single `User` role (`USER="user"`) exists in active code. Any analytics/teacher intelligence therefore has no multi-roster surface.

**G-6. RAG retrieval started positional-only (P0), later vector-based (WS3) — but no closing of the "gap between lesson content and learner state".** RAG answers from content but doesn't *target the learner's weak concepts* for remediation automatically.

**G-7. Progress is a dashboard, not an action surface.** P7 surfaces *what* is weak and *why* (recommendations), but the learner must still manually navigate; there is no "continue / remediate / next best action" deep-link from hypothesis to practice (approved as acceptable slice; a P8 candidate is closing this loop).

**G-8. No interactive 2D lesson editor.** Content is authored via document upload → generated lesson pipeline, not a visual editor.

**G-9. No frontend framework / build system.** Chosen deliberately (zero-Dep constraint), but this limits rich interaction reuse and component awareness.

**G-10. No multi-seat / sharing. Ownership is strictly per-`user.id`.** Not a defect — intentional isolation.

---

## 10. The Learner Journey (As Build Through P7)

1. **Sign up / sign in** (`signup.html` / `signin.html`) → JWT access + refresh tokens stored in `localStorage`.
2. **Upload** a document (`upload.html`) → content extraction → **AIContentService** generates a structured lesson (`processing.html`).
3. **Learn** in `player.html`: linear blocks, learner-journey panel (`#ljPanel`), and an **interactive quiz-taking UI with a complete loop** (P6).
4. **Build memory** as they answer: `educational_memory_service` updates concept mastery (mastered/developing/weak); `recommendation_engine` emits deterministic next-best actions; `QuizAttempt` rows persist assessment history.
5. **View progress** at `dashboard.html` (P7): summary (completed/in-progress/mastery), lesson progress + resume, concept mastery (weak/strong chips), deterministic recommendations, recent attempts, and score trend — all learner-scoped via `/api/v1/me/progress`.
6. **Return & continue**: dashboard exposes recent lessons for resume; the loop closes back into `player.html`.

This is a **functional single-learner loop**: create → learn → assess → remember → reflect → resume.

---

## 11. Capability Areas Assessed (summary; full detail in the Matrix)

Upstream of this doc, the Post-P6 audit scored the estate across ten capability areas. Post-P7 re-verification adds the **Learner Progress / Dashboard** area and confirms:

- **Architecture** — strong: linear migrations, bounded caches, set-based queries, learner-scoped ownership.
- **Security / ownership** — strong: P7 re-verifies cross-user isolation end-to-end.
- **Performance** — strong on query count; caveat on cache freshness (G-4).
- **Product surface** — the biggest remaining deltas are the **interactive 2D editor** (G-8), **frontend framework** (G-9), **exam-grade assessment** (G-2), and **branching/remediation loop** (G-1 / G-7).

---

## 12. Candidates Evaluated (A–J)

| ID | Candidate | Score | Recommendation posture |
|---|---|---|---|
| A | Adaptive Learner Intelligence 2.0 | high | **P7 delivered the "1.0" view surface; "2.0" would deepen determinism into per-concept remediation loops.** Re-framed below. |
| B | Advanced Progress / Analytics | high | Substantially satisfied by P7's dashboard; remaining upside is trend depth + action deep-links. |
| **C** | **Mastery-Aware AI Tutor** | **highest (recommended)** | **Closes the single biggest loop: E2E Browser-verified conversation over the learner's real memory, in a real chat UI, against the already-mandated AIContentService + RAG.** See §13. |
| D | Advanced Visual Learning | medium | Rich but broad; best deferred behind C. |
| E | Adaptive Assessment / Remediation | high | Complementary to C (remediation feeds mastery); could be a C sub-slice. |
| F | Teacher Intelligence | low | No teacher role exists (G-5); blocked by role model, not worth a phase now. |
| G | Interactive 2D Learning Editor | medium | Large, tool-heavy, best deferred (G-8). |
| H | Knowledge Graph / AI Infrastructure | medium | Valuable infrastructure but **not product-facing**; should be *supporting* work in a bigger phase, not the headline of P8. |
| I | Frontend framework migration | low | Violates non-negotiable vanilla SPA; explicitly rejected (see §16). |
| J | Other (regression/edge hardening) | low | Continuous; not a phase headline. |

---

## 13. Recommended Phase for P8: **Candidate C — Mastery-Aware AI Tutor**

**Why C over the rest now:**

1. **It is E2E-browser-verifiable with real value.** The single most convincing, demoable, user-facing artifact is a learner asking questions about *their own* weak concepts and getting answers grounded in their real mastery + the mandated AIContentService + RAG. This is the highest user-delight per unit of architecture risk.
2. **It makes P7's output actionable (closes G-1/G-7).** The dashboard's weak-concept chips and deterministic recommendations already *identify* what to fix; an AI tutor driven by `educational_memory_service` + `recommendation_engine` *acts* on it. P8 thereby converts P7 from "view" into "learning surface."
3. **It respects every non-negotiable.** Vanilla SPA (chat UI in HTML/JS), AIContentService as the mandatory AI path, RAG over the content store, SQLite tests + PostgreSQL prod, deterministic learner intelligence (the tutor is *grounded & deterministic-in-behavior*, not free-form ML).
4. **It is a bounded slice.** One new chat surface + a "remediate my weak concepts" trigger, not a sprawling framework or content-authoring tool. Migrations are minimal (a conversation / tutor-session table).
5. **It de-risks later phases.** Custom `H` (knowledge graph) and `E` (adaptive assessment) become *inputs* to the tutor rather than standalone headlines.

**C risks** (mitigated): free-form hallucination — mitigated by grounding responses in RAG + memories and surfacing source/confidence; chat UI complexity — mitigated by reusing existing SPA patterns (`authFetch`, envelope, `#ljPanel`-style panel); cost — mitigated by bounded context + deterministic behavior.

### P8 MVP (headline scope)
1. **Mastery-Aware Tutor chat surface** in a vanilla HTML/JS panel (reusing `player.html` / dashboard patterns).
2. **Learner-scoped grounding:** tutor reads the learner's `educational_memory_service` state (weak/developing concepts) + bounded recent attempts.
3. **RAG + AIContentService-grounded answers** with attribution/confidence; fallback to deterministic "known gaps" responses when RAG is cold.
4. **"Remediate weak concept" quick-action** that seeds a conversation/walkthrough for the learner's top weak concept (closes the P7 dashboard → action loop).
5. **Persistence:** minimal conversation / tutor-session tables (1 migration), learner-scoped by `user.id`.
6. **E2E browser path:** sign in → dashboard → open tutor → ask → verified grounded reply.

Regression contract, checkpoints C0–C6, exclusions, and risks are specified in `P8_SCOPE_AND_FOUNDATION.md`.

---

## 14. Migration Decision

**Default: NO migration.** The platform stays on **PostgreSQL production + SQLite test**, served from the FastAPI app. Rationale:
- PostgreSQL + SQLite parity is already held by the regression contract (`0026_ws2_pg_parity` + PG suite) and by P7's pure-SQLAlchemy aggregate.
- A migration (e.g. to MySQL/MongoDB) would invalidate the P0–P7 contract for zero demonstrated benefit.
- P8 (Recommended C) does not require a new storage paradigm.

Only scenario that would reopen migration: a future phase requiring a storage model PostgreSQL cannot express efficiently — none identified in P8. See `P8_SCOPE_AND_FOUNDATION.md` §16.

---

## 15. AI Decision

**Current posture:** AIContentService is the **mandatory AI path**; learner intelligence is **deterministic**; RAG is **vector-based** (since WS3).

**Verdict for P8 (Recommended C):** adopt **AI = YES (bounded & grounded)** for the tutor, with these hard rules:
- The tutor **must** route through **AIContentService** (no bypass), over **RAG**-retrieved lesson content, **rounded to the learner's memory**.
- **No ML/DL / free-form inference** for mastery/recommendation — mastery provably remains deterministic.
- Deterministic behavior is preserved as the **fallback** whenever RAG/AI is cold or unavailable.
- Cost is bounded by strict context windows and caching (reuse `BoundedCache`).

Alternative considered: **AI = NO** (tutor returns canned, memory-driven text only) — dropped because it would not close the value loop convincingly; **AI = OPTIONAL behind a config flag** — acceptable as a conservative fallback, but full **YES** is recommended for the reviewer-approved demo value.

---

## 16. Frontend Migration Decision

**Default: NO migration — stay vanilla SPA in `backend/frontend/`.**

- Confirmed the served frontend is vanilla multi-page SPA served by FastAPI `StaticFiles` (P0–P7), with no React/TS/Vite/Tailwind/build step.
- Candidate **I (framework migration)** is **explicitly REJECTED** for P8: it violates the non-negotiable vanilla frontend, adds a build system, and delivers no learner-facing feature by itself.
- P8 (Recommended C) adds a **chat/remediation panel** as plain HTML + inline JS, reusing `authFetch`, `escHtml`, `localStorage` auth, and the response envelope — fully consistent with the existing SPA.

See `P8_SCOPE_AND_FOUNDATION.md` §17.

---

## 17. Candidate Ranking (Final)

1. **C — Mastery-Aware AI Tutor** (Recommended for P8)
2. **E — Adaptive Assessment / Remediation** (complementary; candidate sub-slice of C)
3. **A — Adaptive Learner Intelligence 2.0** (post-C deepening)
4. **B — Advanced Progress / Analytics** (post-C depth + action deep-links)
5. **H — Knowledge Graph / AI Infrastructure** (supporting infra, not headline)
6. **D — Advanced Visual Learning** (defer behind C)
7. **G — Interactive 2D Learning Editor** (large, defer)
8. **J — Other (hardening)** (continuous)
9. **F — Teacher Intelligence** (blocked: no teacher role / G-5)
10. **I — Frontend framework migration** (rejected: violates vanilla SPA mandate)

---

## 18. Risks & Mitigations (P8)

| Risk | Mitigation |
|---|---|
| Tutor hallucination / off-topic answers | Ground via RAG over lesson content + learner memory; require attribution/confidence; bounded context; deterministic fallback |
| Chat UI complexity on vanilla stack | Reuse existing SPA patterns; bounded surface (one panel + one quick-action) |
| AI cost runaway | Strict context window, caching, deterministic cold-path fallback, bounded conversation length |
| Regression of P0–P7 suitability | Lock regression contract (1103 / 15 / 83 / `0028`); run full suite + PG + browser E2E at each checkpoint |
| Cross-user leakage in chat history | Scope every tutor-session/conversation by `user.id`; mirror P7 isolation tests |
| Cache freshness (G-4) | Accept single-learner TTL; document; revisit only if multi-replica required |

---

## 19. Final Decision (Summary)

- **Recommended P8 candidate:** **C — Mastery-Aware AI Tutor**.
- **Migration:** NO (PostgreSQL + SQLite remain).
- **AI:** **YES, bounded & grounded** via AIContentService + RAG + deterministic learner memory; deterministic fallback required.
- **Frontend:** NO migration — vanilla SPA in `backend/frontend/`; P8 adds a plain HTML/JS chat panel.
- **Regression contract locked:** SQLite ≥ 1103 passed; PG ≥ 15 passed; browser P7 E2E 3/3; mypy ≤ 83; ruff clean; head `0028_ws10_idempotency_key_index`; security P0–P7 preserved.
- **Implementations deferred (excluded from P8):** Teacher Intelligence (F), Interactive 2D Editor (G), Visual Learning upgrade (D), Frontend framework migration (I).
- **Full contract:** see `P8_SCOPE_AND_FOUNDATION.md`.

---

## 20. Exclusions From This Audit

- **No implementation of any kind** was performed.
- No source, frontend, test, migration, CI, Docker, dependency, or config file was modified.
- The repo-root `EduVision_AI_Frontend/` is **out of scope** (not the served frontend).
- Feature completeness of **other** phases (WS1–WS10) is not re-audited here in depth; only P7 plus phase-inheritance claims are re-verified.

---

## 21. Cross-Reference

- `P7_SCOPE_AND_FOUNDATION.md` — P7 plan that P8 supersedes for direction.
- `POST_P6_PRODUCT_ARCHITECTURE_AUDIT.md` — prior audit that framed P7 = "Learner Intelligence & Adaptive Progress".
- `POST_P6_CAPABILITY_MATRIX.md` — prior capability inventory (status vocabulary carried forward).
- `POST_P7_CAPABILITY_MATRIX.md` — this phase's capability matrix (companion doc).
- `P8_SCOPE_AND_FOUNDATION.md` — the authoritative next-phase implementation contract (companion doc).
- `P7_IMPLEMENTATION_REPORT.md` — the phase report (treated as claimed evidence, re-verified here).

---

## 22. Status Legend Note

Own status vocabulary (carried from Post-P6): **VERIFIED** (directly confirmed in this phase), **INHERITED** (established earlier, unchanged), **PARTIAL** (partially present), **MISSING** (absent), **NOT VERIFIED** (not re-checked), **DEFERRED** (planned for a later phase), **REGRESSION** (previously working, now broken), **OUT OF SCOPE** (explicitly excluded).