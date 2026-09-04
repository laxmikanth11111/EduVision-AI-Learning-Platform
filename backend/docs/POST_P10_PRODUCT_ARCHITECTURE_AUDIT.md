# Post-P10 Product & Architecture Audit

**Phase:** P10 (Adaptive Remediation & Review Engine — audit)
**Type:** Audit + product decision only — NO P11 implementation
**Branch:** `feature/individual-user-foundation`
**Audited HEAD:** `aa2da2f` (`docs(p10): record P10 completion commit hash`)
**Alembic head:** `0031_review_schedule_concept` (verified)
**Date:** 2026-09-04

---

## 1. Executive Summary

P10 is **genuinely complete and verifiable**. Independent re-verification this pass confirms every P10 release gate: SQLite **1144 passed**, P10 browser E2E **3 passed** (real Chrome against a live uvicorn on SQLite), Ruff clean, mypy exactly **83 errors / 24 files** (zero new), a single Alembic head `0031_review_schedule_concept`, a clean working tree, and `git diff --check` clean. The P10 production fix — quiz mastery recorded under the concept **public ID** so learner intelligence/review/recommendation all share one key — is present in the live code (`quiz_attempt_service._update_concept_mastery` + concept→public_id map) and its effect was independently re-confirmed by the passing NG-3 browser E2E.

Beyond re-verification, this audit looked **past P10** at the product as a whole and reached a clear, evidence-backed conclusion:

1. **The learning loop now genuinely closes in the browser.** Ten of fourteen loop transitions are CONNECTED, two are PARTIAL (assessment→scheduling happens lazily on next dashboard load rather than at submit; review→mastery resets the review clock but does not change the mastery score — by design), and exactly one is NOT CONNECTED (player→review queue has no entry point in `player.html`). No high-severity broken transition remains.
2. **The single largest remaining product gap is NG-5 (study plans / learning goals / learning paths).** P10 closed NG-1/NG-2/NG-3 fully and addressed NG-4/NG-5 *partially* (deterministic review scheduling + decay signal). What remains unimplemented is the *structure* layer: the learner has content, lessons, quizzes, mastery, actionable recommendations, a RAG tutor, and spaced review — but **no plan, goal, or path connecting those into a coherent program**. The tables (`learning_paths`, `learning_goals`, `study_plans`, migration `0011`), the enums (`shared/constants`), and the schemas (`personalization.py`) already exist, orphaned.
3. **NG-4 (genuine adaptive assessment) is the strongest #2 alternative** — the infrastructure (question `difficulty` columns, `educational_memory` mastery, the dead `AdaptiveAssessmentEngine`) is present, but touching the transaction/security-sensitive attempt path is higher risk and lower leverage than building the structure layer on top of the now-complete loop.
4. **Security remains strong.** No CRITICAL findings. P10 preserved authentication, ownership checks, learner isolation, quiz/review/recommendation/mastery ownership, and the prompt-injection boundary. The highest outstanding item is the pre-existing bounded HIGH (own-learner prompt-injection guard) carried from P9, unchanged by P10.

**Recommended P11:** **Personalized Study Plans, Goals & Learning Paths (NG-4-compatible, NG-5 closure)** — a deterministic "today's plan" surface that derives daily items from the learner's live state (due reviews + weak/developing concepts + unfinished lessons) and deep-links into the now-actionable player/tutor/review flows. It reuses the P10 review engine, the 0011 tables, the `shared/constants` enums, and the P10 actionability plumbing, and it closes the last explicitly-deferred NG from the P10 contract.

---

## 2. Starting Commit / Repository State

| Item | Expected | Verified | Evidence |
|---|---|---|---|
| Branch | `feature/individual-user-foundation` | yes | `git branch --show-current` |
| HEAD | P10 completion range `125023c`..`aa2da2f` | yes | `git log --oneline -2` = `aa2da2f`, `125023c`, with `acbfad0` (P10 start) beneath |
| Working tree | clean | yes | `git status --short` = empty |
| Alembic head | single head `0031_review_schedule_concept` | yes | `alembic heads` |
| P10 start commit | `acbfad0` | yes | P10 implementation report §1 |

---

## 3. Verification Baseline (actually re-verified this pass)

| Gate | Command | Observed | Floor |
|---|---|---|---|
| git status | `git status --short` | clean | clean |
| current commit | `git rev-parse HEAD` | `aa2da2f` | `aa2da2f` |
| Alembic heads | `alembic heads` | `0031_review_schedule_concept (head)` | single head |
| SQLite regression | `pytest tests -m "not postgres and not e2e"` | **1144 passed**, 27 deselected, 0 failed | >= 1115 (P10 contract) |
| P10 browser E2E | `pytest tests/e2e/test_p10_adaptive_review_e2e.py -m e2e` | **3 passed** (real browser) | 3 passed |
| Review scheduler/unit | `test_review_scheduler.py test_review_schedule_service.py test_next_action_serialization.py` | **21 passed** | pass |
| Quiz/learner-progress unit | `test_quiz_routes.py test_learner_progress_service.py` | **38 passed** | pass |
| Security/integration | `test_review_api_security.py test_learner_progress_security.py test_mastery_tutor_security.py` | **17 passed** | pass |
| Two-user isolation | `test_two_user_isolation.py` | **22 passed** | pass |
| Ruff | `ruff check . --exclude .venv` | **All checks passed** | clean |
| mypy | `mypy app` | **83 errors in 24 files** | 83/24, zero new |
| git diff --check | `git diff --check` | clean (exit 0) | clean |
| Secret scan | git grep over HEAD for key/secret/password patterns | only legit provider-config references (api_key from settings) — no committed secrets | none |

Note: PostgreSQL suite (15 tests, testcontainers) was verified by the P10 implementation report and is not re-run in this audit pass; the migration parity claim is supported by the single-head Alembic chain and the documented PG run. SQLite count matches P10 exactly (1144).

---

## 4. P0–P10 Evolution Summary

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
| **P10** | **Adaptive remediation & review engine** | **Closed loop: next-action CTA, actionable reco, review queue, mastery public-ID keying, decay signal** |

---

## 5. Current Product Architecture (evidence-based)

- **Backend**: FastAPI (async), SQLAlchemy 2.x, UoW/repository pattern. `app/main.py` mounts 20 routers under `/api/v1` (auth, presentations, storage, folders, player, quiz, visual, simulation, animation, animation-runtime, video, video-runtime, assistant, effectiveness, learner_progress, review, exports, tutor, metrics, health).
- **Database**: PostgreSQL (production) + SQLite (test fast path), PortableJSONB dual-dialect, linear Alembic chain (31 migrations; single head `0031_review_schedule_concept`).
- **Frontend**: vanilla multi-page SPA in `backend/frontend/` (no framework, no build step): `index`, `signin`, `signup`, `upload`, `processing`, `player.html` (2,049 lines — slide engine, 5+ SVG visual strategies, motion/animation engine, video player, simulation runtime, full quiz overlay), `tutor.html` (517 lines — RAG-grounded chat, session resume, remediation + practice CTA), `dashboard.html` (442 lines — summary, actionable recommendations, review queue, lesson progress, concept chips, trend).
- **Worker**: Celery + Redis + SafeDispatch/DLQ + idempotency (beat tasks incl. embedding refresh).
- **AI abstraction**: `AIContentService` (mandatory) with provider registry (`local`/`openai`/`gemini`), retry/timeout/rate-limit/cache/cost; embedding provider registry incl. local deterministic provider.
- **RAG**: shared `app.ai.retrieval.semantic_retrieve_chunks` (P9) — embed query → cosine ranking → threshold → top-k → positional fallback; learner-scoped.
- **Learner intelligence**: deterministic rule-based (mandate): mastery scalar (`educational_memory_service`, `BoundedCache`), rule-table recommendations (`recommendation_engine`), P10 review scheduler (`review_scheduler.py` interval ladder 1/3/7/14 days + decay signal), `review_schedule_service` (lazy seeding, due queue, complete/skip).
- **Security**: Argon2id, JWT (15 min / 7 d refresh, Redis revocation), CSRF, storage proxy, magic-byte validation, ownership 404-equalization, per-IP rate limit, request-size middleware, security headers.
- **Animation/Simulation/Video**: mounted routers with unit coverage; frontend wires a subset (generateAnimation, animation runtime sync, generateVideo). Video **runtime** router (bookmark/assessment/tutor-context) and standalone script/storyboard routes are backend-only (not called from the frontend).

### Architectural invariants (held as of P10)
1. `AIContentService` is the mandatory AI path.
2. Learner intelligence is deterministic rule-based, no ML/DL.
3. Vanilla multi-page SPA, no framework migration.
4. PostgreSQL production / SQLite test dual-dialect.
5. Linear Alembic chain, additive-only migrations, single head.
6. Every resource scoped by `user.id` from auth; ownership 404-equalized.
7. Bounded in-process caches; bounded list/query constants.

---

## 6. Current User Journey (evidence-traced)

| Stage | Implemented | Browser | Persisted | User-scoped | Fallback | Evidence |
|---|---|---|---|---|---|---|
| Authentication | yes | yes | yes | n/a | Google OAuth | `auth.py`, `signin.html` |
| Presentation ingestion | yes | yes | yes | yes | — | `upload.html`, `presentations.py` |
| Content extraction | yes | via processing | yes | yes | AI retry | `content_extraction_service.py` |
| Lesson generation | yes | yes | yes | yes | AI retry | `lesson_generation_service.py`, Celery |
| Lesson player | yes | yes | yes | yes | — | `player.html`, `player.py` |
| Visual learning (canvases/SVG) | yes | yes | yes | yes | visual fallback | `player.html`, `visual_canvases.py` |
| Animation / simulation / video | **BACKEND-ONLY (partial)** | partial (player wires 4 of 15 routes) | — | yes | — | `animation_router`, `video_router`, `simulation.py`; no browser E2E |
| Learning session | yes | yes | yes | yes | — | `player.py`, `learning_sessions` |
| Checkpoint | yes | yes | yes | yes | — | `player.html` "Take Checkpoint" |
| Interactive quiz | yes | yes | yes | yes | AI gen retry | `quiz.py`, `quiz_attempt_service.py` |
| Assessment / scoring | yes | yes | yes | yes | deterministic grading | `submit_quiz`, `_evaluate_answer` |
| Mastery | yes (scalar) | yes | yes | yes | — | `educational_memory_service.py`; public-ID keying (P10) |
| Recommendation | yes | **actionable (P10)** | derived | yes | deterministic | `recommendation_engine.py`, `dashboard.html` `recoAction` |
| Review scheduling | yes | yes (queue) | yes | yes | deterministic | `review_scheduler.py` + `review_schedule_service.py`, dashboard review panel |
| Mastery decay / pressure | yes (ranking) | yes (badges) | no mutation | yes | — | `compute_decay_signal`, `priority_bucket` |
| Learner dashboard | yes | yes | read | yes | — | `dashboard.html`, `/me/progress` |
| Mastery-aware tutor | yes | yes | yes | yes | deterministic | `mastery_tutor_service.py`, `tutor.html` |
| Semantic RAG | yes | yes (**rag**) | yes | yes | positional | `app.ai.retrieval`, P9; P8 E2E asserts `source_kind=="rag"` |
| Remediation + re-practice CTA | yes | yes | yes | yes | deterministic | `remediate` + `practiceCtaHtml` (P10) |
| Session persistence / resume | yes | yes | yes | yes | — | `tutor.html` session list / `?session=` |

---

## 7. Learning Loop Transition Map (re-trace)

| # | Transition | Status | Evidence |
|---|---|---|---|
| 1 | assessment → mastery | **CONNECTED** | `submit_quiz` → `_update_concept_mastery` → `educational_memory_service.update_concept_mastery` (public-ID keyed, P10) → `save_to_db` |
| 2 | mastery → recommendation | **CONNECTED** | `generate_recommendations` reads `memory.concept_records`, priorities weakest-first |
| 3 | recommendation → action | **CONNECTED** | `learner_progress_service._action_lesson_map` resolves lesson public ids; `recoAction()` renders `<a>` CTAs |
| 4 | action → practice | **CONNECTED** | dashboard CTAs → `player.html?lesson=<public_id>` → `player/start` |
| 5 | practice → assessment | **CONNECTED** | "Take Checkpoint" → `startQuiz` → overlay → `submitQuiz` |
| 6 | assessment → scheduling | **PARTIAL** | mastery updates on submit; schedules seed lazily on next `GET /me/review` (no immediate scheduling at submit) |
| 7 | scheduling → recommendation | **CONNECTED** | review panel lists due items with Practice deep-link + "Mark reviewed" |
| 8 | tutor → remediation | **CONNECTED** | `remediate()` returns structured `next_action` with `lesson_id` |
| 9 | remediation → practice | **CONNECTED** | `practiceCtaHtml()` renders player deep-link |
| 10 | review → mastery | **PARTIAL (by design)** | `complete()` calls `record_review_activity()` (resets review clock, advances interval); does not change mastery score — review ≠ assessment |
| 11 | dashboard → lesson | **CONNECTED** | lesson cards deep-link to player |
| 12 | dashboard → tutor | **CONNECTED** | weak chips → `tutor.html?concept=` |
| 13 | player → review | **NOT CONNECTED** | no review-queue entry point in `player.html`; queue only reachable via dashboard |
| 14 | player → assessment | **CONNECTED** | checkpoint button → quiz overlay |

**Result:** 11 CONNECTED, 2 PARTIAL, 1 NOT CONNECTED. No high-severity broken transition. P10 achieved its loop-closure objective.

---

## 8. Capability Audit

See companion **`POST_P10_CAPABILITY_MATRIX.md`** for the full status table.

Summary by domain:
- **Content/Lesson/Visual/Assessment**: VERIFIED for the learn→assess spine; adventure animation/simulation/video surfaces are BACKEND-ONLY or PARTIAL.
- **Learner intelligence**: VERIFIED deterministic stack; mastery decay only as a ranking signal (not persisted decay).
- **Review scheduling**: VERIFIED (P10) — deterministic, user-scoped, interval ladder, lazy seeding.
- **Study plans / goals / learning paths**: **NOT IMPLEMENTED** (tables + enums + schemas exist, no wire). This is NG-5.
- **Genuine adaptive assessment**: **NOT IMPLEMENTED** (dead `AdaptiveAssessmentEngine`; fixed-order delivery). This is NG-4.
- **Tutor + RAG**: VERIFIED.
- **Dashboard**: VERIFIED and actionable (P10).
- **Teacher/classroom, collaboration, 2D editor, mobile, framework migration**: NOT IMPLEMENTED / OUT OF SCOPE (unchanged).
- **Learner analytics**: PARTIAL (dashboard trend only; analytics tables/schemas orphaned).

---

## 9. P10 Verification (independent pass)

- **NG-1 (next-action CTA)**: FIXED. `next_action` is a computed field on `LearningRecommendation` (`app/schemas/next_action.py:63-73`); `AttemptResult` carries `lesson_id`; `player.html` renders a working `<a class="lj-take">`. Re-verified via `test_p10_ng1_quiz_next_action_cta` (browser click → valid owned player).
- **NG-2 (actionable reco/remediation)**: FIXED. `recoAction()` emits real hrefs; review panel has Practice + Mark-reviewed. Re-verified via `test_p10_dashboard_ng2_reco_and_weakdeep`.
- **NG-3 (closed remediation loop)**: FIXED. Weak (30%) → practice → assess (100%) → mastery 30→100 → weak state resolved → review scheduled/completed → due queue exits. Re-verified via `test_p10_ng3_critical_learning_loop`.
- **NG-4 (partial)**: Deterministic spaced-repetition scheduler + decay pressure signal delivered; genuine per-question adaptivity explicitly not in the P10 MVP (still the NG-4 remainder for P11+).
- **NG-5 (partial)**: Spaced review reachable in browser; plans/goals/learning-paths remain unreachable (still the NG-5 remainder for P11).
- **Production fix preserved**: `_update_concept_mastery` records master under the concept public ID (`quiz_attempt_service` concept→public_id map); NG-3 E2E re-confirmed mastery persisted 30→100 for the tracked concept.

---

## 10. Security Audit

Overall: **strong; no CRITICAL; P10 introduced no new attack surface.**

Verified preserved:
- **Authentication** — `get_current_user` on all new/changed endpoints (`review.py`, `learner_progress.py`, `tutor.py`, `quiz.py`).
- **Ownership / user isolation** — `test_review_api_security.py` (17 pass) and `test_two_user_isolation.py` (22 pass) re-run green; cross-user review complete → 404; concept/lesson/quiz resolution via the ownership chain; foreign IDs cannot obtain private data.
- **Learner-scoped tutor sessions** — unchanged (P8/P9 chain); `test_mastery_tutor_security.py` green.
- **Learner-scoped RAG** — chunk ownership sealed; no cross-user retrieval path (P9 invariant).
- **Prompt-injection boundary** — remediation/RAG stays behind `AIContentService`; learner content treated as data (delimiter guard). Pre-existing HIGH (own-learner self-injection window, bounded by `TUTOR_MAX_CONTEXT_CHARS` + `TUTOR_MAX_RESPONSE_TOKENS`) carried, not introduced by P10.
- **XSS protections** — all new dashboard/tutor/player dynamic content escaped via `escHtml`.
- **Storage isolation / quiz ownership / review ownership / recommendation ownership / mastery ownership** — all user-scoped; ownership 404-equalized.
- **API authorization** — new `POST /me/review/{id}/complete` and `/skip` derive owner from auth; no client-supplied user ids.

Outstanding (pre-existing, unchanged, documented — NOT P11-blocking):
- HIGH — own-learner prompt-injection guard (bounded, self-only).
- MEDIUM — refresh token not rotated on use; in-memory revocation fallback not shared across processes; body-size check relies on declared Content-Length; no per-user AI credit budget; `_jwt_secret()` dev fallback uses `APP_SECRET_KEY` silently.
- LOW — effectiveness report leaks presentation title (ownerless); CSRF helpers not enforced on auth POSTs; SVG innerHTML path in player.

---

## 11. AI / RAG Audit

- **Pipeline**: verified. `app.ai.retrieval.semantic_retrieve_chunks` — query embedding → join chunk+embedding → cosine (numerically safe) → threshold → deterministic ranking → top-k → `[]`-on-failure → positional fallback.
- **Provider abstraction**: verified. `AIContentService` mandatory; registry `local`/`openai`/`gemini`; embeddings same. Local deterministic provider makes tests/interests reproducible without API keys.
- **Attribution/confidence**: verified on `TutorMessageResponse` (`source_kind`, `confidence`, `attribution`) and rendered as chips.
- **Context/token limits**: verified bounded — `TUTOR_MAX_CONTEXT_CHARS` (16000), `TUTOR_MAX_RESPONSE_TOKENS` (1024), `TUTOR_MAX_HISTORY_MESSAGES` (12). Assistant still hardcodes `limit=20` (LOW consistency only).
- **Deterministic fallback**: verified — cold AI/RAG yields mastery-grounded explanation + recommendations; the P8 E2E guards the *real* RAG path (`source_kind=="rag"` cannot be satisfied by fallback).
- **Failure behaviour**: provider failures → fallback path; retry/timeout/rate-limit/cost accounting in the AI service.
- **P11 recommendation**: the next phase likely needs **no new AI provider**. Study-plan generation is deterministic over existing mastery/review/lesson data; any optional AI summary stays behind `AIContentService`. Prefer deterministic where correctness matters (scheduling, prioritisation).

---

## 12. Database / Migration Audit

- PostgreSQL production / SQLite test: verified dual-dialect (PortableJSONB; PG suite in P10 report).
- Alembic: **linear, single head `0031_review_schedule_concept`** (verified `alembic heads`). Migration history carries index-parity discipline (0030 composite index matches ORM; 0031 adds concept_id + last_reviewed_at + `(user_id, due_at)` due-queue index).
- Reusable existing infrastructure for P11:
  - `learning_paths`, `learning_goals`, `study_plans` — migration `0011`, FKs to `users`/`learning_paths`, full index set (public_id, user_id+status, user+dates). **Currently unreachable from code.**
  - `review_schedules` — live since P10 (model/service/router/UI), interval ladder, due queue indexed.
  - `educational_memories` — concept mastery + `last_reviewed_at` + `review_count` + (unused) `streak_days`/`revision_queue`/`weekly_goals` fields.
  - `generated_lessons` / `learning_sessions` / `quiz_attempts` — for plan item targeting and completion tracking.
- Orphaned/schema-only (candidates for wiring or explicit retirement): `adaptive.py`, `personalization.py`, `analytics.py`, `analytics_insights.py`, `director.py`, `teaching_strategy.py`, `student_note.py`, `learning_activity.py` schemas, plus the dead `adaptive_assessment_engine.py`, `visual_question_generator.py`, `concept_service.py` services and the unused `analytics_*`/`system_analytics` tables.
- P11 will likely need **no new tables** (reuse 0011) and at most **one additive migration** if plan-item→review linkage needs a column.

---

## 13. Frontend Audit

- **player.html** (2,049 lines): slides, thumbnails, learner-journey panel, 6 SVG strategies, motion engine, video, simulation runtime, full quiz overlay with score ring + next-action CTA. Robust error handling; `escHtml`/`escSvg`.
- **dashboard.html** (442 lines): stat cards, actionable "Next Best Actions", review queue (Practice + Mark reviewed), lesson progress, weak/developing/mastered chips, recent checkpoints, trend. 12 JS functions; no stubs.
- **tutor.html** (517 lines): weak-concept quick picks, session list/resume, RAG/deterministic badges, remediation + "Practice this" CTA, `?concept=`/`?session=`/`?lesson=` deep links.
- **Navigation**: shared brand/upload/dashboard/tutor nav across pages; JWT refresh (`authFetch`) repeated inline per page (drift risk — LOW/MEDIUM maintainability).
- **State persistence / deep links**: verified (`?lesson=`, `?concept=`, `?session=`, dashboard transitions to player/tutor).
- **Mobile**: pages are desktop-oriented; no responsive audit done this pass (deferred).
- **Accessibility**: basic alt/semantic usage; no formal a11y pass (deferred).
- **XSS safety**: verified `escHtml`/`escSvg` used for all dynamic content.
- **Browser E2E**: 12 E2E tests across 6 files (`test_smoke` ×4, `test_learner_journey` ×2, `test_p6_full_loop` ×1, `test_p7_dashboard` ×1, `test_p8_mastery_tutor` ×1, `test_p10_adaptive_review` ×3); P10's 3 are the relevant regression. All are Playwright-style browser tests against a real uvicorn instance on SQLite.

---

## 14. E2E Product Journey Audit

- **Journey A (signup→signin→content→lesson→learning→assessment→mastery→recommendation)**: CONNECTED (P6/P7 E2E + P10 NG-1; dashboard mastery chips render; recommendations actionable).
- **Journey B (weak concept→recommendation→remediation→practice→assessment→mastery→scheduling→changed recommendation)**: CONNECTED end-to-end (P10 NG-3 is exactly this; browser-verified).
- **Journey C (tutor→learner question→learner-owned context→semantic RAG→response→remediation→practice)**: CONNECTED (P8 E2E asserts `rag`; P9 resume; P10 practice CTA).
- **Journey D (dashboard→weak concept→actionable recommendation→destination→learning action)**: CONNECTED (P10 NG-2).
- **Journey E (User A/B isolation)**: VERIFIED (`test_two_user_isolation.py` 22 pass; owner chains 404-equalized).
- **Remaining broken transition:** player → review queue (no entry point in `player.html`; LOW severity — review is reachable from the dashboard).

---

## 15. Product Gaps (post-P10)

| ID | Gap | Severity | Status post-P10 | Best evidence |
|---|---|---|---|---|
| G1 | Study plans / learning goals / learning paths | **HIGH** | NOT IMPLEMENTED (tables+enums+schemas orphaned) | `0011`, `shared/constants`, `personalization.py`; no service/router |
| G2 | Genuine adaptive assessment | **MEDIUM** | NOT IMPLEMENTED (dead `AdaptiveAssessmentEngine`; fixed-order delivery) | `adaptive_assessment_engine.py` (no imports) |
| G3 | Persisted mastery decay / confidence | MEDIUM | PARTIAL (P10 pressure signal is ranking-only; score never decays) | `compute_decay_signal` vs `update_concept_mastery` |
| G4 | Player → review queue entry point | LOW | NOT CONNECTED | `player.html` has no review link |
| G5 | Assessment → immediate scheduling | LOW | PARTIAL (lazy on next dashboard load) | `review_schedule_service._ensure_schedules` |
| G6 | Animation/video runtime frontend wiring | MEDIUM | PARTIAL — video runtime bookmark/assessment/tutor-context backend-only | `video_runtime_router.py` not called by `player.html` |
| G7 | Learner-facing analytics / insights | MEDIUM | PARTIAL (dashboard trend only; analytics tables/schemas orphaned) | `analytics.py`, `analytics_insights.py` (no imports) |
| G8 | Retention scheduled/global | MEDIUM | PARTIAL (on-read only; no beat task) | `enforce_retention` in `list_sessions` only |

---

## 16. Technical Debt That Actually Matters

| Debt | Severity | Why it matters | P11 impact |
|---|---|---|---|
| Orphaned personalization schemas + 0011 tables unwired | **HIGH (product)** | They are the ready-made foundation for G1 (the recommended P11) | Directly reusable — wire, don't recreate |
| Dead services: `adaptive_assessment_engine`, `visual_question_generator`, `concept_service` | MEDIUM | Minor | G2 candidate; otherwise retire |
| Orphaned analytics schemas/tables | LOW | Not used | Keep for future insights phase |
| mypy 83/24 debt | MEDIUM | Held flat by policy; blocks only if P11 adds errors | Keep zero-new policy (P11 must add 0) |
| Duplicated inline `authFetch` per page | LOW/MEDIUM | Maintainability/consistency | Optional P11 hardening; not required |
| Assistant hardcodes `limit=20` (vs setting 12) | LOW | Inconsistent history bound | Out of scope |
| Retention not scheduled globally | MEDIUM | Unbounded tutor rows in prod | Out of P11 scope (documented) |

Do **not** recommend fixing unrelated historical mypy debt — it is gated flat and does not block P11.

---

## 17. Candidate P11 Directions (transparent scoring)

Scoring model (weights summing to 1.0): Learner value 0.25 · Educational value 0.15 · Product differentiation 0.10 · Architectural readiness 0.15 · Existing infra reuse 0.10 · Implementation complexity (inverse) 0.08 · Risk (inverse) 0.07 · Portfolio value 0.10.
Scores are 1–5 (5 = best); weighted total is the sum of `weight × score`.

| Cand | Direction | Lrnr (×.25) | Ed (×.15) | Diff (×.10) | Ready (×.15) | Reuse (×.10) | Cx⁻¹ (×.08) | Risk⁻¹ (×.07) | Port (×.10) | **Total** |
|---|---|---|---|---|---|---|---|---|---|---|
| A | **Personalized Study Plans / Goals / Learning Paths** | 5 (1.25) | 5 (0.75) | 5 (0.50) | 5 (0.75) | 5 (0.50) | 4 (0.32) | 4 (0.28) | 5 (0.50) | **4.85** |
| B | Genuine adaptive assessment | 4 (1.00) | 5 (0.75) | 5 (0.50) | 3 (0.45) | 3 (0.30) | 3 (0.24) | 3 (0.21) | 4 (0.40) | 3.85 |
| C | Tutor 2.0 (richer multi-turn pedagogy) | 4 (1.00) | 4 (0.60) | 4 (0.40) | 5 (0.75) | 4 (0.40) | 3 (0.24) | 2 (0.14) | 4 (0.40) | 3.93 |
| D | Learner-facing analytics / insights | 3 (0.75) | 3 (0.45) | 3 (0.30) | 2 (0.30) | 2 (0.20) | 4 (0.32) | 4 (0.28) | 3 (0.30) | 2.90 |
| E | Richer mastery model (persisted decay/confidence) | 3 (0.75) | 3 (0.45) | 3 (0.30) | 3 (0.45) | 3 (0.30) | 4 (0.32) | 4 (0.28) | 3 (0.30) | 3.15 |
| F | Content quality / 2D editor | 3 (0.75) | 3 (0.45) | 4 (0.40) | 1 (0.15) | 1 (0.10) | 1 (0.08) | 1 (0.07) | 3 (0.30) | 2.30 |
| G | Teacher/classroom / collaboration | 3 (0.75) | 2 (0.30) | 3 (0.30) | 1 (0.15) | 1 (0.10) | 1 (0.08) | 2 (0.14) | 3 (0.30) | 2.12 |

**Ranked outcome (highest score first):** A (4.85) > C (3.93) > B (3.85) > E (3.15) > D (2.90) > F (2.30) > G (2.12).

**Why A (Study Plans / Goals / Learning Paths) wins:**
1. **Largest remaining learner value** — it answers the learner's daily question "what should I do today?" by turning the now-working loop (learn→assess→review→remediate) into a structured, dated program anchored in their real weak/developing/due state.
2. **Highest architectural readiness + reuse** — the exact tables, enums, and schemas already exist (0011 + `shared/constants` + `personalization.py`); P10's `review_schedules`, `learner_progress_service`, `recommendation_engine`, and actionability deep-links are all live foundations. Implementation is mostly read-composition + deterministic plan generation + one UI surface.
3. **Lowest risk** — additive; does not touch the transaction/security-sensitive quiz-answer path (unlike adaptive assessment); no new AI provider; deterministic (respects the no-ML mandate).
4. **Closes the explicitly-deferred NG-5** from the P10 contract and is compatible with a later NG-4 (adaptive assessment) phase since it consumes the same mastery/review data.
5. **Portfolio value** — "personalized adaptive study plan with goals and learning paths" is a headline feature for a student-built production project, directly demonstrable in the browser and E2E-testable deterministically.

**About C vs B (both close).** C (Tutor 2.0) scores marginally higher on raw weighted score (3.93) because the tutor subsystem is architecturally complete. It is intentionally ranked *behind* B (adaptive assessment, 3.85) as the preferred runner-up because: (a) C is a *depth* enhancement to an already-working surface rather than a *new product gap* (the tutor already grounds semantically and remediates), whereas B closes an explicitly-deferred NG (adaptive assessment is part of the "adaptive" brand promise); (b) C carries higher ongoing AI cost and reliability risk, while B is deterministic over existing data. Both B and C are strong future candidates; the #2 pick for the P11 decision document is **B — Genuine adaptive assessment**, kept as the explicit alternative, with C noted as a viable but lower-priority follow-on.

---

## 18. Recommended P11

**P11 — Personalized Study Plans, Learning Goals & Adaptive Learning Paths** (see `P11_SCOPE_AND_FOUNDATION.md`).

It reuses the deterministic intelligence stack (mastery, recommendations, review scheduling, learner progress) and the vanilla frontend to give each learner a dated, actionable daily plan generated from their live state — with goals and an adaptive learning path. No rewrite, no new tables (reuse 0011), no new AI provider, deterministic, additive, and fully testable in the browser.

---

## 19. Explicitly Rejected for P11

- **AG-1 React/Next.js/framework migration** — vanilla SPA is fine; no product-critical reason found. Rejected.
- **AG-2 2D lesson/content editor** — large new subsystem; product gap is structure (plans), not authoring. Rejected.
- **AG-3 Microservices / vector-DB / pgvector migration** — no scale evidence; RAG works. Rejected.
- **AG-4 ML/DL learner model** — violates the architectural mandate; deterministic is correct at this maturity. Rejected.
- **AG-5 Autonomous agents / unrestricted AI chat** — deliberate bounds preserved. Rejected.
- **AG-6 Multi-tenancy / enterprise SSO / teacher platform** — no role model; different product. Rejected.
- **AG-7 Social collaboration** — no architecture, low leverage. Rejected.
- **AG-8 Mobile app** — vanilla SPA responsive pass only. Rejected.
- **AG-9 New AI providers** — no architectural need. Rejected.
- **AG-10 Large-scale infrastructure rewrite** — out of scope at 1–10K user scale. Rejected.
- **AG-11 Unrelated historical mypy debt** — held flat by zero-new policy; does not block P11. Rejected.
- **AG-12 Genuine adaptive assessment as P11** — deferred to a later phase (it is P11's #1 alternative, but touching the attempt path now is higher risk and lower leverage than wiring the always-present 0011 tables). Ranked #2.

---

## 20. Risks (P11)

| Risk | Mitigation |
|---|---|
| Plans/goals become disconnected dashboard furniture | Anchor plan items to live state (due reviews, weak/developing concepts, unfinished lessons) with deep-links to existing player/tutor/review actions; completing an item calls existing review/mastery flows |
| Scope creep into analytics/insights/adaptive assessment | Bound MVP (P11 scope §7 below); explicitly exclude |
| Session semantics drift of existing review queue | P11 is additive over `review_schedules`; never rewrite P10 behaviour |
| mypy floor | Zero-new policy; P11 files typed to match |
| "Today's plan" generation cost on hot path | Deterministic, bounded read-composition (reuse `learner_progress_service` query shapes); cache plan outline per user |

---

## 21. Final Architectural Decision

Proceed to **P11: Personalized Study Plans, Learning Goals & Adaptive Learning Paths**. Rationale (evidence): P10 closed NG-1/2/3 and made the loop time-aware and actionable; the last explicitly-deferred gap (NG-5) is the **structure layer** connecting the now-working subsystems into a dated daily program, and the entirety of its data foundation (0011 tables, `shared/constants` enums, `personalization.py` schemas, live `review_schedules`) already exists. It is the highest-value, highest-leverage, most feasible, and lowest-risk next step.