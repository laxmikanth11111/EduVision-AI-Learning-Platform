# P13 Implementation Report -- Learner Analytics & Insights ("Know my trajectory")

## 1. Starting Commit
`c730350` (`docs(p12): add post-p12 architecture audit and p13 scope`) -- before any P13 implementation work. Branch: `feature/individual-user-foundation`. Working tree was clean at the start of P13.

## 2. Final Commit
Pending -- P13 work is currently an uncommitted scoped change on `feature/individual-user-foundation` at HEAD `c730350`. This report describes that work; it is ready to be committed as the P13 completion commit once the release gate is signed off.

## 3. P13 Scope
Close the "can't see my trajectory" gap: give the learner a deterministic, read-only view of **accuracy over time, per-concept mastery movement, and effort vs. mastery gained** -- all derived from live, persisted activity rows (`quiz_attempts`, `score_summaries`, `learning_sessions`) plus the existing `educational_memories` blob. No AI, no ML, no IRT, no new tables, **zero migrations**.

Four learner-scoped endpoints under `/api/v1/me/analytics/*`:

- **Overview** (`GET /me/analytics`, alias `GET /me/analytics/overview`) -- attempts taken, average percent, mastered/developing/weak counts, completed sessions, a recent-vs-earlier trend percent, and a single actionable **current focus** concept (weakest with activity, carrying a server-built deep-link).
- **Trend** (`GET /me/analytics/trend?window=≤30`) -- accuracy per date over a bounded, latest-first window (oldest -> newest).
- **Concepts** (`GET /me/analytics/concepts`) -- per-concept band + up/flat/down arrow + current mastery + numeric mastery movement + Practice (**player.html?lesson=**) and Ask-tutor (**tutor.html?concept=**) deep-links, weakest first.
- **Effort** (`GET /me/analytics/effort`) -- attempts, sessions, time spent, mastery gained, and points-per-attempt for each concept ("3 attempts -> +38 mastery" loop).

Out of scope per the audited contract (still deferred): LLM-generated insights, teacher/classroom/creator analytics, generic BI tool, adaptive assessment (NG-4, now P12), retention scheduling, analytics writes, calendar UI.

## 4. Checkpoints Completed
| Chk | Objective | Result |
|---|---|---|
| C0 | Baseline / contract (alembic head `0033`, SQLite 1183, PG 19, E2E 15, ruff clean, mypy 83/24) | PASS |
| C1 | Pure `learner_analytics.py` logic (band/classify_trend/trend_delta/trajectory/clamp_window/gain_per_attempt/band_rank) | PASS |
| C2 | `learner_analytics_service.py` read-composition (overview/trend/concepts/effort; batched, bounded, learner-scoped) | PASS |
| C3 | Schemas + router `/me/analytics/*` + mount in `main.py` + `p13_analytics_*` metrics | PASS |
| C4 | Unit tests `tests/unit/test_p13_learner_analytics.py` (22) | PASS |
| C5 | Integration tests `tests/integration/test_p13_analytics_api.py` (8: 401s, learner scoping, empty-state, metrics, overview/trend/concepts/effort) | PASS |
| C6 | PostgreSQL aggregation tests `tests/postgres/test_p13_analytics_pg.py` (6) incl. migration-head guard | PASS |
| C7 | Dashboard analytics panels (trajectory / concepts / effort) + empty states | PASS |
| C8 | Player -> dashboard hub link; dead `?deck=` removal (`processing.html`; player had none) | PASS |
| C9 | Browser E2E `tests/e2e/test_p13_analytics_e2e.py` (3: panels render, empty state, player-dashboard hub) | PASS |
| C10 | Release gate (SQLite 1213, PG 25, E2E 18, ruff clean, mypy 83/24, single head `0033`, P10 NG-1/NG-3 stabilized, diff-check clean) | PASS |
| C11 | This report + docs | PASS |
| C12 | Completion commit | PENDING (commit withheld until user requests) |

## 5. Files Changed (P13)
New:
- `app/services/learner_analytics.py` -- pure, side-effect-free helpers (no DB dependency; mirrors `adaptive_assessment.py` / `recommendation_engine` style).
- `app/services/learner_analytics_service.py` -- `LearnerAnalyticsService` (read-composition over `UnitOfWork`).
- `app/schemas/learner_analytics.py` -- `AnalyticsOverview`, `ConceptFocus`, `TrendPoint`, `TrendResponse`, `ConceptAnalytic`, `ConceptsResponse`, `EffortAnalytic`, `EffortResponse`.
- `app/api/v1/analytics.py` -- router `analytics_router` (prefix `/me/analytics`), mounted after `path_router` in `app/main.py`.
- `tests/unit/test_p13_learner_analytics.py` (22), `tests/integration/test_p13_analytics_api.py` (8), `tests/postgres/test_p13_analytics_pg.py` (6), `tests/e2e/test_p13_analytics_e2e.py` (3).

Modified:
- `app/observability/metrics.py` (register `p13_analytics_views_total` / `p13_analytics_errors_total` after the P12 section).
- `frontend/dashboard.html` (three analytics panels + focus callout + CSS; all `escHtml`-escaped, server-built links only).
- `frontend/player.html` (header **Dashboard** hub link).
- `frontend/processing.html` (stopped emitting the dead `?deck=` query param on the start-button href).
- `tests/e2e/test_p10_adaptive_review_e2e.py` (test-only stability hardening, see SS5a).

**Zero new database migrations.** Alembic single head remains `0033_educational_memories`.

### 5a. P10 E2E hardening (test-only, required by the gate)
While running the full browser suite, P10 `test_p10_ng1_quiz_next_action_cta` and `test_p10_ng3_critical_learning_loop` failed ~1-in-2 runs with the quiz score ring showing 50% instead of 100%. **Root cause (pre-existing, reproduced on the P12 baseline `c730350~1` via `git stash`):** after answering Q1 and clicking "Next", the adaptive `/next` handshake rebuilds the question DOM asynchronously; the test's next `click()` could land on the still-visible Q1 option (re-selecting it) leaving Q2's answer blank, so the server graded 1-of-2. Fix: a `_wait_for_question(page, stem)` helper waits for Q2's stem before clicking its option (same pattern as the P12 adaptive E2E). Test-only; no product code changed. Mirrors the precedent of the P11 selector-scoping note.

## 6. Design Decisions

### Mastery movement is DERIVED, not stored (important correction)
The educational-memory blob persists only a *categorical* trend (`improving|stable|...`), so a numeric "how much did mastery move" cannot come from the blob. P13 derives a numeric `delta_mastery` from each concept's **completed-attempt percent series** (`quiz_attempts.percent_score` for attempts on the concept's lesson, via `Quiz.lesson_id`): `trend_delta(series)` = `mean(later half) - mean(earlier half)` with the later half carrying the remainder (oldest -> newest). It is reported **only when ≥ 2 completed attempts exist** -- never a fabricated zero/None; a single attempt yields `delta_mastery=None` and `efficiency=None`.

### Band/arrow split (deterministic, total)
- **Band** buttons: `band(mastery_score)` reuses the authoritative 50/85 thresholds (`weak < 50`, `developing 50-84.99`, `mastered >= 85`).
- **Arrow** (`up|flat|down`): `classify_trend(memory categorical trend)` maps `improving -> up`, `regressing -> down`, everything else -> `flat`. Attempt-derived and memory-derived signals are kept separate and both surfaced (`arrow` from memory category; `delta_mastery` numeric from attempts).

### Ordering (deterministic, weakest first)
- **Concepts**: key `(band_rank, -mastery_score, concept_public_id)` so the weakest instructional target always surfaces first.
- **Effort**: key `(band_rank, -attempts, concept_public_id)`.
- **Trend**: grouped by date (`YYYY-MM-DD`, `unknown` for null `completed_at`), reversed to oldest -> newest; `percent` = mean of percent-bearing attempts that day; `correct`/`incorrect` come from the `score_summaries` LEFT join (legacy attempts without a summary contribute 0 counts, never a crash).

### Deep-links are server-built (no dead buttons)
Practice links to `/frontend/player.html?lesson=<lesson>` when a resolvable lesson exists (direct `Concept.lesson_id`, else the presentation's lessons fallback via `GeneratedLesson`); otherwise practice is `None` and the dashboard renders no Practice button. Ask-tutor (`/frontend/tutor.html?concept=<id>`) is always present. The focus callout reuses the overview's deep-link so a dashboard insight always resolves to an action.

### Bounded-world policy
- Trend window: OpenAPI `ge=1, le=30` plus a service-level `clamp_window` (default/clamp 30) -- defense in depth.
- Concept/effort rows: capped at 100; activity scans capped (`_MAX_ATTEMPTS_SCAN = 500`, `_MAX_TREND_ATTEMPTS_SCAN = 60`).
- Memory reads reuse the existing `educational_memory_service` BoundedCache (5000/1800) unchanged.

## 7. User Isolation / Security
All four endpoints resolve the identity exclusively from `get_current_user` -- no user id is ever accepted from the client, so a cross-user "read" is structurally impossible (there is no resource-id argument to equalize). **Test-documented behavior:** user B (authenticated but bare) receives genuinely empty analytics (200 with zeroes / empty lists) on every endpoint while A's rows are never returned.

- Unauthenticated / invalid-token requests -> **401** on all four endpoints (test: `test_unauthenticated_analytics_requests_rejected`).
- Learner-scoped query layer: every aggregation is `WHERE user_id = :auth_uid` (test: `test_analytics_are_learner_scoped_user_b_sees_empty`).

Note: the P13 scope doc's "cross-user analytics read -> 404" line cannot be expressed on a no-resource-id read API; the honest enforcement is structural learner-scoping (B's own empty payload), verified above. No learner PII is logged (metrics carry only `endpoint`/`outcome`/`reason`).

Frontend: all new dynamic content goes through `escHtml`, and every CTA href is a server-built deep-link.

## 8. Performance / Bounded Queries
- `_load_concept_activity` batches Concept lookups and joins `QuizAttempt` -> `Quiz` by `lesson_id` (each concept's series from a single query per lesson set, no N+1).
- Trend/overview scans are bounded (60/500 attempts); lectures run on existing indexes.
- No AI on any read path.

## 9. Observability
Registered in `app/observability/metrics.py`, incremented in `app/api/v1/analytics.py` `_build`:
- `p13_analytics_views_total{endpoint, outcome="ok"}` on every successful build.
- `p13_analytics_errors_total{endpoint, reason="build_failed"}` on exceptions (re-raised).
Rendered by the existing `GET /api/v1/metrics` Prometheus endpoint; verified in `test_analytics_metrics_appear_after_read`.

## 10. Database Impact
**Zero.** No migration, no new table, no column change. All reads land on P12-parity tables (`quiz_attempts` / `score_summaries` / `learning_sessions` / `educational_memories`) plus `quiz`/`generated_lessons`/`concepts`. Alembic single head unchanged: `0033_educational_memories` (guarded by `test_p13_no_new_migration_head_unchanged`).

## 11. AI / RAG Impact
None. All analytics are deterministic read-compositions; no AI provider and no RAG path were touched. Prompt-injection boundary unchanged.

## 12. Browser E2E Flow
Playwright + system Chrome against a real uvicorn server (real sign-in, vanilla `backend/frontend/`). `tests/e2e/test_p13_analytics_e2e.py`:

1. **`test_p13_dashboard_analytics_panels_render`** -- seeds a learner with 3 completed attempts at 40/65/90, two concepts (weak 35 improving / mastered 90 stable) and one completed session, then signs into the real dashboard and asserts: three trajectory bars (40%/65%/90%), the focus callout with a `player.html?lesson=` deep-link, two concept rows with band chips + up-arrow + working Practice/Ask-tutor links, and the effort row ("3 attempts", "+38 mastery", "13 pts/attempt").
2. **`test_p13_dashboard_empty_state`** -- a brand-new learner sees "No checkpoints yet" / "No concepts tracked yet" empty state (waits on the final copy, not the loading skeleton).
3. **`test_p13_player_dashboard_hub_link`** -- `player.html` exposes a Dashboard header link that navigates to the dashboard.

Result: **3 passed** for the new P13 E2E; full E2E suite **18 passed** (`pytest -m e2e`), including the stabilized P10 NG-1/2/3 regressions.

## 13. Test Results
- **Unit + integration** (`pytest -q tests/unit tests/integration -p no:cacheprovider`): **1213 passed** (was 1183 at the P12 baseline; the +30 are the 22 P13 unit tests + 8 P13 integration tests), 1 external StarletteDeprecationWarning, 0 failed.
- **PostgreSQL** (`pytest -q tests -m postgres -p no:cacheprovider`): **25 passed** (was 19; the +6 are `tests/postgres/test_p13_analytics_pg.py`, pinning sums/avgs on the real engine + the migration-head guard).
- **Browser E2E** (`pytest -m e2e -q -p no:cacheprovider`): **18 passed, 0 failed** (15 baseline + 3 P13; NG-1/NG-3 stabilized by the test-only stem-wait in SS5a).
- **Ruff** (`ruff check .`): **All checks passed** (whole repo, no exceptions).
- **Mypy** (`mypy app`): **83 errors / 24 files** -- exactly the authoritative P12 baseline, **zero new P13 errors**.
- **Alembic head**: single head `0033_educational_memories` (unchanged; zero P13 migrations).
- **Secret scan** (Select-String over every P13 new/changed file): **0 hits for real secrets** -- the only matches are the deterministic local E2E fixture credentials (`P13Loop1234!` / `P10Loop1234!`, the established `P12Loop1234!` pattern). `git diff --check`: clean.

## 14. Known Limitations / Notes
- **`delta_mastery` is attempt-backed, not blob-backed** (see SS6). A learner who has memory categories but <2 completed attempts sees `delta_mastery=None`; this is honest ("no movement proven yet"), never fabricated.
- **Cross-user behavior is structural scoping, not 404** (see SS7) because the endpoints expose no resource-id surface to equalize.
- The overview endpoint is reachable at both `/me/analytics` (primary, used by the dashboard) and `/me/analytics/overview` (documented alias, hidden from the OpenAPI schema).
- The P10 NG-1/NG-3 stem-wait is a test-only change to pre-existing flaky browser tests (stability of the adaptive `/next` DOM rebuild); it does not alter product behavior.

## 15. Exact Commands Used
```
.venv\Scripts\python.exe -m ruff check .                          # All checks passed (whole repo)
.venv\Scripts\python.exe -m mypy app                              # 83 errors / 24 files -- authoritative P12 baseline, 0 new in P13
.venv\Scripts\python.exe -m alembic heads                         # 0033_educational_memories (single, unchanged)
.venv\Scripts\python.exe -m pytest tests/unit tests/integration -q -p no:cacheprovider       # 1213 passed
.venv\Scripts\python.exe -m pytest tests -m postgres -q -p no:cacheprovider                  # 25 passed
.venv\Scripts\python.exe -m pytest tests/e2e -m e2e -q -p no:cacheprovider                   # 18 passed
# Secret scan (new/changed files): 0 real secrets; only deterministic E2E fixture passwords. git diff --check: clean.
```

## 16. Final Release-Gate Conclusion
All P13 release gates are **GREEN**:
- The learner can see their accuracy trajectory (bounded ≤30-point trend), per-concept up/flat/down + numeric movement, and effort vs. mastery gained -- all in the browser on `dashboard.html`.
- Every new endpoint is learner-scoped (auth-only identity), unauthenticated -> 401, cross-user rows structurally unreachable (B's genuinely empty payload verified), and bounded (trend ≤30 via validation + server clamp; concepts/effort ≤100).
- All insights are deterministic read-compositions -- no AI / no new AI provider / no RAG change / no new scheduler.
- Every dashboard deep-link is server-built and verified in the browser (practice/tutor/focus).
- **Zero new migrations** (single alembic head `0033_educational_memories`), zero DB writes.
- SQLite regression 1213 passed (> P12 1183). PostgreSQL 25 passed (> P12 19). Browser E2E 18 passed (incl. P10 NG-1/NG-2/NG-3, two of which were stabilized with a test-only stem-wait). Ruff clean (whole repo). Mypy 83/24 baseline, zero new P13 errors.
- Observability counters added. Secret scan: 0 real secrets (deterministic E2E fixture passwords only). git diff --check: clean.
- Completion commit pending user request (git commit is not performed unless explicitly asked).