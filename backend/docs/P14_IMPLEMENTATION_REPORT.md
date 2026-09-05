# P14 Implementation Report -- Retention & Review Automation ("Close the review loop")

## 1. Starting Commit
`32ab12b` (`docs(p13): add post-p13 architecture audit and p14 scope`) -- before any P14 implementation work. Branch: `feature/individual-user-foundation`. Working tree was clean at the start of P14 (P13 committed at `c191d44`).

## 2. Final Commit
This P14 change is committed as `feat(p14): close the review loop with self-reported recall outcomes and a retention surface` once the release gate is signed off (per the P14 objective, P14 is committed only after C0->C8 is release-green -- that gate is green; see section 16).

## 3. P14 Scope
Close the "learn -> review" retention gap: give the learner a **deterministic self-assessment** at the moment of review (a small controlled outcome vocabulary) that drives the spaced-interval ladder **and** an honest, persisted **retention/recall signal** surfaced in the dashboard -- all stored inside the existing `review_schedules.review_metadata` JSONB. No AI, no ML, no IRT/Elo, **zero new tables, zero migrations**.

Delivered surfaces:
- **Review outcomes** -- `again | hard | good | easy` on the review queue. Mapping (deterministic, bounded): `again` -> step 0 (tightest interval), `hard` -> hold step, `good` -> +1 (identical to legacy/default), `easy` -> +2 capped at `MAX_STEP` (3). Ladder stays `(1,3,7,14)`.
- **Retention signal** per concept -- a recall signal derived from observed outcome history (weighted recent outcomes, decayed by days since review), distinct from the quiz-owned mastery scalar, plus status `on_track | at_risk | overdue | new`.
- **Retention surface** -- `GET /me/analytics/retention` returns an overdue-first list of concept signals (bounded at 100) with server-built deep-links and a bucketed summary.
- **Outcome completion API** -- `POST /me/review/{schedule_id}/complete` accepts an optional body `ReviewCompleteIn{outcome}`; absent/empty body === legacy default `good` exactly.

Out of scope (deferred, unchanged): nudges, trend-line beyond MVP, IRT/Elo, mastery-decay rewrite, video offload, Tutor 2.0, RAG, mobile/ML.

## 4. Checkpoints Completed
| Chk | Objective | Result |
|---|---|---|
| C0 | Baseline / contract (alembic head `0033`, SQLite unit+int 1213, PG 25, E2E 18, ruff clean, mypy 83/24) | PASS |
| C1 | Pure `app/services/retention.py` (outcome vocabulary, next-step/interval, JSONB merge + counts + history cap, accuracy, band, status, summary, deterministic sort) | PASS |
| C2 | `tests/unit/test_retention_service.py` (67) | PASS |
| C3 | Schemas `app/schemas/review.py` (`ReviewOutcome`, `ReviewCompleteIn`, enriched queue/complete responses) | PASS |
| C4 | Product wiring: `review_schedule_service.complete(outcome=...)` outcome-aware; `_build_queue_item` enrichment; `app/api/v1/review.py` optional body + `p14_review_outcomes_total`; `app/observability/metrics.py` counters | PASS |
| C4b | `tests/integration/test_p14_retention_api.py` (15: 401s, 422s, cross-user 404 no-write, 4-outcome spacing, no-body==legacy good, mastery invariant, history cap, queue enrichment, retention aggregation/ordering, metrics) | PASS |
| C5 | `GET /me/analytics/retention` in `app/api/v1/analytics.py`; Retention schemas in `app/schemas/learner_analytics.py`; `get_retention` in `learner_analytics_service.py`; `p14_retention_views_total` / `p14_retention_errors_total` | PASS |
| C6 | PostgreSQL behavior `tests/postgres/test_p14_retention_pg.py` (5: JSONB v2 round-trip, spacing ladder, cross-user 404 + bad outcome, retention aggregation, migration-head guard) | PASS |
| C7 | Dashboard retention panel + review-queue outcome buttons ("Mark reviewed"/good FIRST, then Again/Hard/Easy); `tests/e2e/test_p14_retention_e2e.py` (3: good->on_track, again->at_risk, learner-scoped cross-user 404) | PASS |
| C8 | Release gate (SQLite 1295, PG 30, E2E 21, ruff clean, mypy 83/24 0-new, single head `0033`, diff-check clean, secret scan clean) | PASS |
| C9 | `P14_IMPLEMENTATION_REPORT.md` + completion commit | PASS |

## 5. Files Changed (P14)
New:
- `app/services/retention.py` -- pure, side-effect-free retention/review-outcome helpers (no DB, no AI; mirrors `learner_analytics.py` / `adaptive_assessment.py` style).
- `tests/unit/test_retention_service.py` (67)
- `tests/integration/test_p14_retention_api.py` (15)
- `tests/postgres/test_p14_retention_pg.py` (5)
- `tests/e2e/test_p14_retention_e2e.py` (3)

Modified:
- `app/schemas/review.py` -- `ReviewOutcome(str, Enum)`, `ReviewCompleteIn`, `ReviewQueueItem` + `retention_status`/`review_accuracy`, `ReviewCompleteResponse` + `outcome`/`retained_strength`/`review_accuracy`.
- `app/services/review_schedule_service.py` -- `complete(..., outcome=DEFAULT_OUTCOME)`; writes v2 metadata (counts/history/step); `_build_queue_item` enrichment; `_days_since_review` helper.
- `app/api/v1/review.py` -- optional body, outcome validation via `ReviewCompleteIn`, `p14_review_outcomes_total` metric.
- `app/schemas/learner_analytics.py` -- `RetentionConcept`, `RetentionSummary`, `RetentionResponse`.
- `app/services/learner_analytics_service.py` -- `get_retention(user_id)` (bounded 100, schedule-gated, batch lesson links, deterministic sort, summary).
- `app/api/v1/analytics.py` -- `GET /me/analytics/retention` + `p14_retention_views_total` / `p14_retention_errors_total`.
- `app/observability/metrics.py` -- three P14 counters registered after the P13 section.
- `frontend/dashboard.html` -- Retention panel (summary stats + per-concept chip/strength/accuracy + server-built deep-links) and the review-queue outcome buttons ("Mark reviewed" first, then Again/Hard/Easy).
- `tests/e2e/test_p10_adaptive_review_e2e.py` -- test-only wait change for the new 4-button outcome layout (see SS5a).
- `tests/integration/test_p13_analytics_api.py` -- test-only fix for a pre-existing cross-file user collision (see SS5b).

**Zero new database migrations.** Alembic single head remains `0033_educational_memories`.

### 5a. P10 E2E test-only adjustment
P10 `test_p10_ng3_critical_learning_loop` clicked the review queue's `.reco-btn` and then waited on `#reviewPanelBody .reco-btn` to detach. P14 adds Again/Hard/Easy beside "Mark reviewed", so that locator now resolves to 4 elements and `wait_for(detached)` trips Playwright's strict-mode violation. Fix (test-only): wait on the specific clicked "Mark reviewed" button detaching instead of the whole `.reco-btn` set. Product behavior unchanged; the P10 NG-3 flow (click first button == good) is preserved.

### 5b. Pre-existing P13 cross-file collision (test-only, not a P14 regression)
`test_p13_analytics_api.py::test_analytics_are_learner_scoped_user_b_sees_empty` seeded user A under the reserved `p13_a@test.com` / `p13_b@test.com` emails that the module's autouse `_jwt_users` fixture owns as fixed `_USER_A_ID`/`_USER_B_ID` rows (same ids, same emails) in the shared DB. In a full-suite run this is a `UNIQUE users.email` (or id) collision the instant another module (e.g. `test_review_api_security.py`, `test_two_user_isolation.py`) reuses the identical well-known ids. This reproduces at the P13 baseline and is unrelated to P14 product changes. Fix (test-only): the scoping test now seeds A and B under fresh `uuid.uuid4()` ids + unique emails (the same pattern every other test in the file already uses), so isolation is guaranteed regardless of cross-file reuse. `users.email` uniqueness is preserved by the app.

## 6. Design Decisions

### Outcome vocabulary drives the interval ladder (D1-A)
`again` -> step 0, `hard` -> hold, `good` -> +1 (byte-for-byte the legacy completion path), `easy` -> +2 capped at `MAX_STEP` (3). `DEFAULT_OUTCOME = good` so any pre-P14 caller (absent body) behaves exactly as before. Ladder `(1,3,7,14)` unchanged.

### Review history is persisted inside the existing JSONB (D1-E)
`apply_outcome_to_metadata` merges `{outcome, at}` entries into `review_metadata["history"]` (capped at `MAX_HISTORY=20`), recomputes fixed-size per-outcome `counts`, and stamps `"v": 2`. Pre-P14 rows (no `v`/`history`) merge in place; every other existing key (`step`, `last_pressure`, `skipped_at`, ...) is preserved; malformed/missing metadata degrades to a fresh valid shape. Backward compatible, bounded growth, no schema change.

### Retention signal is OBSERVED RECALL, distinct from mastery
`retention_signal(...)` derives `retained_strength` (0-100) from `_recall_strength` over the recent-window outcomes (weights `(0.5, 0.3, 0.2)` newest->older; `again=0 / hard=0.5 / good=0.85 / easy=1.0`) decayed by days since review over a 30-day horizon. **It never writes the quiz-owned mastery scalar** -- mastery is only a fallback anchor when a legacy concept predates recall history. `review_accuracy` is the share of good+easy (None when no valid history; hard is NOT a success).

### Statuses are deterministic (D1-B)
`overdue` (due + unreviewed) > `new` (never reviewed, no fabricated strength) > recent-`again` -> `at_risk` > strength >= 80 -> `on_track`, else `at_risk`. `_retention_days_since` returns `None` (-> `new`) when a concept has no `review_schedule`; when it has one, the memory anchor (`last_reviewed_at or first_learned_at`) is preferred over `schedule.last_reviewed_at` (same precedence as the scheduler's decay signal).

### Ordering & summary (deterministic)
Sort key `(status_sort_key, -retained_strength-or-(-1.0), concept_public_id)` puts overdue first, then at_risk, on_track, new, completed. Summary `retention_average` is the mean of non-null strengths (None when no evidence); the four counts are exact.

### Deep-links are server-built & bounded
Both `deep_link_practice` (player.html?lesson=) and `deep_link_tutor` (tutor.html?concept=) are resolved server-side from real rows (batch `_resolve_lessons`, the P13 helper), so the dashboard never renders a dead CTA. Result sets capped at `_MAX_CONCEPTS` (100) via the existing `ReviewScheduleRepository.list_due(limit=100)`.

## 7. User Isolation / Security
- Identity always from `get_current_user`; the schedule is resolved only against the owning user (`get_by_user_and_public_id`) so a cross-user completion is a `404` with **no write** (test: `test_p14_cross_user_*`).
- Invalid outcome literals (`"gonzo"`, `"GOOD"`) -> automatic **422** via the strict `ReviewOutcome` enum (no partial write).
- Unauthenticated / empty token -> 401.
- `GET /me/analytics/retention` is learner-scoped by construction (all queries `WHERE user_id = auth`).
Frontend: all new dynamic content goes through `escHtml`; every CTA href is server-built.

## 8. Performance / Bounded Queries
- Retention read is a single `list_due(100)` + the P13 batch lesson-resolution (at most 3 queries) + in-memory memory records; no N+1.
- History is capped at 20 entries per schedule, so JSONB stays bounded regardless of review count.
- No AI on any read or write path.

## 9. Observability
Registered in `app/observability/metrics.py`:
- `p14_review_outcomes_total{outcome}` -- incremented on every completion with the actual outcome.
- `p14_retention_views_total` / `p14_retention_errors_total` -- around the retention endpoint build.
Rendered by the existing `GET /api/v1/metrics` Prometheus endpoint (verified in the integration suite).

## 10. Database Impact
**Zero.** No migration, no new table, no column change. New state lives only inside the existing `review_schedules.review_metadata` JSONB. Alembic single head unchanged: `0033_educational_memories` (guarded by `test_p14_no_new_migration_head_unchanged`).

## 11. AI / RAG Impact
None. Every P14 path is deterministic (no AI provider, no RAG). Prompt-injection boundary unchanged.

## 12. Browser E2E Flow
Playwright + system Chrome against a real uvicorn server (real sign-in, vanilla `backend/frontend/`). `tests/e2e/test_p14_retention_e2e.py`:

1. **`test_p14_good_default_and_on_track`** -- seeds one weak concept + overdue step-0 schedule; asserts the review queue renders "Mark reviewed" first then Again/Hard/Easy; clicks "Mark reviewed" (good), the panel empties (interval advanced), `GET /me/review` is empty, and the retention API shows the concept `on_track` with 100% recall / ~85% strength, persisting across a dashboard refresh.
2. **`test_p14_again_lapses_and_shows_at_risk`** -- the opposite: clicks "Again", the ladder resets (no longer due) and the retention signal flips to `at_risk`, 0% recall, persisting across refresh.
3. **`test_p14_retention_is_learner_scoped`** -- a brand-new user B sees the empty retention/queue states, and completing user A's schedule with B's token is a 404 with no write (A's interval unchanged).

## 13. Test Results
- **Unit + integration** (`pytest -q tests/unit tests/integration`): **1295 passed** (baseline 1213 at P13; +82 = 67 retention unit + 15 P14 integration), 1 external StarletteDeprecationWarning, 0 failed.
- **PostgreSQL** (`pytest -q tests -m postgres`): **30 passed** (baseline 25; +5 `tests/postgres/test_p14_retention_pg.py` on the real migrated engine, incl. JSONB round-trip + migration-head guard).
- **Browser E2E** (`pytest -q tests/e2e -m e2e`): **21 passed, 0 failed** (baseline 18 + 3 P14; P10 NG-1/2/3 still green after the test-only 4-button wait adjustment).
- **Ruff** (`ruff check .`): **All checks passed** (whole repo, no exceptions; new files ruff-formatted).
- **Mypy** (`mypy app`): **83 errors / 24 files** -- exactly the authoritative P13 baseline, **zero new P14 errors** (verified none of the 83 touch a P14 file).
- **Alembic head**: single head `0033_educational_memories` (unchanged; zero P14 migrations).
- **Secret scan** (Select-String over every P14 new/changed file): **0 hits for real secrets** -- only the deterministic local E2E fixture credentials (`P14Loop1234!`, matching the established `P13Loop1234!` / `P10Loop1234!` pattern). `git diff --check`: clean.

## 14. Known Limitations / Notes
- **Legacy envelope preserved**: the P10 "Mark reviewed" button is now the "good" outcome (first button), so P10 NG-3 and the P11 Today-plan review action keep the exact legacy behavior.
- **Mastery scalar untouched**: P14 never rewrites `quiz_owner` mastery; it only reads it as a fallback anchor and records recall outcomes.
- **P13 seed fix**: the `test_p13_analytics_api.py` edit is test-only (fresh ids/emails for the scoping test) to remove a pre-existing cross-file collision; no product or app behavior changed.
- The retention API is a read surface: it does not (and must not) mutate review state or mastery.

## 15. Exact Commands Used
```
.venv\Scripts\python.exe -m ruff check .                          # All checks passed (whole repo)
.venv\Scripts\python.exe -m mypy app                              # 83 errors / 24 files -- P13 baseline, 0 new in P14
.venv\Scripts\python.exe -m alembic heads                         # 0033_educational_memories (single, unchanged)
.venv\Scripts\python.exe -m pytest tests/unit tests/integration -q # 1295 passed
.venv\Scripts\python.exe -m pytest tests -m postgres -q            # 30 passed
.venv\Scripts\python.exe -m pytest tests/e2e -m e2e -q             # 21 passed
.venv\Scripts\python.exe -m ruff format --check <new files>        # formatted (new files)
# Secret scan (new/changed files): 0 real secrets; only deterministic E2E fixture passwords. git diff --check: clean.
```

## 16. Final Release-Gate Conclusion
All P14 release gates are **GREEN** (`RELEASE-GREEN`):
- The learner records how well they recalled a reviewed concept (`again|hard|good|easy`) and the interval ladder responds deterministically (`again`->tightest, `hard`->hold, `good`->+1, `easy`->+2 capped), all persisted in the existing `review_metadata` JSONB with a bounded (20) history.
- The dashboard now shows a Retention panel: per-concept signal, status chip, retained strength, recall accuracy, and server-built Practice/Ask-tutor deep-links, sorted overdue-first, over a bounded read-only `GET /me/analytics/retention`.
- The review completion API accepts the controlled outcome (optional body; absent === legacy `good`), rejects bad literals with 422, and 404-no-writes on cross-user access.
- Zero new migrations (single alembic head `0033`), zero DB writes to mastery, zero AI/RAG impact.
- SQLite 1295 passed (> P13 1213). PostgreSQL 30 passed (> P13 25). Browser E2E 21 passed (incl. P10 NG-1/2/3, preserved). Ruff clean (whole repo). Mypy 83/24 baseline, zero new P14 errors. Secret scan clean. `git diff --check` clean.
- Observability counters added (`p14_review_outcomes_total`, `p14_retention_views_total`, `p14_retention_errors_total`).
- Committed per the P14 objective once the gate is green.
