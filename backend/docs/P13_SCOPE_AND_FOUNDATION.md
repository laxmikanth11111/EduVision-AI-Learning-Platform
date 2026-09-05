# P13 Scope & Foundation — Learner Analytics & Insights ("Know my trajectory")

**Status:** PLANNING (audit phase — NO implementation)
**Authoritative implementation contract for P13.**
**Branch target:** `feature/individual-user-foundation`
**Parent of P13:** Post-P12 audit at HEAD `623c43f` (this doc + `POST_P12_PRODUCT_ARCHITECTURE_AUDIT.md` + `POST_P12_CAPABILITY_MATRIX.md`)
**Type:** Feature phase — implementation occurs ONLY after this doc is approved.

---

## 1. P13 Objective

Give the learner a **deterministic, per-learner analytics & insights surface** ("Know my trajectory") that answers three questions the product currently cannot:

1. **Am I improving?** — a performance/accuracy trajectory over completed attempts (percent, correct/incorrect) across time.
2. **Where am I strong and weak over time?** — concept-wise mastery trajectory (weak → developing → mastered movement), the concepts trending up or stuck.
3. **Is my effort paying off?** — effort (attempts taken, sessions, time) vs mastery gained, so the learner sees whether practice is converting into mastery.

Every insight panel must carry an **actionable deep-link** (→ review, → practice, → plan, → tutor) so analytics drives the next learning action rather than being a passive dashboard. P13 also folds in the **player → dashboard/plan/review hub link** (the single biggest learner dead-end) and the dead `?deck=` cleanup, because they are the same "connect the learner to their plan" work.

**Non-goal:** no LLM-generated "insights", no ML/IRT, no teacher/classroom dashboards, no generic BI tool.

---

## 2. User Problem

> "I study and take checkpoints, but I can't see whether I'm actually getting better. The dashboard shows today's numbers and a short trend, but nothing tells me which concepts I've been stuck on for weeks or whether my extra practice time is moving my mastery. So I don't know what to prioritize."

Today the learner has mastery scalars, recommendations, a review queue, a Today Plan, goals and a learning path — but **no trajectory/insight view** that aggregates the life of their attempts into a decision. The `analytics.py` models exist but are orphaned; only a thin 10-point trend exists on the dashboard (`_build_trend`). P12 repaired the attachment data (attempt/score/session persistence on PostgreSQL) that makes this aggregation trustworthy.

---

## 3. Why P13 Now

- **Foundation readiness is highest it has ever been.** P12 just made `quiz_attempts` / `score_summaries` / `question_attempts` / `user_answers` persist correctly on PostgreSQL (19 PG behavioral tests). Any aggregation over attempts now reads reliable data.
- **It is the flagged "phase after P12."** The Post-P11 audit explicitly earmarked learner analytics as "the phase after A (P12)", blocked only by the then-broken attempt persistence. That blocker is now removed.
- **Deterministic and low-risk.** Aggregation over stored rows + rule-derived annotations (reusing the recommendation thresholds) needs zero AI, zero new infrastructure, and a single (optionally) additive migration — ideal for checkpoint-based, browser-verifiable engineering.
- **It is the last major missing learner intelligence surface** — everything else in the learn→assess→mastery→review→plan→tutor loop is COMPLETE and browser-verified.

---

## 4. Current Architecture Assumptions

- Backend: FastAPI (async), SQLAlchemy 2.x, UoW/repository, `app/main.py` mounts routers under `/api/v1`.
- Dual-dialect PostgreSQL (production) / SQLite (tests) via `PortableJSONB`; linear Alembic chain, **single head `0033_educational_memories`**; additive-only migrations.
- Frontend: vanilla multi-page SPA in `backend/frontend/`, no framework, mounted at `/frontend`; per-page `authFetch`/`escHtml`.
- Learner intelligence is **deterministic rule-based** (mandate); `AIContentService` is the only AI path.
- Ownership: every resource scoped to `user.id` from `get_current_user`; 404-equalized.
- Bounded-world policy: learner-scoped windows, `LIMIT`s, bounded caches (5000/1800), bounded lists.
- Mypy floor: **83 errors / 24 files**, zero new.
- Existing deterministic services: `educational_memory_service` (bands weak<50 / developing 50–85 / mastered ≥85), `recommendation_engine` (thresholds 50/85/95), `learner_progress_service` (bounds `_MAX_LESSONS=50`, `_MAX_RECENT_ATTEMPTS=10`, `_MAX_TREND_POINTS=10`, `_MAX_CONCEPTS=100`).

---

## 5. Scope (MVP)

**P13-A1 — Analytics read-composition service + endpoints (deterministic).**
A new `learner_analytics_service` that aggregates learner-scoped rows from **existing tables only**:
- `quiz_attempts` (status `completed`, `percent_score`, `completed_at`, `user_id`, `quiz_version_id`)
- `score_summaries` (correct/incorrect counts, earned/total)
- `learning_sessions` (completion, activity)
- `educational_memories` (mastery bands) via the existing cache-backed service
- `review_schedules` (optional: review completion count/regularity)

Endpoints (all under `user` from `get_current_user`, learner-scoped, bounded windows):
- `GET /me/analytics/overview` — summary: attempts taken, average/mastery, mastered/developing/weak counts, trend percent, effort (sessions).
- `GET /me/analytics/trend` — accuracy/percent over last N (≤30) completed attempts by date.
- `GET /me/analytics/concepts` — per-concept trajectory: current band, change over window, review count, and whether trending up / flat / down (rule-derived from recent mastery movement).
- `GET /me/analytics/effort` — effort (attempts + sessions + time) vs mastery delta, per concept or overall.

Each response borrows the **existing** (orphaned-but-harmless) schema shapes where suitable (e.g. reuse `analytics.py`/`analytics_insights.py` response models as shapes only; do NOT write to the orphaned tables).

**P13-A2 — Dashboard analytics panels (vanilla frontend).**
New panels in `dashboard.html` fed by the endpoints above: "Your trajectory" (sparkline/bar), "Concepts at a glance" (up-flat-down per concept with deep-links to practice/tutor), "Effort vs mastery". All dynamic content `escHtml`-escaped; deep-links built server-side.

**P13-A3 — Hub navigation completion (folded in).**
- `player.html`: add a header/breadcrumb link to `dashboard.html` (and, where trivially present, the review/Today Plan) so the learner can leave a lesson to their plan — closing the biggest dead-end (G7).
- Remove dead `?deck=` consumption in `player.html` and stop emitting it in `processing.html`.

**P13-A4 (hardening, small) — Stabilize the adaptive `/next` player handshake.**
Address the P12-era flakiness in the two P10 browser tests: make `submit` idempotent against a `/next` that has already persisted a question (no double UoW commit / no response race) so the 50%-vs-100% race cannot yield a wrong persisted answer. This is a correctness guard, not a redesign.

---

## 6. Explicit Exclusions (OUT OF SCOPE)

- NO LLM/AI-generated insights or summaries; if a future "AI insight" is ever added it MUST stay behind `AIContentService`.
- NO ML/IRT/elo learner modeling; NO teacher/classroom/creator analytics dashboards; NO `SystemAnalytics`/multitenant surfaces.
- NO framework migration; NO new infra; NO vector-DB; NO Redis/Celery functional-test work in this phase (E — retention automation — remains deferred).
- NO changes to Mastery invariants, scoring, recommendations, review scheduling, or adaptive ordering semantics.
- NO new analytics **write** tables by default — read-compose existing rows; do NOT force the orphaned analytics tables to become write targets.
- NO RAG/tutor changes; NO video/animation/simulation runtime work (C remains deferred).

---

## 7. Existing Systems Reused

- `quiz_attempts` / `score_summaries` / `question_attempts` / `user_answers` — now PG-correct (P12). Source of accuracy/trend/attempt data.
- `learning_sessions` — effort/completion data.
- `educational_memory_service` (+ BoundedCache 5000/1800, mastery bands) — concept mastery + trajectory source.
- `recommendation_engine` thresholds (50/85/95) — reused for up/flat/down + weak/strong classification consistency.
- `learner_progress_service` bounds pattern (`_MAX_*`) — reuse the hard-bound convention.
- `study_plan_service` / `review_schedule_service` deep-link builders — reuse for actionable CTAs.
- `app/schemas/analytics.py` + `app/schemas/analytics_insights.py` — reuse as **response shapes** only.
- `dashboard.html`, `player.html` (vanilla), `escHtml`, `authFetch`.
- `quiz_repository`/`score_summary_repository`/`learning_session_repository` / UoW.
- `observability/metrics.py` — add `p13_*` counters.

---

## 8. Proposed Domain Model

**No new persisted domain models by default.** P13 reads and aggregates existing tables. The domain artifacts are:

- `LearnerAnalyticsService` (new, in `app/services/learner_analytics_service.py`) — pure-ish read-composition service with bounded windows.
- Pure aggregation helper functions (mirror `adaptive_assessment.py` style: `app/services/learner_analytics.py`) — deterministic, unit-testable banding/trend/up-flat-down logic with NO DB dependency:
  - `band(mastery)` (reuse 50/85), `trend_delta(series)`, `classify_trend(delta)` → `up|flat|down`, `effort_vs_gain(attempts, mastery_delta)`.
- Response models in a P13 schema (or reuse the orphaned analytics response schemas as shapes) — no DB table.

**Optional additive migration (documented, decided at implementation, NOT created now):** if query profiling shows the aggregation is slow on realistic volumes, add a single-column index on `quiz_attempts(user_id, completed_at)` (or `score_summaries(user_id, created_at)`) to make the trend/concept window bounded and indexed. This is a small additive Alembic migration — justified only by measured need; default is to reuse the existing `user_id` indexes first. Per the audit rule, a storage/content migration is not applicable here; this would be the only schema-touching candidate and is optional.

---

## 9. API Contract

All endpoints under `GET /me/analytics/*`, `Depends(get_current_user)`, learner-scoped, 404/401 semantics per the platform, response envelope `APIResponse[T]` (FastAPI), and every insight item carries a server-built `deep_link`.

- `GET /me/analytics/overview` →
  ```
  {
    attempts_taken: int,
    avg_percent: float | null,
    mastered_count, developing_count, weak_count: int,
    session_count: int,
    trend_percent: float | null,        # recent vs prior accuracy
    current_focus: {concept_public_id, name, band, deep_link} | null
  }
  ```
- `GET /me/analytics/trend?window=30` (window ≤ 30, bounded) →
  ```
  { points: [ {date, correct, incorrect, percent, attempts} ], window }
  ```
- `GET /me/analytics/concepts` →
  ```
  { concepts: [ {concept_public_id, name, band, trend: up|flat|down,
                 current_mastery, delta_mastery, review_count,
                 deep_link_practice, deep_link_tutor} ] , max: 100 }
  ```
- `GET /me/analytics/effort` →
  ```
  { effort: [ {concept_public_id, name, attempts, sessions, time_seconds,
               mastery_delta, efficiency: gain_per_attempt} ], max: 100 }
  ```

Backward compatible: **no existing endpoint contract changes**. Existing `/me/progress`, `/me/review`, `/me/plan`, `/me/goals`, `/me/path` all unchanged.

---

## 10. Frontend Behavior

`dashboard.html` gains analytics panels driven by `/me/analytics/*`:
- **"Your trajectory"** — a compact bar/sparkline from `/trend` (percent per window point), with current-focus summary from `/overview`.
- **"Concepts at a glance"** — table/chips from `/concepts`: each concept shows current band + trend arrow (up/flat/down) + a **Practice** deep-link (→ `player.html?lesson=`) and **Ask tutor** (→ `tutor.html?concept=`) where those IDs exist; server builds links so no dead buttons.
- **"Effort vs mastery"** — from `/effort`, e.g. "3 attempts → +18 mastery" per concept, to motivate the loop.
- All injected HTML escaped via `escHtml`; empty state ("No checkpoints yet — take a checkpoint to start seeing your trajectory.") with a CTA to a lesson.
- `player.html`: add header nav to `dashboard.html`; remove dead `?deck=` handling. `processing.html`: stop emitting `?deck=`.

---

## 11. Security Model

- All `user_id` resolution from `get_current_user`, never client-supplied.
- Every endpoint learner-scoped; cross-user access → 404 (equalized) via existing repository/ownership pattern.
- New `test_p13_analytics_security.py`: unauth 401, cross-user analytics read → 404, own-only data.
- No new secrets; no rate-limit changes needed beyond verifying default/override coverage for `/me/analytics/*`.
- Reuse `escHtml` for all new dynamic frontend content; server-built deep-links only.
- Do NOT surface another user's rows in any aggregation (all aggregations filter by `user.id` at the query layer).

---

## 12. Database Considerations

- **Prefer existing tables** (`quiz_attempts`, `score_summaries`, `learning_sessions`, `educational_memories`, `review_schedules`). No new write path.
- Aggregations are **learner-scoped** (`WHERE user_id = :uid`) and **bounded** (`LIMIT` / time-window ≤30 points / ≤100 concepts), reusing existing `user_id` indexes.
- SQLite/PG dual-dialect green; PortableJSONB unaffected (no new JSON fields by default).
- **Optional single additive migration**: an index on `quiz_attempts(user_id, completed_at)` (or `score_summaries(user_id, created_at)`) ONLY if profiling justifies it; document in the implementation report if used. **Do not create it now.** Keep head single (`0033` + optional `0034`).
- Anchors on SQLAlchemy aggregates (`func.avg`, `func.count`, `func.sum`) with explicit `user_id` filters — no table scans outside the learner's rows.

---

## 13. Testing Strategy

- **Unit (pure):** `tests/unit/test_p13_learner_analytics.py` — banding, trend_delta, up/flat/down classification, effort_vs_gain bounds, determinism (same input → same output), empty-state handling, window clamping. Pure `learner_analytics.py` has no DB.
- **Integration (HTTP + service):** `tests/integration/test_p13_analytics_api.py` — each endpoint returns correct learner-scoped aggregates over seeded rows; empty-state; bounded windows (window clamp, concept cap).
- **Security:** `test_p13_analytics_security.py` — cross-user 404, unauth 401.
- **Dual-dialect:** full SQLite regression stays green (≥ 1183).
- **PostgreSQL:** extend (at least) one PG behavioral test asserting the analytics aggregation over a migrated schema returns correct sums/avgs on `quiz_attempts`/`score_summaries` (guard against any future drift on the newly-relied-upon columns).
- **Mypy:** zero new errors (83/24).

---

## 14. Browser E2E Strategy

New `tests/e2e/test_p13_analytics_e2e.py` (Playwright + system Chrome, real login against the live vanilla SPA on SQLite):
1. Seed a learner with 2–3 completed attempts of differing percents + a concept with moving mastery → dashboard shows the trajectory panel, the concept trend arrow, and the effort line.
2. Assert the "Practice"/"Ask tutor" deep-links resolve to real `player.html?lesson=` / `tutor.html?concept=` pages (no dead buttons).
3. Assert the **player → dashboard** hub link (P13-A3) is present and navigates correctly.
4. Fold in the (stabilized) P6/P10/P12 regression paths so the adaptive player still works.

---

## 15. Performance Constraints

- Every `/me/analytics/*` query is learner-scoped and bounded: trend ≤ 30 points; concepts ≤ 100; effort ≤ 100; no table scan outside the learner's rows.
- Reuse the existing `educational_memory_service` cache for mastery so concept reads are cache-backed (single DB hit on miss).
- No N+1: bulk `IN` loads for score summaries/sessions; avoid per-concept subqueries where a join/aggregate suffices.
- Whole-request target: ≤ a handful of bounded queries, no unbounded pagination.

---

## 16. Observability

- Add `p13_*` counters in `observability/metrics.py` (e.g. `p13_analytics_views_total{endpoint}`, `p13_analytics_errors_total{reason}`) exposed via `GET /api/v1/metrics`, following the P10/P11/P12 pattern.
- Log aggregation windows / errors without learner PII.

---

## 17. Checkpoint Structure

| Chk | Objective | Files expected | Tests | Acceptance |
|---|---|---|---|---|
| C0 | Baseline / contract (re-verify P12 gates incl. the stabilized E2E) | none | full regression | gates green |
| C1 | Pure `learner_analytics.py` logic (band/trend/up-flat-down/effort) | pure module + unit tests | unit | deterministic, bounded |
| C2 | `learner_analytics_service` + `/me/analytics/*` endpoints + schemas | service, router, schemas | integration + security | learner-scoped, correct, 404/401 |
| C3 | PG behavioral extension for aggregation | PG test | PG | correct on migrated schema |
| C4 | Dashboard analytics panels (trajectory/concepts/effort) + empty states | `dashboard.html` | — | wired, escaped, deep-linked |
| C5 | Player→dashboard hub link; dead `?deck=` removal | `player.html`, `processing.html` | — | navigable, no dead param |
| C6 | Adaptive `/next` handshake stabilization | `quiz_attempt_service` / `player` | E2E P10/P12 re-run | flakiness resolved |
| C7 | Browser E2E (P13 + P6/P10/P12/regressions) | `test_p13_analytics_e2e.py` | E2E | green |
| C8 | Observability (`p13_*`) | metrics | — | present |
| C9 | Full regression (all gates, PG behavioral, E2E) | — | all | contract green |
| C10 | Release gate + report + docs | P13 report | — | final + clean tree |

---

## 18. Release Gates (P13 must hold; use P12 baselines)

- SQLite: ≥ 1183 passed (0 failed). 
- PostgreSQL: ≥ 19 passed **plus** the new aggregation behavioral test green.
- Browser E2E: ≥ 15 passed with the P10/P12 tests **stable** (no flakiness) plus the new P13 analytics E2E.
- Ruff: clean. Mypy: ≤ 83 errors / 24 files, **zero new** (unless a future phase intentionally changes the baseline and documents why).
- Alembic: single head `0033` (default) or `0034_*` only if the optional index is justified; single head either way.
- Secret scan: clean. `git diff --check`: clean. Working tree clean.
- User isolation preserved on every new/changed endpoint (cross-user → 404).
- No new AI/RAG changes; deterministic learner intelligence preserved.
- `p13_*` observability present.

---

## 19. Known Risks

| Risk | Mitigation |
|---|---|
| Aggregation slow on large attempts | learner-scoped + bounded windows + existing indexes; optional additive index, chosen only by profiling |
| Analytics becomes decoration with no loop | every row/deep-link actionable (practice/tutor/plan); empty state nudges to a checkpoint |
| Orphaned analytics models tempt a migration-for-migration's-sake | read-compose existing tables; use orphaned schemas as shapes only; no forced writes |
| Scope creep to LLM insights / teacher dashboards | explicit exclusions; deterministic-only MVP |
| Adaptive `/next` flakiness persists | C6 hardening (idempotent submit guard) + E2E re-run as a gate |
| Frontend helper duplication grows | reuse existing `authFetch`/`escHtml` per page (no refactor required); no framework migration |

---

## 20. Rollback Strategy

- No historical migration changes; optional new index is additive and safely reversible (`alembic downgrade` one revision at most).
- New endpoints/services are additive: revert the router mount + service + dashboard panel to undo P13 without touching P0–P12 files.
- Frontend panel and player link are purely additive DOM; revert by reverting the dashboard/player edit.
- Checkpoint-by-checkpoint rollback = revert the last checkpoint commit; primary path never requires a destructive migration.

---

**Definition of Done:** the learner can view their accuracy trajectory, per-concept trend (up/flat/down) with actionable practice/tutor deep-links, and effort-vs-mastery — all deterministic, learner-scoped, PG-correct, and browser-verified; the player connects back to the dashboard/plan; the adaptive `/next` flakiness is resolved; all release gates green; tree clean; P13 report produced.
