# Post-P13 Product & Architecture Audit

**Phase:** P13 (Learner Analytics & Insights — "Know my trajectory") — audit
**Type:** Audit + product decision only — NO P14 implementation
**Branch:** `feature/individual-user-foundation`
**Audited HEAD:** `c191d44` (`feat(p13): add learner analytics and insights`)
**Alembic head:** `0033_educational_memories` (single, verified)
**Date:** 2026-09-05

---

## 1. Executive Summary

P13 is **complete, committed, and clean** at HEAD `c191d44`. Independent re-verification this pass confirms every P13 release gate from live output: SQLite unit+integration **1213 passed**, PostgreSQL **25 passed** (testcontainers, `postgres:16-alpine`, head `0033`), browser E2E **18 passed** on the full suite, Ruff **clean on the whole repo**, mypy exactly **83 errors / 24 files** (the P12 authoritative baseline — zero new), a **single Alembic head `0033_educational_memories`** (no migration added by P13), a **clean working tree**, `git diff --check` clean, and a secret scan with **no real secrets** (only the deterministic E2E fixture passwords, matching the P12 baseline pattern).

P13 delivered what its scope contract promised, verified against source and tests:
1. **P13-A1** — four learner-scoped `/me/analytics/*` endpoints (overview, trend, concepts, effort) as deterministic read-compositions over `quiz_attempts` / `score_summaries` / `learning_sessions` / `educational_memories`, with `analytics.py:76` window validation (clamped 1–30), bounded result sets, and server-built deep-links (overview + `/overview` alias, trend, concepts with practice+tutor links, effort).
2. **P13-A2** — three dashboard analytics panels (trajectory, concepts-at-a-glance, effort-vs-mastery), all `escHtml`-escaped, browser-verified (`tests/e2e/test_p13_analytics_e2e.py`, 3 tests).
3. **P13-A3** — player → dashboard hub link (closing the biggest remaining dead-end, G7) and `?deck=` dead-param removal in `processing.html`; confirmed `player.html` no longer consumes `?deck=` (frontend audit) and `dashboard.html` is the hub.
4. **P13-A4** — the pre-existing P10 adaptive-`/next` browser flake was **root-caused and closed with evidence** (detailed in §14 and report §5a): a test-side stale-DOM click race, reproduced against the P12 baseline via `git stash`, fixed with a **test-only** `_wait_for_question(stem)` synchronized click. The full browser suite is now **stable** (18 passed, including P10 NG-1/NG-2/NG-3).

### Product-state summary

The fully-connected learning spine — **Learn → Visualize → Practice → Assess (adaptive) → Mastery → Measure (P13) → Remediate/Tutor → Review → Adapt → Next Action** — is now **COMPLETE and learner-visible end to end** for the first time. The three questions P13 set out to answer ("am I improving?", "where am I stuck?", "is my effort paying off?") are answerable on the dashboard.

**The single most important remaining broken transition (evidence-backed, the largest remaining product gap) is in the RETENTION/REVIEW leg:** completing a review captures **no recall outcome** and produces **no behavioral adaptation** — `ReviewScheduleService.complete` (`review_schedule_service.py:113-183`) resets the review clock and advances a pure time ladder (1/3/7/14) regardless of whether the learner actually remembered the concept: *"The routine does not change mastery; it resets the review clock on the learner's educational memory"* (L122-123), *"Reset the review clock in educational memory (no mastery rewrite)"* (L167). Failure never shortens the interval, success never strengthens the signal, decay pressure is **computed pure but never persisted** (`compute_decay_signal`, `review_scheduler.py:82-115`), and no background beat task exists for retention (`celery_app.py:69-106` schedules only health-check / presentation analytics / cleanups / embedding maintenance). The learner therefore **cannot see whether they are retaining what they learned** — and the review leg of the loop does not adapt to the learner at all. This is the evidence-based target for **P14**.

---

## 2. Starting Commit / Repository State

| Item | Expected | Verified | Evidence |
|---|---|---|---|
| Branch | `feature/individual-user-foundation` | yes | `git branch --show-current` |
| HEAD | `c191d44` (P13 completion) | yes | `git rev-parse HEAD` |
| Working tree | clean (post-commit) | yes | `git status --short` = empty |
| Alembic head | single `0033_educational_memories` | yes | `alembic heads` |
| P13 report/scope docs | present | yes | `P13_IMPLEMENTATION_REPORT.md`, `P13_SCOPE_AND_FOUNDATION.md` |
| Migration count | unchanged by P13 (0033 single) | yes | 33-revision linear chain, single head |

---

## 3. Verification Baseline (independently re-verified this pass)

| Gate | Command | Observed |
|---|---|---|
| git status | `git status --short` | clean |
| current commit | `git rev-parse HEAD` | `c191d44` |
| Alembic heads | `alembic heads` | `0033_educational_memories (head)` — single |
| SQLite regression | `pytest -q tests/unit tests/integration -m "not postgres and not e2e" ` | **1213 passed**, 0 failed |
| PostgreSQL | `pytest -q tests -m postgres` | **25 passed** |
| Browser E2E | `pytest -m e2e -q` (full suite) | **18 passed, 0 failed** (stable across multiple runs) |
| Ruff | `ruff check .` | **All checks passed** (whole repo) |
| Mypy | `mypy app` | **83 errors / 24 files** (checked 304 source files) — exactly the P12 baseline, zero new |
| git diff --check | `git diff --check` | clean (exit 0) |
| Secret scan | `Select-String` over P13 new/changed files | 0 real secrets; only deterministic E2E fixture credentials (`P13Loop1234!`/`P10Loop1234!` = the `P12Loop1234!` pattern) |

**E2E stability note (regression resolved):** the P12-era flake (`test_p10_ng1`/`test_p10_ng3` asserting `"100" in ring.inner_text()`, observing 50%) did **not** reappear. Root cause was established factually in P13 (see §14) and the fix is test-only. This pass's full-suite run: **18 passed, 0 failed**.

---

## 4. P13 Capability Verification (survey per the P13 scope contract)

| # | P13 contract item | Verdict | Evidence |
|---|---|---|---|
| 1 | `/me/analytics/overview` (+ `/overview` alias) | **VERIFIED** | `app/api/v1/analytics.py`; integration test asserts 3 seed attempts, avg 65.0, +37.5 trend, focus deep-link, metrics counter |
| 2 | `/me/analytics/trend?window=` bounded ≤30 | **VERIFIED** | schema `ge=1, le=30`; service clamp; test `window=31` → 422; chronological ordering |
| 3 | `/me/analytics/concepts` band+arrow+deep-links | **VERIFIED** | weak/developing/mastered bands; up/flat/down from memory categorical trend; practice + tutor server-built links; ≤100 rows |
| 4 | `/me/analytics/effort` attempts/sessions/time vs mastery | **VERIFIED** | 240/255/270s seed → 765s total; `+delta` and efficiency; ≤100 rows |
| 5 | Learner-scoped + 401 unauthenticated | **VERIFIED** | unauth → 401 on all four; user B → genuinely empty payloads (never A's rows); no client user_id anywhere |
| 6 | Empty-state contract | **VERIFIED** | `test_p13_analytics_e2e.py` empty-state journey ("No checkpoints yet" / "No concepts tracked yet") |
| 7 | Dashboard panels, escaped, deep-linked | **VERIFIED** | dashboard.html trajectory/concepts/effort panels; `escHtml`; e2e asserts real `player.html?lesson=` / `tutor.html?concept=` links |
| 8 | Player → dashboard hub link | **VERIFIED** | player.html header nav-link → `/frontend/dashboard.html`; e2e `test_p13_player_dashboard_hub_link` |
| 9 | `?deck=` removal | **VERIFIED** | processing.html starts player with `?lesson=` only; player.html has no `deck` consumption (frontend audit) |
| 10 | Zero migrations, single head | **VERIFIED** | `alembic heads` single `0033`; `test_p13_no_new_migration_head_unchanged` in PG suite |
| 11 | Observability `p13_*` | **VERIFIED** | `p13_analytics_views_total{endpoint,outcome}` + `p13_analytics_errors_total{endpoint,reason}` registered; metrics test green |
| 12 | Deterministic (no AI) | **VERIFIED** | `learner_analytics.py` pure helpers; no AI provider on the read path |

**12/12 verified.**

---

## 5. Product Capability Audit (post-P13)

Convention: **COMPLETE** (implemented + wired + tested + persisted) · **PARTIAL** (implemented but wiring/gap) · **MISSING** (not implemented/orphaned) · **BROKEN** (fails at runtime) · **DEFERRED** (explicitly out of scope).

### A. Authentication and user isolation — COMPLETE
Argon2id, access+refresh JWT (Redis JTI revocation for refresh), httponly/secure/samesite cookies, 404-equalized ownership everywhere learner-touching. Isolation suites green: two-user 22, P6 assessment 15, mastery-tutor 8, learner-progress 5, review 6, P11 security 5, P13 analytics 9. **Remaining (pre-existing, carried):** access tokens stateless/unrevocable (15-min expiry mitigates); refresh rotation does not revoke the consumed JTI; OAuth at `auth.py:321-324` matches `(google_id) | (email)` with `EMAIL_VERIFICATION_REQUIRED=False` (account-linking vector); tokens also echoed in JSON bodies.

### B. Lesson ingestion — COMPLETE
Upload/extraction/lesson-generation (Celery) → playable versioned lessons; `upload.html → processing.html → player.html` real path.

### C. Topic/lesson sequencing — COMPLETE
`topic_outline_service`, lesson versions, slide engine with keyboard navigation.

### D. Visual learning — COMPLETE
SVG canvas/strategy renderers on the player; static visual types.

### E. Animation/simulation — PARTIAL
Player uses `/animations/plan` + `/animations/runtime/sync`; animation `classify` + several GET blueprint routes unwired; simulation start/step wired but parameters/playback/reset backend-only; **both runtime states in-memory** (not multi-replica safe).

### F. Video learning — PARTIAL
`/videos/create` wired to the player but **renders synchronously in the async request handler** (4× `subprocess.run` in `video_renderer_service.py`, blocking the event loop ~15s+); `/videos/runtime` router (bookmark/assessment/tutor-context) is **dead from the frontend** (zero callers).

### G. Interactive player — COMPLETE
Lesson rendering, learner-journey panel, adaptive quiz overlay, motion engine, dashboard hub link.

### H. Quiz/assessment — COMPLETE
Quiz → attempts → question attempts → user answers → score summaries, PG-correct after P12.

### I. Genuine adaptive assessment — COMPLETE
`adaptive_assessment.py` deterministic ordering + within-attempt `/next`; ADAPTIVE badge + rationale; PG + unit + E2E verified. Inter-attempt adaptation / IRT / elo deferred.

### J. Mastery calculation — COMPLETE
`educational_memory_service` bands (weak<50, developing 50–85, mastered ≥85), BoundedCache 5000/1800, written on quiz submission only. Mastery scalar is **stable and quiz-owned** (invariant to preserve).

### K. Mastery-aware recommendations — COMPLETE
`recommendation_engine` (50/85/95) → dashboard Next Best Actions with deep-links.

### L. Spaced review — COMPLETE (schedule side)
`review_scheduler` 1/3/7/14 ladder, lazy `_ensure_schedules` on dashboard read, due queue bounded (≤limit; `MAX_DUE_LIMIT=200` for internal scans).

### M. Review scheduling — PARTIAL (outcome side)
Schedules exist and advance, **but no recall outcome is captured and failure does not shorten the interval**; the ladder is pure time. See §7 (journey) and §9 (remediation) — **this is the broken transition that motivates P14.**

### N. Remediation — COMPLETE
Tutor `remediate()` → deterministic take-knowledge-check next_action + practice CTA.

### O. Learner dashboard — COMPLETE
Stats, Next Best Actions, review queue, Today Plan, Goals, Learning Path, lesson progress, chips, trend, and now P13 analytics panels.

### P. Learner analytics — COMPLETE (P13)
Four `/me/analytics/*` endpoints + three dashboard panels, deterministic, learner-scoped, deep-linked. Attempt-history depth and analytics export remain thin (future, not needed to close a loop).

### Q. Learner trajectory — COMPLETE
Trend (≤30 pts), concept up/flat/down + numeric delta, effort-vs-mastery, focus callout.

### R. Study plans/goals — COMPLETE
Today Plan, goals (server-derived progress), item completion; P11 browser-verified.

### S. Learning paths — COMPLETE
Weakest-first ordered path with deep-links; P11 browser-verified.

### T. AI tutor — COMPLETE
Multi-turn learner-scoped RAG chat, deterministic fallback, attribution/confidence, remediation CTA. Tutor 2.0 depth deferred.

### U. Semantic RAG — COMPLETE (semantic path)
Embedding + cosine retrieval with threshold + positional fallback; learner-scoped upstream. **RAG fusion (RRF/MMR) inert** (`TUTOR_RETRIEVAL_MMR_LAMBDA`/`TUTOR_RETRIEVAL_RRF_K` unconsumed) — DEFERRED.

### V. Educational memory — COMPLETE
Concept memory with bands/categorical trend/review counters, JSONB `memory_data`, cache-backed, PG-created by migration 0033.

### W. Adaptive learner intelligence — COMPLETE (deterministic)
Mastery → assessment → recommendations → review priority (pressure buckets) → plans → path → analytics focus. All rule-based, no AI on intelligence paths.

### X. Export — COMPLETE (created surface, limited)
Export jobs/files/templates + CSV with injection prefix guard; PPTX/PDF document export; learner-data export not a focus. (Note: no dedicated browser E2E; covered by API tests.)

### Y. Persistence — COMPLETE (PG-correct)
Assessment spine PG-verified (P12); analytics tables (`analytics.py` models) remain **orphaned** — P13 deliberately read-composed existing tables instead (matching the scope contract; zero write path). `presentation_analytics` beat task is creator-level, unrelated.

### Z. Browser E2E coverage — COMPLETE (18 tests, 9 files)
smoke, learner-journey, P6 full loop, P7 dashboard, P8 tutor, P10 NG-1/2/3, P11 plans/goals/path, P12 adaptive A/B, P13 analytics (render/empty-state/hub). **Journey gaps:** no upload→processing→player browser journey; no review-completion (outcome) journey yet — directly relevant to P14.

### AA. PostgreSQL parity — COMPLETE (assessment + analytics spine)
25 PG tests incl. analytics aggregation over migrated schema and migration-head guard. Past the assessment/analytics spine, coverage is behavioral-only on other tables (carried).

### AB. Observability — COMPLETE
`/api/v1/metrics` with `p11_*`/`p12_*`/`p13_*` families, request IDs, structlog, slow-request logs (1000ms), no PII. Tracing/alerting absent (carried).

### AC. Performance/scalability — PARTIAL
Bounded-world caps on all learner-facing reads (progress ≤20/≤10, analytics ≤30/≤100, review ≤100/200-scan, plan ≤111). **Material concerns:** sync video render blocks the event loop (HIGH); `effectiveness_service` `.all()` full-table user-scoped reads (L288/338/457); `count_due` unbounded-but-unused; OFFSET pagination none; no functional Redis/Celery test (mocks only); in-memory animation/simulation/video runtime state (not replica-safe).

### AD. Retention — PARTIAL / BROKEN-OUTCOME
Review completion advances a pure time ladder with **zero outcome sensitivity**, decay is computed-pure-not-persisted, no retention beat task, and the dashboard surfaces **no retention/decay signal** to the learner. **This is the highest-value remaining learner gap.**

### AE. Background processing — PARTIAL
Celery workers + beat (health, presentation analytics, cleanups, embedding maintenance) exist; live broker integration test MISSING; video render deliberately NOT delegated; no retention/scheduling task.

---

## 6. Learner Journey Audit (post-P13)

| # | Transition | Runtime status | Evidence |
|---|---|---|---|
| 1 | Register | CONNECTED | signup → `/auth/register` → sign in |
| 2 | Sign in | CONNECTED | arcdot, JWT cookies + body tokens |
| 3 | Discover content | CONNECTED | dashboard indices + upload entry |
| 4 | Start lesson | CONNECTED | player?lesson= → learning sessions |
| 5 | Understand concept | CONNECTED | slide engine + chips + journey panel |
| 6 | Visualize | CONNECTED | SVG strategies; animation/simulation PARTIAL |
| 7 | Practice (chapter checkpoint) | CONNECTED | "Take Checkpoint" → adaptive quiz |
| 8 | Assess | CONNECTED | start → answer → `/next` → submit |
| 9 | Receive result | CONNECTED | score ring + rationale + next action CTA |
| 10 | Mastery updated | CONNECTED | `_update_concept_mastery` on submit (public-ID keyed) |
| 11 | See trajectory/analytics | CONNECTED (P13) | dashboard trajectory/concepts/effort panels |
| 12 | Review/remediation decision | CONNECTED | reco + tutor remediate (knowledge-check CTA) |
| 13 | Recommendation | CONNECTED | Next Best Actions deep-links |
| 14 | Review due work | CONNECTED | `/me/review` queue; learner can complete/skip |
| 15 | **Review → adaptation** | **BROKEN** | completing a review captures **no outcome**; interval never reacts to forgetting; decay not persisted; nothing learner-visible changes beyond the clock reset (`review_schedule_service.py:113-183`) |
| 16 | Next learning action | CONNECTED | player/tutor deep-links from reco/plan/path/analytics |
| 17 | Return to learning later | CONNECTED | dashboard hub; player→dashboard link (P13) |
| 18 | Long-term progress | CONNECTED (measure) / PARTIAL (retention) | analytics show accuracy trajectory; **no retention/decay trajectory exists** |

**Dead ends / duplication check:**
- `?deck=` fully retired (P13). No dead buttons verified in dashboard (`recoAction` guards). 
- `/videos/runtime/*` = dead API surface (no frontend callers). Animation classify + 5 GET blueprint routes unwired. Simulation params/playback/reset unwired.
- tutor.html refresh-token **divergence** (pre-existing): `authFetch` refresh branch stores only `access_token`, not the rotated `refresh_token` ({~L183-185}) — stale refresh token retained after rotation. LOW (mild refresh fragility).
- `?deck=` removed; `upload.html` has no dashboard link (minor).

**Most important remaining broken transition:** `#15 — Review → adaptation`. The review leg is the only stage of the connected spine that receives **no input about the learner** and produces **no calibrated consequence**. Everything else adapts; reviews do not.

---

## 7. Architecture Audit

- **Duplicated/orphaned services:** `models/analytics.py`, `schemas/analytics.py`, `schemas/analytics_insights.py` remain orphaned (zero callers) — deliberate P13 outcome (read-composition). `video_runtime_router.py` dead. `count_due` (`review_schedule_repository.py:108`) defined/unused.
- **Dead endpoints/config:** 8 of 9 rate-limit override patterns match **no registered route** (only quiz-submit `=30/60` is live); `^/api/v1/quizzes/[^/]+/session$` stale override. `get_ai` dependency dead (zero `Depends(get_ai)`). `UPLOAD_ALLOWED_EXTENSIONS` second allow-list unused (hard-coded supported-ext list in `set_source` instead).
- **Transaction boundaries:** UoW-based; quiz `start/next/submit` and review `complete/skip` persist within single units; no nested transactions observed.
- **Ownership consistency:** universal `get_for_user`/`assert_ownership`/404-equalization; `assert_quiz_ownership(quiz_id, user.id)` invoked at `quiz.py:70/90/138` (P1-fixed — verified no regression).
- **Migration drift:** none — single linear chain `0001..0033`, single head; P12 parity verified by PG behavioral suite; analytics tables intentionally untouched.
- **Unbounded memory/result sets:** learner-facing paths bounded (see §12); `effectiveness_service` `.all()` user-scoped full reads and unused `count_due` are the exceptions.
- **Process-local state:** animation/`_RUNTIME_STATES`, simulation `_sessions`, video project cache — in-memory (multi-replica risk, carried).
- **Missing indexes:** trend aggregation orders by `quiz_attempts.completed_at` filtered `user_id+status` — covered only by the 500-row scan cap (P13 deliberately chose scan-limit over a new index; acceptable at current scale, documented).
- **Stale comments/docs:** docstrings still reference "no rewrite" semantics (accurate today); P14 will supersede them.

---

## 8. Security Audit (post-P13)

Pre-existing controls preserved; **no new attack surface from P13** (analytics resolve user only from `get_current_user`; no client identifiers; B sees empty, never A's rows).

| Find | Sev | Evidence / status |
|---|---|---|
| OAuth account-linking: `(google_id) OR (email)` with `EMAIL_VERIFICATION_REQUIRED=False` | **HIGH (pre-existing)** | `auth.py:321-324`, `config.py:319` — a Google account provided an unverified registered email can adopt the account. Not fixed by P13. Documented. |
| Prompt-injection guard inert: `TUTOR_INJECTION_FLAG_THRESHOLD` unconsumed | **HIGH (carried)** | `config.py:238`; bounded mitigation = learner-scoped RAG (self-only window) + sync request only |
| `/uploads` public static mount serves generated TTS audio + rendered MP4s without auth (guessable IDs) | **MED (pre-existing)** | `main.py:181-183`, `tts_service.py`, `video_renderer_service.py`; blocks listing; private storage path NOT exposed — exposure limited to own-generated media via known id |
| Access tokens stateless/unrevocable | **MED (carried)** | 15-min expiry compensates |
| Refresh rotation does not revoke consumed JTI | **MED (carried)** | old token valid until expiry |
| CSRF wiring inert (functions exist, no enforcement); mitigated by SameSite=Lax + same-origin mount | **MED (carried)** | `security.py:138/142`, `config.py:322` |
| `.env` holds real-looking secrets | **LOW (carried)** | verified gitignored + untracked (`git ls-files .env` empty; `git grep` clean) — local only |
| Rate-limit fails OPEN without Redis | **MED (carried)** | `rate_limit.py:157-159,207-211` |
| tutor.html refresh-token divergence (only access_token re-saved) | **LOW (pre-existing)** | frontend audit — stale refresh token after rotation |
| Todo: learner-scoped analytics ✓, review isolation ✓ (404), tutor isolation ✓ | — | all green suites |

No CRITICAL finding was verified this pass. The two HIGH rows are pre-existing, carried, and documented rather than silently fixed.

---

## 9. Remediation / Review-Feedback Audit (evidence for P14)

- **`ReviewScheduleService.complete`** (`review_schedule_service.py:113-183`): takes **no outcome**; always `next_interval(step)` → advances; failure cannot shorten an interval; docstring explicitly says mastery is **not** changed (L122-123, L167).
- **`compute_decay_signal`** (`review_scheduler.py:82-115`): pure, deterministic "review pressure" — **persists nothing**, only annotates queue priority (`priority_bucket`).
- **`review_metadata`** JSONB (`review_schedule.py:84-86`) already carries `step`, `last_pressure`, `skipped_at` — a proven, existing persistence surface for review outcomes (no schema change required to add `outcome`/`history`).
- **`educational_memories.memory_data`** JSONB (migration 0033) + `record_review_activity` — existing surface for a deterministic retention/decay signal.
- **Mastery invariant:** `mastery_score` is written ONLY on quiz submission (`educational_memory_service.update_concept_mastery`). Any review-driven signal must be **separate** from this scalar to preserve P10 NG-3 and P2/P7 semantics.
- **Scheduling:** interval ladder 1/3/7/14 (`review_scheduler.py`), lazy seeding `_ensure_schedules` (`review_schedule_service.py:233-285`), queue priority `high/medium/low`. Learner outcome currently contributes zero.
- **No retention beats:** `celery_app.py:69-106` beat has no retention/decay/scheduling task.

**Conclusion:** The review leg has persistence, a queue, deep-links, an E2E suite — but no learner feedback loop. Exactly one change closes it: capturing recall outcomes and adapting deterministically from them + persisting a retention signal the learner can see.

---

## 10. Performance Audit

Measured/bounded facts (no load numbers claimed — none exist; no fabricated numbers):
- **Learner-facing reads bounded:** progress ≤20 recent / ≤10 trend, analytics ≤30 window / ≤100 concepts+effort / 500-attempt scan for overview, review ≤100 queue / ≤200 internal scan, plan ≤111 productivity items.
- **Assessment path ≈ 6 bounded queries** with `selectinload` + batched `IN` — no N+1 (verified P12).
- **Video render — the single worst offender:** `/videos/create` runs synchronous 4× `subprocess.run` FFmpeg in an `async def` handler (`video_router.py:110`, `video_renderer_service.py:119/133/146/170`) — blocks the event loop for the render (~15s+). Directly caps any video product push and any multi-replica request concurrency during renders.
- **Aggregation:** `effectiveness_service` `.all()` user-scoped full-table reads (`:288/:338/:457`); `count_due` unbounded-unused. Analytics scan-capped instead of indexed (`completed_at` ordering) — acceptable and documented.
- **Redis/Celery:** no functional integration test (mocks only) — blocks risk-free scheduled/worker features.

---

## 11. UX Audit

"Can a real learner understand what to do next without knowing the internal architecture?" — **Largely yes** on the learn/measure leg; **no** on the retention leg:
- Dashboard → player ✓; player → dashboard ✓ (P13); dashboard → tutor?concept= ✓; tutor → player?lesson= ✓; reco/plan/path CTAs ✓; analytics → practice/tutor ✓.
- **The review queue is the weak spot:** a learner can complete a review and see only "next due in N days" — nothing tells them *today* whether they're retaining ("at risk"/"on track"), and nothing changes because they did well or poorly.
- Loading/empty states good on analytics/review/plan (skeleton + "No checkpoints yet"); error states use the shared envelope.
- Remaining dead ends (minor): `/videos/runtime` unreachable from UI; animation classify + 5 GET blueprint routes unwired; simulation advanced controls backend-only; upload.html post-login links only to self + sign-out.

---

## 12. P13 Regression Audit — Adaptive `/next`

- **Product path is correct and deterministic:** `adaptive_assessment.py` pure selector; `/next` persists the answered question, re-evaluates correctness server-side, returns the server-chosen next question; ordering key and in-attempt ±1 clamped 0..2; PG + unit + E2E (P12) green.
- **Root cause of the P12-era flake (established, not reopened):** both P10 tests clicked the Q2 option via `.quiz-opt` `.first` while the adaptive `/next` DOM rebuild had not yet replaced Q1's options — the click re-selected the stale Q1 option, Q2's answer stayed `[]`, server graded 1/2 = 50%. Reproduced at the P12 baseline (`c730350~1`) via `git stash`, proving it was NOT P13-introduced.
- **Fix is correctly scoped:** test-only `_wait_for_question(page, stem)` synchronization inside `tests/e2e/test_p10_adaptive_review_e2e.py`; zero product-behavior changes; the identical player payload path is exercised exactly as before, just deterministically-timed.
- **Evidence this pass:** full browser suite **18 passed, 0 failed**; the P10 file alone 3/3.

---

## 13. Remaining Product Gaps (ranked, post-P13)

| Rk | Gap | Findings | Best evidence | Priority |
|---|---|---|---|---|
| 1 | **Retention invisible + review does not adapt** | Review completion captures no outcome; failure never shortens the interval; decay computed-but-never-persisted; no retention surface anywhere; no retention beat. Learner cannot see or influence retention. | `review_schedule_service.py:113-183,167`; `review_scheduler.py:82-115`; `celery_app.py:69-106` | **HIGH** |
| 2 | **Video learning incomplete + render blocks loop** | `/videos/runtime` dead from UI; `/videos/create` synchronous render blocks event loop (4× subprocess.run). | `video_runtime_router.py`; `video_router.py:110`; `video_renderer_service.py:119+` | HIGH (feature), HIGH (perf) |
| 3 | Adaptive 2.0 (inter-attempt/IRT/elo) | Depth extension; mutates assessment/mastery invariant just stabilized. | P12 report §7 | MED (deferred) |
| 4 | RAG fusion (RRF/MMR) + Tutor 2.0 | Inert knobs; AI-risk heavy; tutor already works. | `config.py:222-223` unconsumed | MED (deferred) |
| 5 | Mastery decay persistence (as mastery rewrite) | Mutates the core mastery scalar owned by quizzes. | `compute_decay_signal` pure | MED (defer behind retention signal design) |
| 6 | Performance/scale hardening | Sync render, `.all()`s, Redis/Celery functional test, stale rate-limit config, `/uploads` exposure. | §10 audit | MED (platform) |
| 7 | Deep analytics extension / export | Attempt-level depth; diminishing returns right after P13. | — | LOW |

---

## 14. Candidate P14 Directions & Scoring

Scoring model (per criterion 1–5, 5 = best; weights same as Post-P12 for continuity): Learner value 0.25 · Architectural fit 0.15 · Foundation readiness 0.15 · Implementation complexity (inverse) 0.10 · Security risk (inverse) 0.10 · Data-model risk (inverse) 0.08 · AI-independence 0.07 · Testing/browser ease 0.05 · Scalability 0.03 · Learning-loop-gap closure 0.02.

| Cand | Direction | Lrnr .25 | Fit .15 | Ready .15 | Cx⁻¹ .10 | Sec⁻¹ .10 | DM⁻¹ .08 | AI⁰ .07 | Test .05 | Scale .03 | Loop .02 | **Total** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **A** | **Retention + Review Automation (outcome-driven reviews, persisted decay, retention surface)** | 5 (1.25) | 5 (0.75) | 5 (0.75) | 4 (0.40) | 5 (0.50) | 5 (0.40) | 5 (0.35) | 4 (0.20) | 4 (0.12) | 5 (0.10) | **4.82** |
| B | Video learning runtime completion (+ render offload) | 3 (0.75) | 3 (0.45) | 3 (0.45) | 2 (0.20) | 3 (0.30) | 4 (0.32) | 3 (0.21) | 2 (0.10) | 2 (0.06) | 3 (0.06) | 2.90 |
| C | Learner Workspace / hub completion 2.0 | 2 (0.50) | 4 (0.60) | 5 (0.75) | 4 (0.40) | 4 (0.40) | 5 (0.40) | 5 (0.35) | 3 (0.15) | 4 (0.12) | 2 (0.04) | 3.71 |
| D | Deeper Learner Analytics / export | 2 (0.50) | 4 (0.60) | 5 (0.75) | 3 (0.30) | 4 (0.40) | 4 (0.32) | 5 (0.35) | 3 (0.15) | 3 (0.09) | 2 (0.04) | 3.50 |
| E | RAG fusion + Tutor 2.0 | 3 (0.75) | 4 (0.60) | 4 (0.60) | 2 (0.20) | 3 (0.30) | 4 (0.32) | 1 (0.07) | 2 (0.10) | 3 (0.09) | 3 (0.06) | 3.09 |
| F | Adaptive Assessment 2.0 (inter-attempt/IRT) | 3 (0.75) | 4 (0.60) | 4 (0.60) | 2 (0.20) | 3 (0.30) | 3 (0.24) | 4 (0.28) | 3 (0.15) | 3 (0.09) | 3 (0.06) | 3.27 |
| G | Mastery decay persistence | 3 (0.75) | 4 (0.60) | 4 (0.60) | 3 (0.30) | 4 (0.40) | 2 (0.16) | 5 (0.35) | 3 (0.15) | 3 (0.09) | 3 (0.06) | 3.46 |
| H | Performance/scale + platform hardening | 2 (0.50) | 4 (0.60) | 3 (0.45) | 3 (0.30) | 4 (0.40) | 5 (0.40) | 5 (0.35) | 3 (0.15) | 5 (0.15) | 1 (0.02) | 3.32 |

**Ranked:** **A (4.82)** > C (3.71) > D (3.50) > G (3.46) > H (3.32) > F (3.27) > E (3.09) > B (2.90).

**Score rationale (A):**
- **Learner value 5** — retention is the measurable reason a learner stays; "am I actually retaining this?" is the natural successor question to P13's "am I improving?". Recall-outcome is the single learner input the platform currently ignores.
- **Fit/readiness 5/5** — full reuse: `review_schedules` (incl. JSONB `review_metadata`), `educational_memories`, `compute_decay_signal` (pure, ready to persist), review E2E + crypto-adjacent isolation suites, analytics panels as the retention surface. `complete()` is an existing, learner-scoped, 404-equalized endpoint with a body-less contract ripe for an optional, backward-compatible outcome body.
- **Data-model risk 5 (low)** — no new table, no migration-for-migration's-sake: outcomes/history land in existing JSONB; retention signal is a **separate derived metric, never the quiz-owned mastery scalar** (preserves NG-3). Smallest possible change.
- **Security risk 5 (low)** — learner-scoped endpoints already exist and are 404-equalized; new cross-user isolation test is mechanical (mirror `test_review_api_security.py`).
- **Loop gap closure 5** — directly fixes the #1 evidence finding (§13-1, §6 #15).

---

## 15. Recommended P14

**P14 — Retention & Review Automation ("Close the review loop"):**
> *When a learner reviews a concept, the platform captures whether they actually recalled it, adapts the spaced interval deterministically from that outcome, persists a retention/decay signal, and shows the learner their retention over time.*

It is the only candidate that closes a **broken transition in the connected spine** (review → adapt), rather than extending an already-complete surface. It is deterministic (zero AI), learner-scoped, fully readable from existing JSONB, backward-compatible with the existing review API, and browser-verifiable with a real learner journey (review → outcome → interval change → retention panel → refresh persistence) plus a User A / User B isolation pass. It also sets the foundation the retention/decay roadmaps keep deferring — without rewriting the mastery invariant.

**Why the top alternatives are NOT P14 now:**
- **C (Workspace/hub 2.0)** — no capability gap: P13 closed the biggest dead-end (player→dashboard); the remainder is polish that should be folded opportunistically into P14's dashboard work, not a phase.
- **B (Video runtime + render offload)** — genuinely valuable but (a) value is capped until the synchronous render is off the event loop, an infra decision with real perf risk, and (b) it extends a *content-experience* niche while the *learning-loop* gap (retention) is unaddressed. Defer; the render-offload hardening item can move on the roadmap when video becomes the priority.
- **D/G/H** — deeper analytics right after P13 yields diminishing returns for the loop; mastery-decay-as-rewrite and generic hardening either mutate the stable mastery invariant or are platform-work that delivers no directly-observed learner capability.

---

## 16. P14 Constraints (non-negotiable)

- Read/reuse existing tables (JSONB fields, review_schedules, educational_memories, analytics panels). A migration is **explicitly NOT** part of the MVP unless profiling of the retention aggregation demands an additive index (same optional, documented rule as P13).
- Retention signal is a **separate deterministic metric**; the quiz-owned mastery scalar and the P10 NG-3 loop are untouched.
- All endpoints learner-scoped; existing 404-equalization and the review isolation suite extended (User A/B).
- Deterministic only; NO LLM insight, NO ML/IRT. Vanilla `backend/frontend/` preserved.
- PostgreSQL parity: new review-outcome path + retention aggregation verified on migrated PG; single Alembic head `0033` preserved.
- Mypy stays 83/24 (zero new) unless a future phase intentionally justifies a change.
- No framework migration; no broker dependency for the MVP (lazy seeding preserved; beat task explicitly OPTIONAL and out of core MVP).

---

## 17. Audit Conclusion

P13 is **VERIFIED** end-to-end: deterministic learner analytics delivered, gate numbers confirmed from live output (SQLite 1213, PG 25, E2E 18 stable, Ruff clean, mypy 83/24, single head `0033`, secret scan clean, clean tree), and the P10 adaptive-`/next` flake closed as a test-side race with product correctness intact.

Product-wise, the learn→measure→adapt spine is now **connected and learner-visible**. The audit's clearest empirical finding is that the **review leg does not adapt to the learner** — outcomes are never captured, intervals never react to forgetting, decay is never persisted, and retention is invisible. That is the highest-value remaining gap, it is fully solvable with existing schema and a deterministic design, and it is browser-verifiable. **P14 = Retention & Review Automation**, with full foundation in **`P14_SCOPE_AND_FOUNDATION.md`**. NO P14 implementation is performed in this phase.