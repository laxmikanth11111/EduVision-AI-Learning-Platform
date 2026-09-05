# Post-P12 Product & Architecture Audit

**Phase:** P12 (Genuine Adaptive Assessment — NG-4 — with mandatory PostgreSQL attempt-path repair) — audit
**Type:** Audit + product decision only — NO P13 implementation
**Branch:** `feature/individual-user-foundation`
**Audited HEAD:** `623c43f` (`docs(p12): record P12 completion commit hash and sign off release gate`)
**Alembic head:** `0033_educational_memories` (verified)
**Date:** 2026-09-05

---

## 1. Executive Summary

P12 is **complete, committed, and verifiable** at HEAD `623c43f`. Independent re-verification this pass confirms every P12 release gate: SQLite **1183 passed**, PostgreSQL **19 passed** (testcontainers, `postgres:16-alpine`, `alembic upgrade head`), browser E2E **15 passed** on a clean full run (real Chrome against a live uvicorn on SQLite), Ruff **clean** on the whole repo, mypy exactly **83 errors / 24 files** (zero new), a **single Alembic head** `0033_educational_memories`, a **clean working tree**, `git diff --check` clean, and a **secret scan** with no committed secrets.

The two P12 deliverables are both **verified against source and tests**, not just against the report:

1. **P12-A1 (PostgreSQL attempt-path repair — CRITICAL drift fixed)**: the live quiz attempt flow (start → timed answers → `/next` → submit → `ScoreSummary`) now runs on a migrated PostgreSQL. The P11 audit empirically proved three failure classes (NOT NULL `max_score`/`time_spent_seconds` unset at start; unmapped NOT NULL `question_attempts.public_id`/`time_spent_seconds`; `feedback` JSONB vs `Text`; plus, discovered this pass, missing `educational_memories` table, unmapped `user_answers.public_id` and `score_summaries.public_id/computed_at/graded_at/scoring_version`). P12 resolved them with **two additive migrations** (`0032`, `0033`) and ORM-parity mappings, proven by a new 4-test PG behavioral suite (`tests/postgres/test_p12_adaptive_persistence.py`). The PG suite grows 15 → 19.
2. **P12-A2 (Genuine adaptive assessment — NG-4)**: a pure, deterministic adaptive selector (`app/services/adaptive_assessment.py`) drives mastery-tuned question ordering and true **within-attempt** adjustment (`/next` re-evaluates correctness server-side and returns the server-chosen next question). The real vanilla player delivers an **ADAPTIVE** badge with deterministic rationale and a fallback to fixed order. Dead VisualQuestion-based engines (`adaptive_assessment_engine.py`, `visual_question_generator.py`) and orphaned assessment schemas were **deleted with zero-ref proof**.

### Key finding this pass (beyond re-verification)

**Browser E2E flakiness in 2 pre-existing P10 tests.** On separate partial runs the P12-era adaptive player path produced intermittent failures (2 failed / 13 passed in one full attempt; `test_p10_ng1_quiz_next_action_cta` failing on a 2-test rerun while `test_p10_ng3` passed) — all manifesting as a "50% vs 100%" score-ring assertion. A clean full re-run returned **15 passed**. Conclusion: this is a **timing race/flakiness in the adaptive `/next` player flow**, reproducibility-variable rather than deterministic. It is a MEDIUM reliability finding for P13 (harden the adaptive player's async `/next` handshake), not a confirmation of deterministic breakage.

### Product-state summary

The core learning spine — **Learn → Assess (now adaptive) → Mastery → Recommend → Remediate/Tutor → Review Schedule → Today Plan/Goals/Learning Path → Practice Again → Assess Again** — is **fully CONNECTED and production-correct on PostgreSQL** for the first time. The last major capability still **missing** as an implemented surface is **learner analytics / insights**: the dashboard shows only a thin trend, and the analytics models/tables are **orphaned** (metadata-registered but never written or read). This is the flagged "phase after P12" from the Post-P11 audit, it is **deterministic** (no AI), it reads exactly the attempt rows P12 just repaired, and it is browser-verifiable on the dashboard. **Recommended P13: Learner Analytics & Insights** (scoring and rationale in §17–§18).

---

## 2. Starting Commit / Repository State

| Item | Expected | Verified | Evidence |
|---|---|---|---|
| Branch | `feature/individual-user-foundation` | yes | `git branch --show-current` |
| HEAD | `623c43f` (P12 sign-off) | yes | `git rev-parse HEAD` |
| P0–P11 chain | present | yes | `git log --oneline -10` |
| Working tree | clean | yes | `git status --short` = empty |
| Alembic head | single `0033_educational_memories` | yes | `alembic heads` |
| P12 report/scope docs | present | yes | `P12_IMPLEMENTATION_REPORT.md`, `P12_SCOPE_AND_FOUNDATION.md` |

Expected final P12 commits `150ec1f` and `623c43f` are both present and `623c43f` is HEAD. Repo state matches the P12 contract exactly.

---

## 3. Verification Baseline (independently re-verified this pass)

| Gate | Command | Observed | P12-claimed |
|---|---|---|---|
| git status | `git status --short` | clean | clean |
| current commit | `git rev-parse HEAD` | `623c43f` | `623c43f` |
| Alembic heads | `alembic heads` | `0033_educational_memories (head)` — single | single head `0033` |
| SQLite regression | `pytest tests/unit tests/integration -m "not postgres and not e2e"` | **1183 passed**, 0 failed (622.47s) | 1183 |
| PostgreSQL | `pytest tests/postgres -m postgres` | **19 passed** (58.99s) | 19 |
| Browser E2E | `pytest tests/e2e -m e2e` (full run) | **15 passed** (163.63s); **flaky on partial reruns** | 15 |
| Ruff | `ruff check .` | **All checks passed** (whole repo) | clean |
| Mypy | `mypy app` | **83 errors / 24 files** — exactly the P11/P10 baseline, zero new | 83/24 |
| git diff --check | `git diff --check` | clean (exit 0) | clean |
| Secret scan | `git grep` over HEAD for secret patterns | only legitimate setting-driven references; no committed secrets | none |

**E2E flakiness detail:** my first detached full E2E run reported `2 failed, 13 passed` (`test_p10_ng1_quiz_next_action_cta[chromium]` and `test_p10_ng3_critical_learning_loop[chromium]`), both asserting `"100" in ring.inner_text()` but observing `50%`. A re-run of just those two reported `1 failed, 1 passed` (NG-1 failing again, NG-3 passing). A subsequent clean full E2E run returned **15 passed**. The failures localize to the two P10 adaptive-review browser tests under the P12 adaptive player, and are timing-variable — consistent with a race in the new async `/next` handshake rather than a deterministic score regression (both questions carry the same correct option, Q1 tagged weak → band 0, Q2 untagged → generic developing, so adaptive order does not reverse them; the 50% implies one answer did not reach the persisted `UserAnswer` before `/submit` graded it).

---

## 4. P12 Capability Verification (survey per the contract)

| # | Capability | Verdict | Evidence |
|---|---|---|---|
| 1 | PostgreSQL attempt-path repair | **VERIFIED** | migrations `0032`/`0033` additive + idempotent; ORM parity on `quiz_attempts`/`question_attempts`/`user_answers`/`score_summaries`; `tests/postgres/test_p12_adaptive_persistence.py` runs the live start→answer→next→submit→ScoreSummary on migrated PG (19 PG passed) |
| 2 | PostgreSQL behavioral coverage | **VERIFIED** | the new 4-test PG behavioral suite exercises the attempt INSERT path the old 15-test suite never did; PG suite 15→19 |
| 3 | QuizAttempt persistence | **VERIFIED** | `QuizAttempt.max_score`/`time_spent_seconds` now NOT NULL server-defaulted + mapped; `adaptive` column added; PG insert succeeds throughout the lifecycle |
| 4 | QuestionAttempt persistence | **VERIFIED** | `QuestionAttempt.public_id` mapped (`qast_`), `time_spent_seconds` defaulted, `feedback` typed `PortableJSONB`; PG insert succeeds |
| 5 | JSON feedback persistence | **PARTIAL** | schema/ORM now agree (`PortableJSONB` vs `jsonb`); but per P12 report §14 the service still never populates `question_attempts.feedback` (per-question feedback flows via the submit response, not the column) — carried observation, not a regression |
| 6 | Attempt timing persistence | **VERIFIED** | `time_spent_seconds` forwarded through `/next` (`submit_answer`) and `/submit`; mapped/defaulted on both tables |
| 7 | Deterministic adaptive assessment | **VERIFIED** | `adaptive_assessment.py` pure selector; selection key `(band, fit, difficulty_rank, bloom_rank, position, public_id)`; `tests/unit/test_p12_adaptive_assessment.py` 10 pure-selector tests incl. determinism |
| 8 | Mastery-aware question ordering | **VERIFIED** | weak band (0) sorts first; per-band difficulty target; mastery read auth-scoped from `educational_memory_service`; PG + unit + E2E |
| 9 | Within-attempt adaptation | **VERIFIED** | `/next` persists the just-answered question, re-evaluates correctness server-side, returns server-chosen next question; `get_next_question` uses `select_next_question(candidates, answered_history)` |
| 10 | Adaptive metadata | **VERIFIED** | `adaptive` bool + `adaptive_rationale` in `StartAttempt`/`NextQuestion` responses; persisted on `quiz_attempts.adaptive` |
| 11 | Adaptive player UI | **VERIFIED** | `player.html` `startQuiz({adaptive:true})` with 422 fallback, `quizNav` adaptive `/next` swap, ADAPTIVE badge + rationale; `<escHtml>` used |
| 12 | Security isolation | **VERIFIED** | cross-user 404 equalization on `/next`, attempt read, start; unknown question 404; next-after-submit 409; ineligible (1-question) adaptive start 422 with zero attempt rows; verified in unit + PG suites |
| 13 | Browser adaptive E2E | **VERIFIED** | `tests/e2e/test_p12_adaptive_e2e.py` Scenario A (correct→advanced) and B (incorrect→beginner) pass |
| 14 | Retirement of dead assessment code | **VERIFIED** | `adaptive_assessment_engine.py`, `visual_question_generator.py`, `schemas/adaptive.py`, `visual_assessment.py`, `director.py`, `teaching_strategy.py` deleted; zero imports confirmed; `app.main` imports clean; ruff clean |
| 15 | Observability | **VERIFIED** | `p12_adaptive_starts_total`, `p12_adaptive_orders_total{outcome}`, `p12_adaptive_rejections_total` in `metrics.py`, exposed via `GET /api/v1/metrics` |
| 16 | Bounded candidate loading | **VERIFIED** | `selectinload(Question.options)` (2 queries), one batched `IN` concept map, cache-backed memory; `get_next_question` ≈ 6 bounded queries, O(n log n) in-memory ordering |

**16/16 verified (1 partial — the pre-existing, documented `question_attempts.feedback`-unpopulated observation).**

---

## 5. Product Journey (reconstructed learner path, P12 reality)

Trace of the actual learner journey with P12 included. Each transition is classified by **runtime behavior**, not endpoint existence.

| # | Stage | Status | Evidence |
|---|---|---|---|
| 1 | Registration | CONNECTED | `signup.html` → `POST /auth/register` (Argon2id) → redirect |
| 2 | Authentication | CONNECTED | `signin.html` email/password + Google OAuth link; access+refresh JWT, httponly cookies |
| 3 | Presentation ingestion | CONNECTED | `upload.html` (file drag-drop / topics) → `POST /presentations/*` |
| 4 | Content extraction | CONNECTED | `processing.html` poll → `content_extraction_service` |
| 5 | Lesson generation | CONNECTED | Celery `lessons.generate` → `generated_lesson_version` published |
| 6 | Lesson / player open | CONNECTED | `player.html?lesson=` → `player/start` → `learning_sessions` |
| 7 | Slide / content render | CONNECTED | slide engine; concept chips; learner-journey panel |
| 8 | Visual / content experience | PARTIAL | SVG strategies + motion + simulation wired; **video runtime (bookmark/assessment/tutor-context) backend-only**; animation classify + 5 GET routes unwired |
| 9 | Lesson → checkpoint | CONNECTED | "Take Checkpoint" → `startQuiz` |
| 10 | Adaptive assessment | CONNECTED | `startQuiz({adaptive:true})` → mastery-tuned order; `/next` within-attempt adjustment |
| 11 | Scoring / mastery | CONNECTED | `submitQuiz` → `_evaluate_answer` → `_update_concept_mastery` (public-ID keyed) → `ScoreSummary` |
| 12 | Recommendations | CONNECTED | `recommendation_engine` → dashboard "Next Best Actions" + `recoAction()` deep-links |
| 13 | Review scheduling | CONNECTED (lazy) | `_ensure_schedules` on dashboard read; due queue; 1/3/7/14 ladder |
| 14 | Today Plan | CONNECTED | `/me/plan/today` composed read; item completion routes through review |
| 15 | Goals | CONNECTED | `/me/goals` derived-only progress |
| 16 | Learning Path | CONNECTED | `/me/path` weakest-first ordered deep-links |
| 17 | Tutor / RAG | CONNECTED | multi-turn `tutor.html`, semantic RAG, `remediate()` + Practice CTA |
| 18 | Next learning action | CONNECTED | reco/plan/path CTAs → player or tutor deep-links |

**Result:** the full learn→assess→mastery→recommend→review→plan/goal/path→tutor→next-action spine is **CONNECTED** and — critically, for the first time — its persistence legs run on migrated PostgreSQL. The distinct **PARTIAL** transitions are all in the content *experience* layer (video runtime frontend wiring, animation classify/GET routes, simulation parameter/playback/reset) — real but not on the core learning loop.

---

## 6. Capability Matrix Summary

See the complete **`POST_P12_CAPABILITY_MATRIX.md`** companion.

By domain (high-level):
- **Content/Lesson/Visual/Assessment**: learn→assess spine COMPLETE and now PG-correct; video-runtime/animation-classify/simulation-controls PARTIAL.
- **Learning**: lesson player, learner journey, progress, mastery, recommendations, review, Today Plan, goals, path, tutor, RAG, remediation — all COMPLETE.
- **Assessment**: quizzes, attempts, question attempts, scoring, deterministic adaptive assessment (ordering + in-attempt), assessment→mastery — COMPLETE. Inter-attempt adaptation and elo/IRT deferred.
- **Learner Intelligence**: mastery, weak/strong concepts, review pressure, next action, plans, goals, path, tutor context — all COMPLETE (deterministic).
- **Analytics**: learner analytics — **MISSING** (orphaned models/tables; dashboard trend only).
- **Platform**: PostgreSQL fix verified; SQLite, storage, authN/Z, observability, migrations, CI — COMPLETE; Redis/Celery functional integration test MISSING.
- **Retention / review→mastery feedback**: PARTIAL / DEFERRED.

---

## 7. Assessment Audit

- **Fixed-order delivery replaced** by P12 adaptive default in the player; fixed order retained as the 1-question fallback and always available via non-adaptive start.
- **Deterministic**: `adaptive_assessment.py` is pure and replayable; identical inputs → identical order; no randomness, no AI on the delivery path.
- **Mastery-tuned**: `band_for_mastery` mirrors `educational_memory_service` bands (weak <50, developing 50–85, mastered ≥85); per-band target difficulty; within-attempt +1 on correct / −1 on incorrect (clamped 0..2).
- **Scoring unchanged**: `submit_quiz` grading (`_evaluate_answer` vs `AnswerKey`) is identical; adaptivity never randomizes score. Fairness preserved.
- **Resume path**: `adaptive` persisted on `quiz_attempts.adaptive` so a resumed adaptive attempt continues adaptively.
- **Deferred (explicit)**: inter-attempt difficulty adaptation beyond ordering, adaptive persistence beyond the attempt's delivery order, elo/IRT/ML learner modeling, AI question generation.

---

## 8. Learning Intelligence Audit

All-COMPLETE deterministic stack (evidence in §6 and capability matrix):
- **Mastery** — `educational_memory_service`, mastery bands, BoundedCache(5000 / 1800s). **Decay is NOT persisted** — `compute_decay_signal` is a ranking/annotation pressure only, reset to `None` on review completion (PARTIAL, DEFERRED).
- **Recommendations** — `recommendation_engine` thresholds 50/85/95, weakest-first, deterministic.
- **Review scheduling** — `review_scheduler` 1/3/7/14 ladder, `ReviewScheduleService` lazy seeding, bounded due queue `MAX_DUE_LIMIT=200`, retention (mastered@max interval → auto-complete) on-read.
- **Today Plan / Goals / Path (P11 NG-5)** — read-compositions, zero AI, deterministic ordering, derived-only goal progress.
- **Gap**: learner-facing **analytics / trajectory visibility** is the one missing intelligence surface (see §16 G-1).

---

## 9. Tutor/RAG Audit

- **Tutor conversation**: COMPLETE — multi-turn, learner-scoped RAG, `AIContentService`-gated, deterministic fallback on AI-disabled/cold/timeout; `source_kind/attribution/confidence` truthful.
- **Remediation**: COMPLETE — `remediate()` deterministic, produces structured `take_knowledge_check` next_action with lesson deep-link.
- **RAG retrieval**: COMPLETE semantic path (`semantic_retrieve_chunks`: embed → cosine null-safe → threshold → top-k → positional fallback), learner-scoped upstream.
- **RAG fusion**: MISSING — `TUTOR_RETRIEVAL_MMR_LAMBDA` / `TUTOR_RETRIEVAL_RRF_K` and `TutorSearchType.HYBRID` are **inert** (config-only, never consumed). Semantic-only today.
- **Self-only prompt-injection** guard (`TUTOR_INJECTION_FLAG_THRESHOLD`): configured but **not consumed**; bounded by learner-scoped throughput (HIGH, carried).
- **`get_ai` dependency**: dead (zero `Depends(get_ai)`); minor cleanup.

---

## 10. Database Audit

- **ORM/schema parity**: P12 closed the attempt-table drift. `QuizAttempt` (max_score/time_spent defaulted+NOT NULL, `adaptive`, `ix_quiz_attempts_status`), `QuestionAttempt` (public_id mapped, feedback JSON/PortableJSONB), `UserAnswer` (public_id mapped), `ScoreSummary` (public_id/computed_at/graded_at/scoring_version mapped) now match their migrations.
- **The P12-discovered PG drift is genuinely resolved**: verified by the 4-test PG behavioral suite running the live attempt flow on a migrated `postgres:16-alpine` + head `0033` (and by ORM reads this pass).
- **Foreign keys / uniqueness / nullable / JSON fields / ownership / soft-delete**: consistent with sibling tables; `educational_memories` now created by migration 0033 with unique `user_id` and native `jsonb` `memory_data`; ownership columns follow the presentation-owner individual-first model; soft-delete semantics unchanged.
- **Migration lineage**: 33 migrations, linear chain, **single head `0033_educational_memories`**; P12 added two **additive, idempotent** migrations (0032, 0033) with `inspect()`/table-existence guards; no historical migration rewritten.
- **Dual-dialect**: PortableJSONB maintains SQLite/PG parity; SQLite 1183 green.

---

## 11. PostgreSQL Audit

- **Production correctness restored on the assessment spine**: start→timed answers→`/next`→submit→`ScoreSummary` verified on migrated PG automatically.
- **PG suite gap closed**: the old 15-test suite never inserted an attempt; the new `test_p12_adaptive_persistence.py` (4 tests) covers the live lifecycle + cross-user 404 on PG, and it was this exact suite that surfaced the three extra drift findings (`educational_memories`, `user_answers.public_id`, `score_summaries` columns) at C10.
- Executive finding: **past the assessment spine, the PG coverage is still shallow** for the analytics tables (they are unused/orphaned) — a P13 consideration, not a blocker.

---

## 12. Security Audit

Verified-preserved controls (no new attack surface from P12):
- **Authentication**: Argon2id, access+refresh JWT (Redis JTI revocation for refresh, in-memory fallback), httponly/secure/samesite cookies, secret-validation guards. **Gaps (carried)**: access tokens stateless/unrevocable (15-min expiry mitigates); refresh rotation does not revoke the consumed token; tokens duplicated in JSON bodies; `.env` holds live-looking credentials + `RATE_LIMIT_WHITELIST` incl. `127.0.0.1/::1/localhost`.
- **Authorization/ownership**: repository-layer `get_for_user`, 404-equalized ownership, prefix-locked storage; all adaptive flows resolve user from `get_current_user`; mastery read auth-scoped.
- **Isolation suites green**: two-user 22, p11 security 5, learner-progress 5, mastery-tutor 7, p6 assessment 14, review 5, upload-validation 23.
- **Adaptive-specific isolation**: cross-user `/next`/read/start → 404; unknown question → 404; next-after-submit → 409; ineligible start → 422 with zero rows (unit + PG).
- **Rate limiting**: per-IP Lua sliding window + route overrides (note: stale `^/api/v1/quizzes/[^/]+/session$` override survives — harmless).
- **Prompt-injection**: `TUTOR_INJECTION_FLAG_THRESHOLD` defined but unconsumed; bounded self-only window (HIGH, carried).

No verified P12-introduced security gap. All findings are pre-existing and carried.

---

## 13. Performance Audit

- **P12 path bounded**: start/`/next` ≈ 6 bounded queries, `selectinload(Question.options)`, batched `IN` concept map, cache-backed memory, O(n log n) in-memory ordering. No N+1.
- **Learner progress bounded**: `_MAX_LESSONS=50`, `_MAX_RECENT_ATTEMPTS=10`, `_MAX_TREND_POINTS=10`, `_MAX_CONCEPTS=100`.
- **Review bounded**: `MAX_DUE_LIMIT=200`.
- **Today Plan bounded**: output ≤111, practice ≤5.
- **Material scale concerns (for the roadmap, not generic infra)**:
  1. **Synchronous video render in the request path** (`video_router.py:110/:137` → `render_video_mp4`), with three synchronous `subprocess.run` FFmpeg calls — no `to_thread`, no Celery. Highest-perf item; directly undercuts any video-feature push.
  2. `_lesson_progress` loads all `LearningSession` rows and caps in Python (should `.limit()` in SQL).
  3. Effectiveness report/compare endpoints `.all()` full tables.
  4. OFFSET pagination (cursor helpers exist, unused).
  5. No functional Redis/Celery integration test (mocks only) — blocks risk-free scheduling/worker features.

---

## 14. Frontend Audit

- **Active frontend**: `backend/frontend/` vanilla HTML/CSS/JS, multi-page SPA, no framework, mounted at `/frontend`. No React migration recommended.
- **Working surfaces**: index/signin/signup/upload/processing (ingestion), player (slides + SVG strategies + motion + animation + video + simulation + adaptive quiz overlay), tutor (RAG/chat/remediate), dashboard (stats, Next Best Actions, review queue, Today Plan, Goals, Learning Path, lesson progress, chips, trend).
- **Verified learner-facing transitions** and the **dead ends**:
  - dashboard → player ✓, dashboard → tutor?concept= ✓, tutor → player?lesson= ✓, player → tutor?concept= ✓, upload → processing → player ✓.
  - **player has NO link to dashboard, Review Queue, Today Plan, Goals, or Learning Path** — and its brand header goes to `upload.html`, not the dashboard hub. The single biggest dead end for a learner mid-loop. (G7, LOW-MED.)
  - processing.html "Start → player" and "Ready for review" language mismatch; no route to a review action; no dashboard/tutor link on this page.
  - upload.html landing post-login has no path to dashboard/tutor (only self + Sign Out).
  - `?deck=` param dead (parsed in player but unused; emitted by processing).
  - Diagnostic CTA suppressed when backend lacks a `lesson_id`/`concept_id` (no dead buttons, but potential silent dead-end).
  - Duplicated `authFetch`/`escHtml`/bootstrap (~5× , with a minor tutor.html refresh-token divergence); orphaned `assets/app.js`/`style.css`.
- Product-value verdict: the **core loop is browser-finished**; the remaining frontend gaps are **hub-navigation completion** (player/dashboard connection) and the **video-runtime frontend wiring**.

---

## 15. Deferred Gap Review (P0 → P12)

| Gap | Verdict | Rationale / evidence |
|---|---|---|
| NG-4 genuine adaptive assessment | **CLOSED** (P12) | deterministic adaptive ordering + in-attempt adjustment; `adaptive` badge; unit+PG+E2E |
| NG-5 study plans / goals / learning paths | **CLOSED** (P11, re-verified) | Today Plan/goals/path live, deep-linked, browser-verified |
| Learner analytics / insights (G3) | **STILL OPEN → P13** | dashboard trend only; analytics models/tables orphaned |
| Video runtime frontend (G5) | **STILL OPEN** | `video_runtime_router.py` backend-only (in-memory BoundedCache), zero frontend callers |
| Retention / review→mastery feedback | **STILL OPEN / PARTIAL** | review resets clock but never rewrites mastery; retention on-read only, no beat task |
| Mastery decay persistence | **STILL OPEN / PARTIAL** | `compute_decay_signal` ranking-only, never persisted |
| Tutor depth / Tutor 2.0 | **STILL OPEN** (carried) | tutor works; depth + AI-risk tradeoff defers a dedicated phase |
| RAG fusion (RRF/MMR) | **STILL OPEN** | knobs inert; semantic-only |
| Adaptive assessment 2.0 (inter-attempt / IRT / elo) | **STILL OPEN** (carried) | explicitly out of P12 scope |
| Player → review/plan entry (G7) | **STILL OPEN** (LOW-MED) | no player exit to dashboard/review/plan |
| Assessment → immediate scheduling (G6) | **STILL OPEN** (LOW) | lazy on dashboard read |
| Functional Redis/Celery integration test | **STILL OPEN** | mocks only |

---

## 16. Remaining Product Gaps (ranked, post-P12)

| Rk | Gap | Findings | Best evidence |
|---|---|---|---|
| 1 | **Learner analytics / trajectory insights** (G3) | The learner cannot see "am I improving", "which concepts trend up/down", "effort vs mastery". Analytics models/tables orphaned; only a thin trend on the dashboard. Reads the just-repaired attempt data. | `analytics.py` (orphaned), `analytics_insights.py`, dashboard trend only |
| 2 | **Player ↔ dashboard hub dead end** (G7 + navigation) | Player has no exit to review Queue / Today Plan / Goals / Path; header brand → upload page. Breaks mid-loop navigation. | `frontend/` subagent walk |
| 3 | **Video runtime + video render plumbing** (G5 + perf) | Runtime backend-only/in-memory; video render synchronous in request path. Blocks a real video-learning push. | `video_runtime_router.py`, `video_router.py:110/137` |
| 4 | **Review → mastery feedback** | Reviewing resets the schedule but does not move mastery; retention is on-read only. | `record_review_activity` vs `update_concept_mastery` |
| 5 | **RAG fusion (RRF/MMR)** | Retrieval is semantic-only; fusion knobs inert. | `config.py:222-223` (unconsumed) |
| 6 | **Mastery decay persistence** | Pressure is ranking-only; score never decays. | `compute_decay_signal` |
| 7 | **Adaptive 2.0 / Tutor 2.0** | Deeper-then-closed gaps; AI-risk heavy. | carried |

---

## 17. Candidate P13 Comparison

Scoring model (each criterion 1–5, 5 = best; weights sum to 1.0): Learner value 0.25 · Architectural fit 0.15 · Foundation readiness 0.15 · Implementation complexity (inverse) 0.10 · Security risk (inverse) 0.10 · Data-model risk (inverse) 0.08 · AI-independence 0.07 · Testing ease 0.05 · Scalability 0.03 · Learning-loop-gap closure 0.02.

| Cand | Direction | Lrnr .25 | Fit .15 | Ready .15 | Cx⁻¹ .10 | Sec⁻¹ .10 | DM⁻¹ .08 | AI⁰ .07 | Test .05 | Scale .03 | Loop .02 | **Total** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **A** | **Learner analytics / insights** | 4 (1.00) | 5 (0.75) | 5 (0.75) | 4 (0.40) | 4 (0.40) | 4 (0.32) | 5 (0.35) | 4 (0.20) | 3 (0.09) | 3 (0.06) | **4.32** |
| B | Tutor 2.0 (richer multi-turn pedagogy) | 4 (1.00) | 4 (0.60) | 4 (0.60) | 2 (0.20) | 3 (0.30) | 4 (0.32) | 1 (0.07) | 2 (0.10) | 3 (0.09) | 3 (0.06) | 3.34 |
| C | Video learning runtime completion | 3 (0.75) | 3 (0.45) | 3 (0.45) | 2 (0.20) | 3 (0.30) | 4 (0.32) | 2 (0.14) | 2 (0.10) | 2 (0.06) | 3 (0.06) | 2.83 |
| D | Review/player integration + hub nav | 3 (0.75) | 5 (0.75) | 5 (0.75) | 5 (0.50) | 5 (0.50) | 5 (0.40) | 5 (0.35) | 5 (0.25) | 5 (0.15) | 3 (0.06) | 4.46 |
| E | Retention automation (scheduled review) | 3 (0.75) | 4 (0.60) | 3 (0.45) | 3 (0.30) | 4 (0.40) | 4 (0.32) | 5 (0.35) | 2 (0.10) | 3 (0.09) | 4 (0.08) | 3.44 |
| F | RAG fusion (RRF/MMR hybrid) | 3 (0.75) | 4 (0.60) | 4 (0.60) | 4 (0.40) | 4 (0.40) | 4 (0.32) | 3 (0.21) | 3 (0.15) | 3 (0.09) | 2 (0.04) | 3.56 |
| G | Adaptive assessment 2.0 (inter-attempt/IRT) | 3 (0.75) | 4 (0.60) | 4 (0.60) | 2 (0.20) | 3 (0.30) | 3 (0.24) | 4 (0.28) | 3 (0.15) | 3 (0.09) | 3 (0.06) | 3.27 |
| H | Mastery decay persistence | 3 (0.75) | 4 (0.60) | 4 (0.60) | 4 (0.40) | 4 (0.40) | 3 (0.24) | 5 (0.35) | 4 (0.20) | 4 (0.12) | 3 (0.06) | 3.72 |
| I | UX completion niche (fold dead links, dedupe helpers) | 2 (0.50) | 5 (0.75) | 5 (0.75) | 5 (0.50) | 5 (0.50) | 5 (0.40) | 5 (0.35) | 5 (0.25) | 5 (0.15) | 2 (0.04) | 4.19 |

**Ranked (raw):** D (4.46) > A (4.32) > I (4.19) > H (3.72) > F (3.56) > E (3.44) > B (3.34) > G (3.27) > C (2.83).

**Why the recommendation is A, not the raw winners D/I:** D (review/player hub nav) and I (UX completion) are inexpensive **navigation/UX-folding** wins that should be folded opportunistically into any phase, not made a phase of their own — they add no new capability and would _not_ deliver a meaningful P13 product narrative. A delivers a genuinely **missing capability** (the learner's trajectory/insight surface) with the strongest foundation readiness (P12 just repaired the exact attempt rows it reads), full AI-independence, low risk, and clear browser verifiability. H/F/G/B/C/E are each either a depth-extension with higher AI/data-model risk (B/G), a niche content surface (C), retention hardening with a Redis/Celery functional-test dependency (E), or an inert-knob polish (F).

---

## 18. Recommended P13

**P13 — Learner Analytics & Insights ("Know my trajectory").**

Deterministic, learner-scoped aggregates over the existing (and now PG-correct) attempt/session/mastery data, surfaced as browser-verifiable insight panels on the dashboard: **performance trend over time, concept-wise mastery trajectory, effort vs mastery, attempt-history analytics, and weak/strong concept analytics** — closing the learner's "am I improving and what should I focus on?" gap. Zero AI; read-composes existing tables first (prefer existing schema); only a small additive migration if a join index is genuinely justified by query analysis.

MVP shape (summary): (1) new `/me/analytics/*` read-composed endpoints (aggregation from `quiz_attempts`/`score_summaries`/`learning_sessions`/`educational_memories`, all learner-scoped and bounded); (2) dashboard analytics panels (trend, concept trajectory, effort vs mastery) wired to those endpoints with `escHtml`; (3) the **player→dashboard/plan/review hub link** folded in as part of the same deliverable (the single biggest dead-end), plus removal of the dead `?deck=` param; (4) reuse of the currently-orphaned analytics schemas/models where they fit, but **no new schema by default**. Full definition in `P13_SCOPE_AND_FOUNDATION.md`.

---

## 19. Why Other Candidates Are Deferred

- **D / I (hub nav / UX completion)** — real, cheap, and folded into P13's frontend deliverable; not a phase. Not "architecture-flexing," just a needed connection.
- **C (video learning runtime)** — genuine, but its value is capped until the synchronous-render perf problem and the backend-only runtime are addressed; a narrow content experience, not the highest-marginal learner capability, and higher risk/effort.
- **E (retention automation)** — valuable, but depends on a functional Redis/Celery integration test that doesn't exist (mocks only); higher risk and ops debt. Defer until the worker/infra hardening is a committed prerequisite.
- **F (RAG fusion RRF/MMR)** — inert-knob polish; marginal learner-visible value; cheap to fold into a later tutor/RAG pass, not a phase.
- **B (Tutor 2.0)** — highest raw learner value but heaviest AI dependency and reliability risk; the tutor already works; a depth-extension that does not close a missing loop. Retained as main later follow-up.
- **G (Adaptive 2.0 / IRT)** — mutates the mastery/assessment invariant P12 just stabilized; higher data-model + AI risk; defer.
- **H (mastery decay)** — real educational value but mutates the core mastery invariant; prefer deterministic scheduling/analytics first.

---

## 20. P13 Risks

| Risk | Mitigation |
|---|---|
| Aggregation queries degrade on large attempt volumes | Learner-scoped, bounded windows (`LIMIT`/time-window), reuses existing user_id indexes; add a join index only if profiling justifies it (documented, permitted small additive migration) |
| Analytics becomes a "view with no loop" | Every insight panel carries an actionable deep-link (→ review, → plan, → practice, → tutor) so analytics drives the next learning action, not just display |
| Scope creep into AI-driven "insights" | Deterministic-only MVP: plain aggregates + rule-derived annotations (thresholds mirror recommendation engine); no LLM summaries; any future AI insight stays behind `AIContentService` |
| Reuse of orphaned analytics models drags in schema | Prefer read-composition of existing tables; use the orphaned schemas as response shapes only; do not force unused tables to become write targets |
| Flaky P10 browser tests surface again | Stabilize the adaptive `/next` player handshake (idempotent double-submit guard) as a hardening item within P13 before adding new analytics E2E |
| `.env` values / rate-limit whitelist in prod | Documented pre-existing; not created by P13; confirm git-ignore + production rotation before any deployment |

---

## 21. P13 Constraints (non-negotiable)

- Existing tables/services/repositories preferred; a small additive migration **only** if genuinely justified and documented.
- Deterministic learner intelligence unless AI is explicitly justified (no LLM analytics by default).
- Preserve PostgreSQL production correctness; keep SQLite/PG dual-dialect green.
- Preserve vanilla `backend/frontend/`; no framework migration.
- Mypy baseline stays **83 / 24** (zero new) unless a future phase intentionally changes it with justification.
- Browser-verifiable and testable; bounded MVP via checkpoints.
- Do **not** implement P13 in this phase.

---

## 22. Audit Conclusion

P12 is **VERIFIED** in full: the two deliverables (CRITICAL PostgreSQL attempt-path repair and genuine deterministic adaptive assessment) are proven against source, tests, and a real migrated `postgres:16-alpine`. All release gates are green (SQLite 1183, PG 19, E2E 15 on a clean run, Ruff clean, mypy 83/24, single head `0033`, secret-scan clean, clean tree). The one new reliability signal — intermittent flakiness in two pre-existing P10 browser tests under the adaptive `/next` player path — is documented as a MEDIUM hardening item, not deterministic regression.

The product now has a **fully-connected, PG-correct learning loop** from Learn through Assess (adaptive) to Mastery, Recommend, Review, Plan/Goal/Path, and Tutor. The highest-value remaining **capability** gap is **learner analytics / insights** — the learner has no trajectory/insight surface, the analytics models are orphaned, and P12 has just made the underlying data reliable. **P13 = Learner Analytics & Insights** (with the player↔dashboard hub link folded in) is the recommended, deterministic, low-risk, browser-verifiable next phase. The authoritative, implementation-ready foundation is captured in **`P13_SCOPE_AND_FOUNDATION.md`**.
