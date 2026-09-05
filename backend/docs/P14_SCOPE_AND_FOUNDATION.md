# P14 Scope & Foundation — Retention & Review Automation ("Close the review loop")

**Status:** PLANNING (audit phase — NO implementation)
**Authoritative implementation contract for P14.**
**Branch target:** `feature/individual-user-foundation`
**Parent of P14:** Post-P13 audit at HEAD `c191d44` (this doc + `POST_P13_PRODUCT_ARCHITECTURE_AUDIT.md`)
**Type:** Feature phase — implementation occurs ONLY after this doc is approved.

---

## 1. Executive Summary

P13 gave the learner the **measure** of their learning (trajectory, concepts, effort). P14 closes the last broken transition in the connected learning spine: the **review/retention leg**. Today a review is a pure clock reset — completing it captures **no recall outcome**, failure never shortens the interval, decay pressure is computed but never persisted, and the dashboard surfaces **no retention signal**. The learner cannot see whether they are actually retaining what they learned, and the system's only learner input is ignored.

P14 makes reviews **outcome-driven** (the learner records how well they recalled: again / hard / good / easy), adapts the spaced interval deterministically from that outcome, persists the outcome history in existing JSONB, derives a deterministic **retention signal** per concept, and shows retention on the dashboard and in the review queue — all **deterministic, learner-scoped, browser-verified, zero new tables, zero AI**.

---

## 2. Problem Statement

> "I review a concept and click 'complete'. The system just shows 'next review in 7 days'. If I actually struggled, nothing changes. And I can't tell — anywhere on the dashboard — whether I'm really retaining the material or slowly forgetting it."

Verified facts (Post-P13 audit §9):
- `ReviewScheduleService.complete` (`review_schedule_service.py:113-183`) takes **no outcome**; it always advances `next_interval(step)` on the pure 1/3/7/14 ladder and resets the clock. Docstring: *"The routine does not change mastery; it resets the review clock"* (L122-123), *"no mastery rewrite"* (L167).
- `compute_decay_signal` (`review_scheduler.py:82-115`) is pure and **persists nothing**; it only annotates queue priority.
- `celery_app.py:69-106` beat has **no retention, decay, or scheduling task**.
- The dashboard and review queue expose **no retention/recall signal** (gap #1 in the Post-P13 audit, §13).

The result: the only stage of the learning loop that *should* measure long-term memory — review — neither measures it nor adapts to it.

---

## 3. Current-State Evidence (all verified this pass)

| # | Evidence | Source |
|---|---|---|
| 1 | `complete()` has no recall-outcome input; ladder always advances | `review_schedule_service.py:113-183` |
| 2 | Mastery scalar is written only on quiz submission — an invariant to preserve | `educational_memory_service.update_concept_mastery` |
| 3 | `review_metadata` JSONB already carries `step`/`last_pressure`/`skipped_at` — a proven persistence surface, portable across SQLite/PG | `app/models/review_schedule.py:84-86` |
| 4 | `educational_memories.memory_data` JSONB (migration 0033) — existing record surface | `app/models/educational_memory.py` |
| 5 | Queue item already carries `review_count` + `priority`; learner-scoped, 404-equalized | `review_schedule_service.py:287-319`; `review.py` |
| 6 | Review isolation suite exists (6 tests) to extend for outcome isolation | `tests/integration/test_review_api_security.py` |
| 7 | Analytics read-composition + dashboard panels (P13) are the natural retention surface | `learner_analytics_service.py`, `dashboard.html` |
| 8 | No migration needed for the MVP (JSONB is free-form); single head `0033` preserved | `alembic heads` |
| 9 | No functional Redis/Celery broker test exists (mocks only) → no beat task in MVP | Post-P13 audit §10 |

---

## 4. Product Objective (ONE primary outcome)

**When a learner completes a review, the platform captures whether they actually recalled the concept, adapts the spacing deterministically from that outcome, persists the outcome history, and shows the learner their retention over time.**

Everything in P14 directly serves that outcome. Nothing else.

---

## 5. Learner Outcome

After P14 the learner can:
- **Record how a review went** (Again / Hard / Good / Easy) in one click from the review queue.
- **See the consequence:** forgetting (Again) resets the interval to 1 day; Easy skips ahead (bounded); the next-due date and priority react immediately.
- **See their retention** on the dashboard and the review queue: per-concept status (`on_track` / `at_risk` / `overdue` / `new`), retained strength (0–100), self-reported recall accuracy, and days since last review.
- **Trust that mastery is untouched by review** — the score they earned on checkpoints stays canonical; retention is a separate, honest signal.

---

## 6. Exact P14 MVP

**D1-A — Outcome-driven review completion.**
`POST /me/review/{schedule_id}/complete` gains an **optional** body shape `{"outcome": "again"|"hard"|"good"|"easy"}` with **default `good`** (so every existing caller — E2E, isolation tests, legacy UI — produces today's exact behavior). Deterministic outcome→step mapping:
- `again` → step 0 (interval 1 day), lapse recorded
- `hard` → step unchanged (same interval)
- `good` → step + 1 (current behavior; the default path)
- `easy` → min(step + 2, MAX_STEP)

Outcome history (capped at the last 20) and per-outcome counts persist in `review_metadata` JSONB — **no new table, no migration**.

**D1-B — Deterministic retention signal + aggregation.**
New pure module `retention.py` (mirrors `learner_analytics.py` style): `retention_signal({mastery, days_since_review, due, outcome_history})` → `retained_strength` (0–100) + `status` (`on_track|at_risk|overdue|new`), and `review_accuracy(history)` = share of good+easy. Multiple units of the round: determinism, monotonic rules (e.g. lapses lower strength; time since review decays strength; due + unreviewed → overdue).

**D1-C — Learner-visible retention surface.**
- New endpoint `GET /me/analytics/retention` → per-concept retention snapshot (≤100) + a summary (`retention_average`, `at_risk_count`, `overdue_count`), each concept carrying practice/tutor deep-links (server-built, same pattern as P13).
- `GET /me/review` queue items gain additive fields `retention_status` + `review_accuracy` (backward compatible).
- Dashboard gains a **Retention** panel (on-track/at-risk/overdue chips + recall accuracy + empty state) reusing the P13 analytics panel pattern and `escHtml`.

**D1-D — Review queue UI outcome picker.**
When completing a review the learner picks Again/Hard/Good/Easy (default Good if they simply finish) — the real browser action that makes the loop real.

**D1-E (hardening, small)** — keep the review flow idempotent and the JSONB writes bounded (history cap 20; metadata schema versioned `"v": 2`).

**Explicitly NOT in MVP:** a retention Celery beat task (no functional broker test exists — kept lazy like today, documented in §27), mastery-scalar rewriting on review (invariant), adaptive-2.0, tutor/RAG, video, analytics trend-line extension (deferred §27).

---

## 7. User Journeys

**Primary (browser-verified):** sign in → dashboard shows a weak concept's review due + retention status `overdue` → review queue opens → item shows recall accuracy ("57% recalled · 6 reviews") → learner presses **Review** → lesson player opens → back in queue → learner marks **Again** (they struggled) → server resets interval to 1 day, records lapse, retention status flips to `at_risk` → dashboard Retention panel updates → **page refresh** → state identical (persistence) → next-due date and priority reflected.

**Secondary:** learner marks **Good/Easy** repeatedly → interval advances 1→3→7→14 (bounded), accuracy climbs, status `on_track` → mastery scalar unchanged throughout.

**Isolation:** User A completes With outcome; User B that does the same on A's schedule id → **404**; User B's dashboard shows only B's (empty) retention.

**Backward-compat:** legacy UI/E2E that calls `complete` with no body behaves exactly as today (default `good` = the old `next_interval(step)` path).

---

## 8. Backend Architecture

Additive, read-compose-first:
- `app/services/retention.py` — **pure** deterministic logic (no DB, no AI): outcome→step mapping, ladder interaction (`initial_step`/`interval_at_step`/`next_step`/`next_interval`/MAX_STEP reused from `review_scheduler.py`), `retention_signal`, `review_accuracy`, history capping, response bucketing. Everything unit-testable in isolation.
- `app/services/review_schedule_service.py` — extend `complete(user_id, schedule_public_id, *, outcome)`; persist outcome history + counts into `review_metadata`; keep the mastered@max-interval auto-complete path; **never** call `update_concept_mastery`.
- `app/services/learner_analytics_service.py` + `app/api/v1/analytics.py` — add `get_retention` read-composition over `review_schedules` + `educational_memories` + concept deep-links (bounded, learner-scoped, cache-backed mastery via `educational_memory_service`).
- `app/schemas/review.py` / `app/schemas/learner_analytics.py` — additive response fields (`retention_status`, `review_accuracy`, `retention` response model); new `ReviewOutcome` enum with default good.
- `app/api/v1/review.py` — `complete` accepts the optional body (`ReviewCompleteIn`).
- `app/observability/metrics.py` — `p14_review_outcomes_total{outcome}`, `p14_retention_views_total{endpoint}`.
- Frontend: `dashboard.html` Retention panel; `review` queue outcomes rendered in dashboard's review panel (the review queue lives on the dashboard).

UoW/repository pattern unchanged; ownership via `get_by_user_and_public_id` (404).

---

## 9. API Design (additive, backward compatible)

- `POST /me/review/{schedule_id}/complete`
  - Request (optional): `{ "outcome": "again" | "hard" | "good" | "easy" }` — default `good`; unknown value → 422.
  - Response: existing `ReviewCompleteResponse` fields unchanged **plus** `outcome`, `retained_strength` (float|null), `review_accuracy` (float|null).
- `GET /me/analytics/retention`
  - Response: `{ summary: { retention_average: float|null, on_track_count, at_risk_count, overdue_count, new_count: int }, concepts: [ { concept_public_id, name, band, mastery_score, retained_strength, status, due_at, days_since_review, review_count, review_accuracy, deep_link_practice, deep_link_tutor } ], max: 100 }`.
- `GET /me/review` — queue items add `retention_status` (`on_track|at_risk|overdue|new|completed`) and `review_accuracy` (float|null). No existing field changes.

No endpoint is removed; no other endpoint's contract changes.

---

## 10. Service Boundaries

| Service | Responsibility |
|---|---|
| `review_scheduler` (existing) | ladder: `initial_step`, `interval_at_step`, `next_step`, `next_interval`, MAX_STEP (reused unchanged) |
| `retention` (NEW, pure) | outcome→step mapping, `retention_signal`, `review_accuracy`, history capping, buckets |
| `review_schedule_service` (extended) | persists outcomes/history in `review_metadata`; deterministic ladder application; 404 ownership; no-mastery-write invariant |
| `learner_analytics_service` (extended) | `get_retention` read-composition; bounded, learner-scoped, deep-link building |
| `educational_memory_service` (existing) | mastery source + cache for retention derivation (unchanged, read-only in P14) |

---

## 11. Existing Components Reused

`review_schedules` (+ JSONB `review_metadata`) · `educational_memories`(+ `memory_data`, bands, `record_review_activity`) · `review_scheduler` ladder + `compute_decay_signal` · `ReviewScheduleService.complete/skip` + 404 ownership · `learner_analytics_service` + P13 `escHtml` panel pattern · dashboard Review panel + `authFetch` · `tests/integration/test_review_api_security.py` + `tests/e2e/test_p10_adaptive_review_e2e.py` infrastructure · `observability/metrics.py` pattern. **No new provider, no new infra, no new table.**

---

## 12. Frontend Architecture

Vanilla `backend/frontend/` only (no framework migration):
- **Dashboard Review panel** (`dashboard.html`): each queue item renders outcome buttons — **Again / Hard / Good / Easy** — one primary (Good by default) → `complete` with outcome → re-fetch queue + retention. Shows `retention_status` chip + recall accuracy.
- **Dashboard Retention panel** (`dashboard.html`): summary chips (On track / At risk / Overdue) + per-concept rows (status, retained strength, accuracy, days since review, Practice/Ask-tutor deep-links). Empty state: "Review a concept to start seeing how well you retain it."
- All dynamic content `escHtml`-escaped; server-built deep-links only; loading skeleton + error handling per existing pattern.

---

## 13. Database Impact

**No new table. No migration in the MVP.** Outcome history and counts persist in the existing portable `review_metadata` JSONB (`review_schedule.py:84-86`, `JSON().with_variant(JSONB(), "postgresql")`), versioned `"v": 2`; the retention **signal** is derived deterministically from persisted facts (outcomes, mastery, due_at) at read time — read-composition, not a new write column. Bounded growth: history capped at 20 entries per schedule; counts fixed-size.

**Optional additive migration (documented, NOT created now):** if profiling of `GET /me/analytics/retention` aggregation on realistic volumes justifies it, the smallest additive change is an index on `review_schedules(user_id, due_at)` — note `ix_review_schedules_user_due` already covers `(user_id, due_at)`; a candidate would instead be `(user_id, status)`. Decide only with measured evidence; keep single head `0033`.

---

## 14. Migration Plan

None required. If the optional index (§13) is ever justified by profiling: one additive Alembic revision `0034_*` with an existence guard, single head preserved (0033 → 0034), reversible via `alembic downgrade -1`, SQLite-incompatible index ops avoided (plain composite index is portable). Otherwise head stays `0033_educational_memories`.

---

## 15. Security Model

- Outcome enum validated by Pydantic; unknown → 422; body size trivially bounded.
- `complete` continues resolving the schedule via `get_by_user_and_public_id(user_id, schedule_public_id)` → **cross-user 404** (no change to the isolation invariant).
- `GET /me/analytics/retention` learner-scoped from `get_current_user` only; no client identifiers; B sees empty own-only aggregation.
- New isolation tests: unauth 401 (complete + retention), cross-user complete → 404, cross-user retention read → B empty, invalid outcome → 422, at most zero rows mutated for the wrong user.
- No new secrets; no rate-limit change required beyond confirming the existing global default covers `/me/analytics/retention`.
- Frontend: `escHtml` on all new dynamic content; server-built links only.

---

## 16. Performance Model

- `complete`: +1 UPDATE on the schedule row (JSONB metadata), reads memory via the existing cache; bounded history (≤20).
- `GET /me/analytics/retention`: learner-scoped, bounded ≤100 concepts; reuses `ix_review_schedules_user_due`; mastery reads cache-backed; no N+1 (single batched schedule→concept resolution like `concepts`); deterministic ordering `(status_bucket, -retained_strength, concept_public_id)`.
- Queue listing: existing bounded path (≤ `MAX_DUE_LIMIT=200` internal scan) + additive fields, no extra queries.
- No unbounded in-memory growth; retention derivation is O(history) per concept (≤20).

---

## 17. Observability

- `p14_review_outcomes_total{outcome}` on every complete-with-outcome.
- `p14_retention_views_total{endpoint, outcome="ok"}` + `p14_retention_errors_total{reason}` on the retention endpoint.
- Exposed via existing `GET /api/v1/metrics`; no learner PII in labels.

---

## 18. Test Strategy

- **UNIT (pure `retention.py` + `review_scheduler` interaction):** outcome→step mapping (again→0, hard→same, good→+1, easy→+2 capped); default-good = identical to the current `next_interval(step)` path; determinism (same inputs → same outputs); `retention_signal` thresholds, lapse decay, overdue rule; `review_accuracy` edge cases (empty history → null, all-again → 0); history capping at 20; bounded/None mastery handling.
- **INTEGRATION:** `complete` with each outcome persists metadata + changes interval (again resets to 1d, hard keeps, easy skips ahead capped); no-body call reproduces today's exact interval/status (backward-compat regression); `update_concept_mastery` is **never** called by review (assert mastery scalar unchanged after Any outcome — the invariant test); retention endpoint aggregation matches seeded schedule/memory rows; bounded window / 422 unknown outcome / 404 cross-user / 401; metrics counters appear.
- **POSTGRES:** review-outcome JSONB persists and round-trips on the migrated schema (head `0033`); retention aggregation returns correct sums/averages; migration-head guard (P13 pattern); cross-user 404 on PG.

**Convention:** one explicit two-user isolation scenario for every new learner-resource surface (complete and retention) — User B must get neither data nor side effects.

---

## 19. Browser E2E Strategy

New/extended `tests/e2e/` (Playwright + system Chrome, real sign-in, live vanilla SPA on SQLite):
1. Seed learner with a weak concept + a due review schedule (step = 1, interval 3d) and a second concept already reviewed (history incl. hard/good).
2. Sign in → dashboard: assert Retention panel chips and per-concept status; assert Review queue shows retention_status + accuracy.
3. Complete the due review in the **browser** picking **Again** → assert queue re-fetch shows next-due in 1 day, outcome counted, status `at_risk`; refresh the page and assert identical persisted state.
4. Complete the other concept with **Easy** → assert interval skips (bounded), status `on_track`; **mastery scalar read-back unchanged** (invariant asserted in-browser too).
5. **User B isolation flow:** B signs in, calls `complete` on A's schedule id → 404; B's retention panel shows only B's empty state.

This is a complete browser learner journey: sign in → enter feature → real learner action (outcome) → persisted state verified → navigate to resulting action (dashboard panel) → refresh → state correct → ownership isolation.

---

## 20. PostgreSQL Verification Strategy

- New `tests/postgres/test_p14_retention_pg.py`: (1) outcome JSONB persistence round-trip on migrated PG; (2) retention aggregation over seeded schedules (sums/counts/accuracy) on the real engine; (3) cross-user complete → 404 on PG; (4) `alembic heads` single `0033` guard (P13 pattern). Full PG suite must stay ≥ 25 passed (+ new tests).

---

## 21. Rollback Strategy

- No migration in MVP → nothing to downgrade. If the optional index is added, it is one additive reversible revision.
- All API changes additive/backward-compatible: revert = stop honoring the outcome body (default good reproduces today's behavior exactly) and drop the retention route mount + panel.
- JSONB additions are data-only and inert until read (no destructive rewrite of `review_metadata`; `"v": 2` written atomically with `complete`).
- Checkpoint-by-checkpoint revert = revert the last checkpoint commit; P0–P13 files untouched except the documented additive edits to `review_schedule_service`/`analytics`/`dashboard.html`.

---

## 22. Explicit Exclusions (OUT OF SCOPE)

- NO rewrite of the quiz-owned mastery scalar on review (invariant preserved with an explicit regression test).
- NO retention Celery beat / push notifications / email (no functional broker test exists; lazy seeding preserved).
- NO AI/LLM retention insights; NO ML; NO elo/IRT.
- NO framework migration; NO new infra; NO vector-DB; NO Redis/Celery functional-test work in this phase.
- NO tutor/RAG changes; NO video/animation/simulation work; NO adaptive-2.0.
- NO retention *trend-line* (only current status + accuracy in MVP; trend extension deferred).
- NO teacher/classroom/parent surfaces; NO new export; NO unrelated cleanup/refactors.

---

## 23. Risks

| Risk | Mitigation |
|---|---|
| Review path mutates the quiz-owned mastery invariant | Retention signal is separate; `complete` never calls `update_concept_mastery`; invariant regression test asserts zero mastery change across all outcomes |
| Backward-compat break for `complete` | Outcome body optional, default `good` == today's `next_interval(step)` path exactly; existing E2E/isolation tests re-run unchanged |
| JSONB metadata growth / shape drift | History capped at 20, fixed-size counts, `"v": 2` version stamp; read code tolerant of `"v": absent` (pre-P14 rows) |
| Retention aggregation slow on many schedules | Learner-scoped + ≤100 concepts + existing `(user_id, due_at)` index; optional index only by measured need (§13/§14) |
| Scope creep (beat task, trend-line, mastery rewrite, analytics depth) | Explicit exclusions §22; single primary outcome §4 |
| Outcome self-report unreliability | Labeled "self-reported recall" in UI; deterministic and transparent, not hidden |

---

## 24. Acceptance Criteria

- Completing a review with `again` resets a non-zero interval to 1 day; `good` reproduces today's behavior exactly; `easy` advances but never beyond MAX_STEP; `hard` holds the interval. All unit- and integration-verified.
- `review_metadata` stores under `"v":2` a capped history (≤20) + per-outcome counts, round-trips on SQLite and migrated PostgreSQL.
- `GET /me/analytics/retention` returns a correct, bounded, learner-scoped snapshot; cross-user → empty/404; unauth → 401.
- Mastery scalar (and NG-3 loop) unchanged by any review action — explicit test.
- Dashboard shows the Retention panel (status chips + accuracy + deep-links + empty state) and the Review panel's outcome buttons; all new content `escHtml`.
- Full browser E2E journey passes including the A/B isolation flow and refresh-persistence.
- Post-P14 gates hold: SQLite ≥ 1213 passed (0 failed), PG ≥ 25 passed (+ new), E2E ≥ 18 passed (+ journey), Ruff clean, mypy ≤ 83/24 (zero new; no new modules beyond the approved boundary), single Alembic head `0033`, secret scan clean, `git diff --check` clean, tree clean.

---

## 25. Checkpoint Implementation Plan

| Chk | Objective | Files expected | Tests | Acceptance |
|---|---|---|---|---|
| C0 | Baseline / contract re-verify (P13 gates: 1213 / 25 / 18, mypy 83/24, head 0033) | none | full regression | gates green |
| C1 | Pure `retention.py` (outcome→step mapping, ladder interaction, retention_signal, accuracy, capping) + unit tests | `app/services/retention.py`, `tests/unit/test_retention_service.py` | unit | deterministic, bounded, default-good == legacy path |
| C2 | Service: `complete(outcome)` persistence + no-mastery invariant; queue item enrichment | `review_schedule_service.py`, `schemas/review.py` | integration + security | outcomes persist, cross-user 404, mastery unchanged |
| C3 | `GET /me/analytics/retention` + metrics | `learner_analytics_service.py`, `analytics.py`, `schemas/learner_analytics.py`, `metrics.py` | integration + security | correct aggregates, scoped, bounded, counters |
| C4 | PostgreSQL behavioral suite | `tests/postgres/test_p14_retention_pg.py` | PG | JSONB round-trip + aggregation + 404 + head guard |
| C5 | Frontend: review outcome buttons + Retention panel | `frontend/dashboard.html` | — | escaped, deep-linked, empty state |
| C6 | Browser E2E journey + isolation | `tests/e2e/test_p14_retention_e2e.py` | E2E | full journey + A/B + refresh persistence |
| C7 | Full regression (SQLite/PG/E2E/ruff/mypy/alembic) + record | — | all | contract green |
| C8 | Implementation report + clean tree | `P14_IMPLEMENTATION_REPORT.md` | — | final, no P14 commit until gate green |

---

## 26. Release Gate (P14 must hold; use P13 baselines)

- SQLite: ≥ **1213** passed, 0 failed.
- PostgreSQL: ≥ **25** passed plus the new retention behavioral suite green.
- Browser E2E: ≥ **18** passed plus the new retention journey + A/B isolation green.
- Ruff: clean (whole repo). Mypy: ≤ **83 errors / 24 files**, zero new.
- Alembic: **single head `0033`** (or `0034_*` only if the optional index is justified by measured need), import/`upgrade head` clean.
- Secret scan clean; `git diff --check` clean; working tree clean.
- User isolation preserved: cross-user review-complete and retention → 404/empty; unauth → 401.
- Mastery scalar unchanged by review actions (invariant test green).
- `p14_*` observability present. No AI/RAG changes. Zero new tables; optional additive index only if profiled.
- P14 work is committed only after the gate passes and the report is written.

---

## 27. Deferred Follow-Ups

1. **Retention trend-line** (`GET /me/analytics/retention` over time as a chart) — natural post-MVP extension on the same persisted history.
2. **Retention beat / proactive nudges** — requires a functional Redis/Celery integration test first (explicit prerequisite).
3. **Interval outcomes → mastery-aware assessment** (failed reviews feed the adaptive start difficulty) — crosses into adaptive-2.0; delayed.
4. **Mastery decay as a persisted, separately-defined metric** (NOT the quiz-owned scalar) — chain on the P14 retention signal.
5. **Upload → processing → player browser journey** (E2E gap unrelated to P14 core; fold in opportunistically).
6. **tutor.html refresh-token divergence fix** (LOW, pre-existing frontend bug — fold into any frontend touch).
7. **Video render offload + `/videos/runtime` wiring** — remains deferred (perf-gated feature push).

---

**Definition of Done:** the learner can record a recall outcome per review, the spacing reacts deterministically (again→1d reset, easy→bounded skip-ahead, good→today's ladder, hard→hold), the outcome history is persisted in existing JSONB, the dashboard and review queue surface a deterministic per-concept retention signal (status + strength + accuracy) with deep-links and empty states, mastery stays quiz-owned, all four test pillars (unit/integration/PG/E2E) go green on the P14 journey plus isolation, all release-gate baselines hold, tree is clean, and the P14 implementation report is written before any P14 commit.