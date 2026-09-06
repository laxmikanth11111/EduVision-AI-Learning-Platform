# Post-P14 Product & Architecture Audit

**Phase:** P14 (Retention & Review Automation — "Close the review loop") — audit
**Type:** Audit + product decision only — NO P15 implementation
**Branch:** `feature/individual-user-foundation`
**Audited HEAD:** `88af40946ee3bbf46571214c1518d7ad9801176e` (`feat(p14): close the review loop with self-reported recall outcomes and a retention surface`)
**Alembic head:** `0033_educational_memories` (single, verified)
**Date:** 2026-09-06

---

## 1. Executive Summary

P14 is **complete, committed, and clean** at HEAD `88af409`. Independent re-verification this pass (source + live gate output) confirms every P14 release gate: SQLite unit+integration **1295 passed**, PostgreSQL **30 passed** (real migrated engine), browser E2E **21 passed** (full suite), Ruff **clean on the whole repo**, mypy exactly **83 errors / 24 files** (the P12/P13 authoritative baseline — zero new), a **single Alembic head `0033_educational_memories`**, a **clean working tree**, `git diff --check` clean, and a secret scan free of real secrets.

P14 delivered exactly what its scope contract promised:
1. A **controlled recall vocabulary** (`again | hard | good | easy`) captured on review completion, driving a deterministic interval ladder (`again`→step 0, `hard`→hold, `good`→+1 [== legacy], `easy`→+2 capped at 3) persisted into the existing `review_metadata` JSONB as versioned (`"v": 2`), capped (20-entry) outcome history — **zero migration**.
2. A **retention/recall signal** per concept (weighted recent outcomes, decayed by days since review) — deliberately separate from the quiz-owned mastery scalar, surfaced as `on_track | at_risk | overdue | new`, plus a bounded read-only `GET /me/analytics/retention`.
3. A **dashboard Retention panel** + **review-queue outcome buttons** (Mark reviewed = good first, then Again/Hard/Easy), all `escHtml`-escaped with server-built deep-links, browser-verified end to end including User A / User B isolation and refresh persistence.

Product-state: the connected learning spine — **Learn → Understand → Visualize → Practice → Assess (adaptive) → Measure → Recommend → Review → Recall Outcome → Reschedule → Return to Learning** — is now **connected, learner-visible, and adaptive at every stage for the first time**. The last ignored learner input (review recall) is now captured and drives the schedule.

**This pass's most important remaining broken transitions (evidence-backed):**
1. **Resume is promised but does not function** — the sign-in page promises "Pick up where you left off" and the dashboard says "click a lesson to resume", yet the player always starts at slide 0 unless a `?slide=` query param is manually supplied; the server already persists the learner's topic position in `learning_sessions` (`current_block_position`) and has an idle `current_slide_position`/`resume_version` (migration 0009) that no endpoint writes. Every returning-learner path restarts the lesson. This is the **highest-value remaining learner gap** and the P15 target.
2. **Post-login hub dead-end** — after sign-in/register the user lands on `upload.html`, which has **no link to the learner Dashboard or Tutor**; only Sign-out exits the page.
3. **Video learning remains a production risk** — `/videos/create` still renders synchronously (4× `subprocess.run` FFmpeg) inside an `async` handler and blocks the event loop; `/videos/runtime` is still dead from the frontend. Carried, documented, not selected for P15.

---

## 2. Current Repository State

| Item | Expected | Verified | Evidence |
|---|---|---|---|
| Branch | `feature/individual-user-foundation` | yes | `git branch --show-current` |
| HEAD | `88af409` (P14 completion) | yes | `git rev-parse HEAD` |
| Working tree | clean (post-commit) | yes | `git status --short` = empty |
| Alembic head | single `0033_educational_memories` | yes | `alembic heads` |
| P14 report/scope docs | present | yes | `P14_IMPLEMENTATION_REPORT.md`, `P14_SCOPE_AND_FOUNDATION.md` |
| Migration count | unchanged by P14 (0033 single) | yes | 33-revision linear chain, single head |

---

## 3. Verification Baseline (independently re-verified this pass)

| Gate | Command | Observed |
|---|---|---|
| git status | `git status --short` | clean |
| current commit | `git rev-parse HEAD` | `88af40946ee3bbf46571214c1518d7ad9801176e` |
| Alembic heads | `alembic heads` | `0033_educational_memories (head)` — single |
| SQLite regression | `pytest -q tests/unit tests/integration` | **1295 passed**, 0 failed (1 external StarletteDeprecationWarning) |
| PostgreSQL | `pytest -q tests -m postgres` | **30 passed** (real testcontainers engine, head `0033`) |
| Browser E2E | `pytest -q tests/e2e -m e2e` | **21 passed, 0 failed** (full suite run) |
| Ruff | `ruff check .` | **All checks passed** (whole repo) |
| Mypy | `mypy app` | **83 errors / 24 files** (checked 305 source files) — exactly the P13 baseline, zero new (verified none touch P14 files) |
| git diff --check | `git diff --check` | clean (exit 0) |
| Secret scan | `Select-String` over P14 new/changed files | 0 real secrets; only deterministic E2E fixture passwords (`P14Loop1234!` — the established `P14/P13/P10/P12Loop1234!` pattern) |

---

## 4. P14 Capability Verification (independent, from source)

| # | P14 contract item | Verdict | Evidence |
|---|---|---|---|
| 1 | Recall outcome vocabulary `again/hard/good/easy` | **VERIFIED** | `app/services/retention.py:31-40` (`REVIEW_OUTCOMES`), strict enum `app/schemas/review.py:17-36` |
| 2 | Backward-compatible absent-body behavior (== legacy `good`) | **VERIFIED** | `app/api/v1/review.py:56` default `"good"`; `review_schedule_service.py:117` `DEFAULT_OUTCOME`; unit tests prove absent body == legacy interval |
| 3 | Invalid outcome rejection | **VERIFIED** | `ReviewOutcome` enum → 422 via Pydantic; service `validate_outcome` guard at `retention.py:87-91` |
| 4 | Ownership enforcement (cross-user 404 no-write) | **VERIFIED** | `complete()` resolves via `get_by_user_and_public_id` (`review_schedule_service.py:135-142`); integration + PG + E2E `test_p14_*_learner_scoped`/`test_p14_retention_is_learner_scoped` (404 with no interval change) |
| 5 | Review outcome persistence | **VERIFIED** | `apply_outcome_to_metadata` (`retention.py:156-181`): `history` capped 20 + fixed-size `counts` + `"v": 2`, merged into existing JSONB, backward compatible with pre-P14 rows |
| 6 | Deterministic interval adaptation | **VERIFIED** | `outcome_next_step` (`retention.py:94-110`): again→0, hard→hold, good→+1, easy→+2 capped `MAX_STEP`; ladder `(1,3,7,14)` reused from `review_scheduler` |
| 7 | Retention analytics endpoint | **VERIFIED** | `GET /me/analytics/retention` (`analytics.py:113-128` → `LearnerAnalyticsService.get_retention`), bounded ≤100, learner-scoped, deterministic sort, server-built deep-links |
| 8 | Retention dashboard surface | **VERIFIED** | `dashboard.html` Retention panel (summary chips + per-concept rows) + queue outcome buttons (`dashboard.html:380-382, 639-646, 821-870`); all rendered via `escHtml` |
| 9 | Review queue outcome controls | **VERIFIED** | 4 buttons (Mark reviewed = good first, then Again/Hard/Easy) call `completeReview` → POST with `{outcome}`; queue re-fetch + panel advance |
| 10 | Mastery scalar preservation | **VERIFIED** | `complete()` never calls `update_concept_mastery`; retention is a separate observed-recall signal; invariant asserted in unit/integration/E2E |
| 11 | No schema migration | **VERIFIED** | `alembic heads` single `0033`; `test_p14_no_new_migration_head_unchanged` in PG suite |
| 12 | Browser coverage | **VERIFIED** | 3 new P14 E2E tests (21 total suite); refresh-persistence + User A/B isolation in real browser |
| 13 | Observability | **VERIFIED** | `p14_review_outcomes_total{outcome}`, `p14_retention_views_total`, `p14_retention_errors_total` in `observability/metrics.py:201-204`; rendered via `/api/v1/metrics` |

**13/13 verified. The review loop is truly closed.**

---

## 5. Product Capability Audit (post-P14)

Convention: **COMPLETE** · **PARTIAL** (implemented but wiring/gap) · **MISSING** · **BROKEN** · **DEFERRED**.

| Capability | Status | Notes |
|---|---|---|
| A. Auth + user isolation | COMPLETE | Argon2id, JWT access/refresh + httpOnly cookies, 404-equalized ownership everywhere learner-touching. Carried pre-existing: OAuth `(google_id)|(email)` match, refresh rotation does not revoke consumed JTI. |
| B. Lesson ingestion | COMPLETE | Upload/extract/generate (Celery) → playable versioned lessons. |
| C. Topic/lesson sequencing | COMPLETE | `topic_outline_service`, lesson versions, slide engine + keyboard nav. |
| D. Visual learning | COMPLETE | SVG canvas/strategy renderers on the player. |
| E. Animation/simulation | PARTIAL | Wired player paths; runtime state in-memory (not replica-safe); several GET blueprint routes unwired. Carried. |
| F. Video learning | PARTIAL / RISK | `/videos/create` wired but renders synchronously in the async handler (4× `subprocess.run` blocks the event loop); `/videos/runtime` dead from frontend. **Carried HIGH perf/feature gap — not selected for P15 (§20).** |
| G. Interactive player | PARTIAL | Lesson render + learner-journey panel + adaptive quiz overlay. **Resume is broken (see §7/§13).** |
| H. Quiz/assessment | COMPLETE | Quiz → attempts → question attempts → score summaries, PG-correct. |
| I. Adaptive assessment | COMPLETE | Deterministic within-attempt `/next`; PG + unit + E2E. Inter-attempt/IRT deferred. |
| J. Mastery calculation | COMPLETE | Bands weak/developing/mastered, cache-backed, written on quiz submission only. Invariant preserved by P14. |
| K. Mastery-aware recommendations | COMPLETE | Deterministic Next Best Actions with deep-links. |
| L. Spaced review | COMPLETE | 1/3/7/14 ladder, lazy seeding, bounded due queue. |
| M. Review scheduling (outcome side) | **COMPLETE (P14)** | Outcome-driven ladder + persisted history + retention signal. The P13 "broken" transition is now closed. |
| N. Remediation | COMPLETE | Tutor remediate → knowledge-check CTA + practice. |
| O. Learner dashboard | COMPLETE | Stats, actions, review queue, Today Plan, goals, path, lesson progress, concepts, analytics, retention. |
| P. Learner analytics | COMPLETE | 4 `/me/analytics/*` endpoints + 3 panels (P13) + retention (P14). |
| Q. Learner trajectory | COMPLETE | Trend, concept delta, effort-vs-mastery, retention current-state. (Retention *trend over time* deferred.) |
| R. Study plans/goals | COMPLETE | Today Plan, goals, item completion (P11, browser-verified). |
| S. Learning paths | COMPLETE | Weakest-first ordered path. |
| T. AI tutor | COMPLETE | Multi-turn learner-scoped RAG, deterministic fallback, remediation CTA. Tutor 2.0 deferred. |
| U. Semantic RAG | COMPLETE (semantic path) | Embedding + cosine + positional fallback. RRF/MMR fusion knobs inert (deferred). |
| V. Educational memory | COMPLETE | Concept memory, bands, JSONB `memory_data`, PG migration 0033. |
| W. Adaptive learner intelligence | COMPLETE | Deterministic rule-based mastery→assessment→review→plan→analytics. |
| X. Export | COMPLETE (limited) | Export jobs/files + CSV/DOCX/PPTX; injection-prefix guard. No dedicated browser E2E (API-tested). |
| Y. Persistence / PG parity | COMPLETE | Assessment + analytics spine PG-verified. `learning_sessions` fully migrated (0009) with resume columns. |
| Z. Browser E2E coverage | COMPLETE (21, 10 files) | smoke, journey, P6 loop, P7 dashboard, P8 tutor, P10 NG, P11 plans/path/goals, P12 adaptive, P13 analytics, P14 retention. **Gap: no resume journey — the P15 target.** |
| AA. PostgreSQL parity | COMPLETE (behavioral) | 30 PG tests incl. JSONB round-trip, retention aggregation, migration-head guard, learner journey. |
| AB. Observability | COMPLETE | `/api/v1/metrics` with `p11_*/p12_*/p13_*/p14_*` families, request IDs, structlog, no PII. Tracing/alerting absent (carried). |
| AC. Performance/scalability | PARTIAL | Bounded learner reads. Carried: sync video render blocks loop (HIGH); `effectiveness_service` unbounded `.all()` (MED); `_ensure_schedules` `list_due(10000)` (LOW). |
| AD. Retention | **COMPLETE (P14)** | Outcome capture, deterministic adaptation, capped history, retention signal + surface. Retention trend-line / nudges deferred. |
| AE. Background processing | PARTIAL | Celery beat exists; no functional Redis/Celery integration test (mocks only); video render not delegated. Carried. |
| AF. Learner continuity / resume | **BROKEN (P15 target)** | UI promises resume; player always restarts at slide 0; server persists topic position but nothing consumes it; no `?slide=` emission; post-login hub (`upload.html`) has no dashboard link. See §7/§13. |

---

## 6. Learner Journey Audit (post-P14)

| # | Transition | Runtime status | Evidence |
|---|---|---|---|
| 1 | Register | CONNECTED | signup → `/auth/register` → sign in |
| 2 | Sign in | CONNECTED | JWT cookies + body tokens |
| 3 | Discover content | CONNECTED | dashboard indices + upload entry |
| 4 | Start lesson | CONNECTED | `player.html?lesson=` → `/player/start` |
| 5 | Understand concept | CONNECTED | slide engine + chips + journey panel |
| 6 | Visualize | CONNECTED | SVG strategies; animation/simulation PARTIAL |
| 7 | Practice (checkpoint) | CONNECTED | Take Checkpoint → adaptive quiz |
| 8 | Assess | CONNECTED | start → answer → `/next` → submit |
| 9 | Receive result | CONNECTED | score ring + rationale + next-action CTA |
| 10 | Mastery updated | CONNECTED | quiz submission |
| 11 | Measure/trajectory | CONNECTED | P13 analytics panels + P14 retention |
| 12 | Review/remediation decision | CONNECTED | reco + tutor remediate |
| 13 | Recommendation | CONNECTED | Next Best Actions deep-links |
| 14 | Review due work | CONNECTED | `/me/review` queue + outcome buttons |
| 15 | Review → adaptation | **CONNECTED (P14)** | outcome → interval → retention signal → panel |
| 16 | Next learning action | CONNECTED | player/tutor deep-links |
| 17 | **Resume / return to learning** | **BROKEN** | see §7 — the player never restores the persisted position |
| 18 | Long-term progress | CONNECTED | analytics + retention current-state (trend over time deferred) |

**Dead ends / navigation loop (evidence in §7/§8):**
- `upload.html` (post-login hub) has **no Dashboard/Tutor link** — a fresh learner is stuck between upload and sign-out.
- `player.html` has **no final-slide completion CTA** and **no sign-out**.
- `player.html` reads a dead `?deck=` param (line 316) and never consumes `session.topic_index`.
- Dashboard lesson-progress says "click a lesson to resume" but the link carries no resume position (`dashboard.html:332-338`).
- `processing.html` failure/timeout states say "refresh to retry" with no retry button.
- Review "Practice" opens the lesson at slide 0 (no checkpoint deep-link) — acceptable, out of scope.

---

## 7. Resume Audit (the P15 gap, evidence)

- **UI promise:** signin.html:55 "Pick up where you left off"; dashboard.html:332 "click a lesson to resume".
- **Server reality:** the player already persists the learner's topic position — `goTo()` → `syncTopic()` → `POST /lessons/{id}/player/set-topic` (`player.html:564-576`) → `LearningSessionService.set_topic` writes `current_block_position` + `completion_percentage` (`learning_session_service.py:139-156`); `start()` resumes the same persistent session idempotently (`get_or_create`, `:94-137`); `to_player_session` returns `topic_index` (`:173-192`).
- **Frontend non-use:** `init()` reads only `completion_percentage` and calls `goTo(startIndexFromUrl(), false)` (`player.html:339-362`); `startIndexFromUrl` returns slide 0 when no `?slide=` (`:370-374`); nothing ever writes `?slide=` or reads `session.topic_index`. **Result: every return visit restarts the lesson at slide 0.**
- **Idle schema:** migration `0009_learning_sessions` already creates `learning_sessions.current_slide_position`, `current_block_position`, `resume_version` (`0009:57-63`) with full index coverage — no schema change needed; no endpoint writes `current_slide_position` today.
- Player slide model is deterministic: topics × 2 slides (concept + visual) (`player.html:350-354`), so `slide = topic_index * 2 (+ 0|1)`.

**Conclusion:** the backend foundation for precise resume exists and is unused. P15 closes the last broken transition in the spine.

---

## 8. Architecture Audit

- **Reuse confirmed:** player (`LessonPlayerService`), session persistence (`LearningSessionService`), dashboard progress (`LearnerProgressService`), `learner_analytics` deep-links pattern.
- **Orphaned/dead:** `app/models/analytics.py` (`LearningAnalyticsSnapshot`/`CreatorAnalyticsSnapshot`/`SystemAnalytics`) remain **zero-caller** (only imported in `models/__init__.py`; a response schema exists) and — NEW finding this pass — **no migration creates their tables** on a fresh database (migration `0022` only renames `student/teacher_analytics_snapshots` if they exist). **Latent, not active**: no code path queries these tables (verified via repo-wide grep), so no request fails today; but any future feature that touches them on fresh PostgreSQL would error. Classified MEDIUM-latent (not the auditee's active break). Fix options: remove the dead models, or (if a future phase needs them) create them with an additive guarded migration. **Not P15.**
- **Transaction boundaries:** UoW-based; set-topic/advance persist within single units.
- **Ownership consistency:** universal `get_for_user`/404-equalization; player/session lookups are `user_id`-scoped (`learning_session_service.py:51-92`, 404-equivalent `None`).
- **Migration drift:** single linear chain `0001..0033`, single head; P14 added no revision.
- **Process-local state (carried):** animation `_RUNTIME_STATES`, simulation `_sessions`, video project cache, anonymous-player `_SESSIONS` (bounded/TTL'd).
- **Stale rate-limit config (carried):** 8 of 9 `RATE_LIMIT_ROUTES` patterns match no registered route; only quiz-submit `=30/60` is live (`config.py:375-385`). Generic 100/60 applies elsewhere.

---

## 9. Security Audit (post-P14)

### New P14 surface — VERIFIED-OK (no new findings)
P14 adds no new attack surface: outcome enum validates (422); cross-user completion is 404-equalized with zero write; retention reads are learner-scoped from `get_current_user`; all new dashboard content is `escHtml`-escaped; no client-supplied identifiers; body size trivially bounded.

### Findings

| Find | Sev | Tag | Evidence / status |
|---|---|---|---|
| OAuth account-linking `(google_id)|(email)` with `EMAIL_VERIFICATION_REQUIRED=False` | **HIGH** | CARRIED | `auth.py:321-324`, `config.py:319`; no `email_verified` column. Not P15 (requires auth redesign + verification flow). |
| Refresh rotation does not revoke consumed JTI | **HIGH** | CARRIED | `auth.py:376-401` issues new tokens without `_revoke_refresh_jti(old_jti)`; only logout revokes. Plus Redis-less `_revoked_refresh_jtis` set grows unbounded. |
| Sync video render blocks event loop (perf DoS) | **HIGH** | CARRIED | `video_renderer_service.py:119/133/146/170` `subprocess.run` in async handler. |
| Analytics snapshot models absent from migrations | **MEDIUM (latent)** | **NEW** | `app/models/analytics.py`; migration `0022` renames only-if-exists; no code queries them today. |
| `TUTOR_INJECTION_FLAG_THRESHOLD` dead config | **MEDIUM** | CARRIED | `config.py:238` — zero consumers; no prompt-injection guard on tutor paths. |
| `/uploads` + `/frontend` static mounts unauthenticated (guessable ids; blocks listing) | **MEDIUM** | CARRIED | `main.py:183-191`. |
| Rate limiter fails OPEN without Redis / on exception | **MEDIUM** | CARRIED | `rate_limit.py:157-159, 207-211`. |
| CSRF helpers never wired | **MEDIUM** | CARRIED | `security.py:138/142`; mitigated by SameSite=Lax + same-origin mount. |
| tutor.html refresh-token divergence (rotated refresh not persisted) | **MEDIUM→LOW (pre-existing)** | CARRIED | `frontend/tutor.html:174-197` stores access only. |
| upload.html:372-375 raw interpolation of server-sourced id/ints | **LOW** | CARRIED | Server-sourced identifiers only; no free-text vector found. |
| `.env` real-looking secrets | LOW | CARRIED | gitignored + untracked; local only. |
| Stored HTML/SVG XSS | — | **ALREADY-FIXED domain** | No backend API returns stored HTML/SVG; frontend builds SVG/HTML via `escHtml`/`escSvg`. |

No CRITICAL finding verified this pass. **No P15-scoped security work is forced**; P15 adds one new learner-scoped write endpoint (session position) that must mirror the audit's ownership conventions (C3 check).

---

## 10. PostgreSQL / Migration Audit

- **P14 data (JSONB) PG-correct:** `review_metadata` is `JSON().with_variant(JSONB(), "postgresql")` (`review_schedule.py:84-86`); outcomes round-trip on the real engine (`test_p14_retention_pg.py`).
- **Alembic:** single linear chain `0001..0033`, single head `0033_educational_memories`. P14 added nothing.
- **`learning_sessions` (P15 surface) fully migrated:** created at `0009`, columns incl. `current_slide_position`, `current_block_position`, `completion_percentage`, `resume_version`, `client_metadata` (JSONB), plus `ix_learning_sessions_user_*` indexes and `uq_learning_sessions_user_idempotency`. `user_id` FK → users; `lesson_id` FK → generated_lessons (CASCADE). Verified present in migrations (`0009:57-101`).
- **ORM ↔ migration parity:** `app/models/learning_session.py` matches `0009` columns exactly.
- **N+1 / bounded reads:** progress read = single join (`learner_progress_service.py:144-190`); session lookup = indexed `user_id+lesson_id` ordered `updated_at desc limit 1` (`learning_session_service.py:65-75`).
- **Concurrency/uniqueness:** per `(user_id, idempotency_key)` unique; resume is a single-row UPDATE.
- **Conclusion:** P15 needs **no migration**. New writes target an existing, indexed, migrated row.

---

## 11. Performance Audit

| Finding | Sev | Status | Evidence |
|---|---|---|---|
| Sync FFmpeg render in async handler | HIGH | CARRIED | `video_renderer_service.py:119+`; blocks event loop seconds–minutes. **Not P15** (perf-gated feature). |
| `effectiveness_service` unbounded `.all()` reads | MEDIUM | CARRIED | `:284-288`, `:324-339`, `:457` full user/group scans. |
| Review `_ensure_schedules` `list_due(limit=10000)` | LOW | CARRIED | `review_schedule_service.py:267` on read path. |
| 8/9 stale rate-limit patterns | MEDIUM | CARRIED | `config.py:375-385`; expensive AI endpoints unbudgeted (fall back to generic 100/60). |
| Player/start + session writes | — | VERIFIED-OK | bounded: 1 session row read/write, single indexed lookup. |
| P15 resume read path | — | VERIFIED design | dashboard progress already single-join; resume writes <=1 UPDATE, debounced client-side. |

---

## 12. Frontend Audit

See companion audit (2-subagent pass, evidence quoted). Highlights:

1. **Navigation dead-ends:** `upload.html` (post-login hub) → no Dashboard/Tutor link (`upload.html:103-106`); player final slide → no completion CTA (`player.html:262-266`); player → no sign-out; processing failure → no retry (`processing.html:171-177`).
2. **Resume broken:** `player.html` ignores `session.topic_index` (`:339-362`, `:370-374`); no `?slide=` written; dashboard resume copy without resume behavior (`dashboard.html:332-338`).
3. **Escaping:** thorough — `escHtml`/`escSvg` on all user-visible dynamic content; `insertAdjacentHTML` only in tutor.html and always escaped. Residual raw interpolations are server-sourced ids/numbers (LOW).
4. **States:** loading/error/empty states strong on dashboard; player/tutor/upload adequate.
5. **Auth:** `authFetch` refresh mirrors correctly on all pages except tutor.html (rotated refresh_token not persisted — LOW, carried).
6. **Dead code:** `?deck=` in player.html:316 never consumed; `assets/app.js`/`style.css` orphaned (no page references them).

---

## 13. Browser / E2E Audit

- **21 tests / 10 files**, Playwright + system Chrome against a real uvicorn server + fresh SQLite: smoke, learner-journey, P6 full loop, P7 dashboard, P8 tutor, P10 NG-1/2/3, P11 plans/goals/path, P12 adaptive A/B, P13 analytics, P14 retention. Stable this pass (reproduced 21/21 after the P14 full-suite run).
- **Isolation coverage:** two-user suites across review, analytics, retention, plans/path, tutor, assessment — all green.
- **Journey gaps (P15-relevant):** no resume journey; no upload→processing→player ability to **verify position persistence**; no browser check of the dashboard's "resume" deep-link.
- E2E seeding patterns established (`test_p12_adaptive_e2e.py`, `test_p14_retention_e2e.py`) — reusable for the P15 resume journey.

---

## 14. AI / RAG Audit

- P14 added zero AI: outcome→step + retention signal are pure deterministic helpers (`retention.py`); no provider on any path.
- **Mandatory AI seam respected:** all provider access remains behind `AIContentService`/`app.ai.service.get_ai_content_service()`; no feature code calls providers directly (verified pattern in prior audits, unchanged).
- **Tutor:** learner-owned context, semantic RAG with ownership filtering, bounded retrieval/history, deterministic fallback, session resume. Prompt-injection guard knob dead (CARRIED, §9).
- **RAG fusion:** `TUTOR_RETRIEVAL_MMR_LAMBDA`/`TUTOR_RETRIEVAL_RRF_K` inert (deferred).
- **P15:** no AI required; adding none.

---

## 15. Deferred Capability Review

1. **Video Learning Runtime** — partial/dead surfaces + sync render blocks the event loop (HIGH). Value capped until render is off the loop; infrastructure decision with real risk; E2E video is flaky. **Defer.**
2. **Adaptive Assessment 2.0 (inter-attempt/IRT/elo)** — extends a just-stabilized invariant; complexity high; browser value moderate. **Defer.**
3. **Tutor / RAG 2.0** — AI-heavy; tutor already functional; injection-guard debt first. **Defer.**
4. **Mastery / Retention Intelligence** — retention current-state delivered (P14); mastery scalar is quiz-owned by design; decay-as-rewrite deliberately avoided. Trend-line (defer §16). **Defer.**
5. **Learner Analytics** — depth/export are diminishing returns after P13/P14. **Defer.**
6. **Learning Plans / Goals / Paths** — complete (P11). **No gap.**
7. **Production Reliability / Hardening** — carried MED topics + one latent MED (analytics tables). Platform work with no directly-observed learner capability; the active learner gap (resume) ranks higher. **Defer (fold only the small, loop-scoped items into P15).**
8. **Content Intelligence** — not an active learner-journey break. **Defer.**
9. **Learning Workspace (bookmarks/notes save-surface)** — migration 0009 already creates bookmark/note tables, but it is a **new** capability, not a broken transition; no learner-facing need proven this pass. **Defer.**
10. **Review Automation (retention nudges/beat)** — requires functional Redis/Celery integration test first (explicit prereq, still missing). **Defer.**
11. **New discovery with strongest evidence — Learner Continuity / Resume.** Broken UI promise, idle backend foundation, closes the last loop transition. **Select as P15.**

---

## 16. Candidate Scoring (evidence-based)

Scoring model: each candidate scored 1–5 per dimension (5 = best). Weights per the P15 mandate. For **AI risk** and **Complexity**, a higher score means LOWER risk/complexity. Max weighted total = 100.

**Candidates**
- **A — Persistent lesson resume + coherent navigation loop** (player restores saved position; slide-position persistence; dashboard resume deep-links; post-login hub + player completion CTA).
- **B — Retention trend-line** (retention over time chart on P14 history).
- **C — Video runtime completion + render offload.**
- **D — Performance/scale + platform hardening** (rate-limit config, `effectiveness` `.all()`, analytics-table migration gap, video offload).
- **E — RAG fusion + Tutor 2.0.**
- **F — Adaptive Assessment 2.0 (inter-attempt/IRT).**
- **G — Mastery decay persistence (separate metric).**
- **H — Deeper analytics / export.**
- **I — Learning workspace (bookmarks/notes).**

| Dim (wt) | A | B | C | D | E | F | G | H | I |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Learner value (15) | 4 | 3 | 3 | 1 | 3 | 3 | 2 | 2 | 3 |
| Product impact (12) | 4 | 3 | 3 | 2 | 3 | 3 | 2 | 2 | 3 |
| Gap severity (12) | 4 | 3 | 4 | 3 | 3 | 3 | 2 | 2 | 3 |
| Architecture readiness (10) | 5 | 5 | 2 | 4 | 4 | 3 | 3 | 4 | 2 |
| Existing data reuse (10) | 5 | 5 | 2 | 4 | 4 | 4 | 4 | 4 | 2 |
| Product-loop closure (10) | 5 | 3 | 1 | 1 | 2 | 3 | 3 | 2 | 2 |
| Browser verifiability (8) | 5 | 4 | 2 | 1 | 3 | 3 | 3 | 2 | 4 |
| Production readiness (8) | 5 | 5 | 2 | 3 | 4 | 3 | 3 | 3 | 4 |
| Security feasibility (5) | 5 | 5 | 3 | 3 | 3 | 4 | 5 | 4 | 4 |
| Performance feasibility (5) | 5 | 4 | 2 | 4 | 3 | 4 | 4 | 3 | 4 |
| AI risk (3) | 5 | 5 | 4 | 5 | 1 | 4 | 5 | 5 | 5 |
| Complexity (2) | 4 | 4 | 1 | 3 | 2 | 2 | 3 | 3 | 3 |
| **Weighted** | **459** | **387** | **250** | **253** | **310** | **321** | **292** | **274** | **302** |

**Ranked:** **A (459)** > B (387) > F (321) > E (310) > I (302) > G (292) > H (274) > D (253) > C (250).

**Score rationale (A):**
- Learner value 4 — returning learners resume mid-course instead of restating; the promise on the sign-in page becomes true.
- Gap severity 4 — the only *broken* learner-facing transition left in the spine; evidence-backed in this audit and the P13 frontend pass.
- Readiness/reuse 5/5 — `learning_sessions` schema + `LearningSessionService` + `LessonPlayerService.start` already persist position; only wiring + a slide-position write + frontend consumption is missing. No migration.
- Loop closure 5 — directly closes transition #17 (Resume/return) and fixes the post-login hub dead-end (navigation loop).
- Security 5 / Performance 5 — learner-scoped via existing ownership; ≤1 UPDATE + single indexed read; no AI.

---

## 17. Selected P15

**P15 — Persistent Lesson Resume & Learner Continuity ("Pick up where you left off"):**
> *When a learner leaves a lesson and returns, the platform restores them to the slide where they stopped — from any entry point (dashboard, deep-link, cold reload) — and the dashboard/navigation surfaces make resuming the obvious next step.*

It is the only candidate that fixes a **broken transition in the connected spine** (return-to-learning) rather than extending a complete surface. It is deterministic (zero AI), learner-scoped, fully supported by the existing schema (no migration), reusable from existing services, browser-verifiable with a real journey (position → leave → resume → refresh persistence + User A/B isolation), and it delivers on an explicit UI promise. Full contract in `P15_SCOPE_AND_FOUNDATION.md`.

**Why the top alternatives are NOT P15 now:**
- **B (retention trend-line)** — extends the just-shipped P14 measure surface; nothing is broken; right-sized follow-up, not a phase.
- **F/E/I** — adaptive-2.0 (mutates stabilized invariants), tutor/RAG-2.0 (AI-heavy, injection-guard debt first), workspace (new capability with no proven journey break).
- **D/C** — platform hardening and video offload are real but deliver no directly-observed learner capability; the highest-leverage one (video offload) is a separate infra decision.

---

## 18. P15 Risks

| Risk | Mitigation |
|---|---|
| Slide-position writes race with navigation | Debounced client-side sync (existing `syncTopic` pattern); single-row UPDATE; ownership-scoped lookup returns None for foreign users |
| Resume deep-link drift vs topic count | Server persists slide index that is clamped to lesson version at read (`set_position` clamps to total); deep-link uses `?slide=` persisted server-side |
| Player version changed between visits | Resume position clamps to `slides.length`; out-of-range falls back to slide 0 (existing `startIndexFromUrl` behavior) |
| Breaks existing player/E2E flows | Resume only activates when server provides a session position; `?slide=` override retained; full browser suite re-run |
| No schema change | `learning_sessions` (migration 0009) already carries `current_slide_position`/`current_block_position`/`resume_version` |

---

## 19. P15 Implementation Checkpoints

| Chk | Objective |
|---|---|
| C0 | Baseline re-verify (SQLite 1295 / PG 30 / E2E 21, mypy 83/24, head 0033, ruff clean) — **done this pass** |
| C1 | Foundation: `LearningSessionService.set_position` + `slide_index` in session payload + schema additive fields |
| C2 | API: `POST /lessons/{lesson_id}/player/position` (learner-scoped, 404-equalized); dashboard `LessonProgressItem` resume fields + server-built deep-link |
| C3 | Security: cross-user set/read → 404-equivalent no-write; unauth 401; malformed/out-of-range positions bounded |
| C4 | PostgreSQL: resume read/write on migrated `learning_sessions`; single-head + ORM parity guard |
| C5 | Frontend: player resume from session (or `?slide=`), slide sync via `/position`, final-slide CTA + sign-out, dashboard resume deep-links, upload hub dashboard link |
| C6 | Integration: player ↔ session-table ↔ dashboard ↔ navigation loop |
| C7 | Browser E2E: real resume journey + refresh persistence + User A/B isolation |
| C8 | Performance/observability: bounded writes, no N+1, metrics (optional P15 counter), logs |
| C9 | Full release regression + docs + commit |

---

## 20. Audit Conclusion

P14 is **VERIFIED** end-to-end: review-loop closure confirmed from source and gate numbers (SQLite 1295, PG 30, E2E 21, Ruff clean, mypy 83/24, single head `0033`, secret scan clean, clean tree). No new security finding is introduced by P14.

Product-wise, the whole spine is now adaptive and learner-visible. The audit's clearest empirical finding is the **broken Resume/Return transition**: the product promises "pick up where you left off" and the server already persists position, but the frontend ignores it — every return visit restarts the lesson, and the post-login hub dead-ends. That gap is fully solvable with existing schema + a deterministic design and is browser-verifiable. **P15 = Persistent Lesson Resume & Learner Continuity.** Full foundation in **`P15_SCOPE_AND_FOUNDATION.md`**. The video render risk and the carried security findings are documented (not silently ignored): video is a known perf/feature block deferred to its own architected push; the security items remain scoped/documented with their HTML evidence. NO P15 implementation is performed in this phase.