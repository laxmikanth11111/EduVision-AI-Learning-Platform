# P11 Implementation Report -- Personalized Study Plans, Goals & Adaptive Learning Paths

## 1. Starting Commit
`92c4522` (`docs: add post-p10 product architecture audit and p11 scope`) -- before any P11 implementation work. Branch: `feature/individual-user-foundation`. Working tree was clean at the start of P11.

## 2. Final Commit
Pending -- P11 work is currently an uncommitted scoped change on `feature/individual-user-foundation` at HEAD `92c4522`. This report describes that work; it is ready to be committed as the P11 completion commit once the release gate is signed off.

## 3. P11 Scope
Close the structure-layer gap **NG-5** from the Post-P10 audit: give the learner a coherent, dated, actionable daily program instead of scattered dashboard signals. P11 wires the previously **orphaned** `0011` infrastructure (`learning_paths`, `learning_goals`, `study_plans` tables; `personalization.py` request schemas; `shared/constants` enums) into three deterministic, learner-scoped capabilities:

- **Today Plan** (`/me/plan/today`) -- a dated, bounded list of due reviews + weak/developing practice + next lesson, each deep-linked to the existing player/tutor/review flows, each complete-able through those flows (no state drift).
- **Learning Goals** (`/me/goals`) -- learner-authored targets (mastery / lesson-completion / quiz-score / streak) with progress **always derived server-side** from live state, never client-typed.
- **Adaptive Learning Path** (`/me/path`) -- an ordered, mastery-prioritized sequence of lessons with current position/progress.

All three are **read-compositions over live mastery/review/session state** -- no AI, no ML, no second scheduler, and **zero new database migrations** (reuses the `0011` tables as-is).

Out of scope per the audited contract (still deferred): AI plan-writing narratives, calendar UI, notifications, multi-week planning, plan-edit UX beyond complete, adaptive assessment (NG-4), retention scheduling, analytics dashboards, and any new AI provider / RAG change.

## 4. Checkpoints Completed
| Chk | Objective | Result |
|---|---|---|
| C0 | Baseline / contract (alembic head `0031`, ruff clean, harness green) | PASS |
| C1 | Domain foundation: `StudyPlan` / `LearningGoal` / `LearningPath` ORM over 0011 + repositories | PASS |
| C2 | Services: `StudyPlanService`, `LearningGoalService`, `LearningPathService` (deterministic) | PASS |
| C3 | API: `plan` / `goals` / `path` routers under `/me/` (mount in `main.py`) | PASS |
| C4 | Dashboard panels: Today Plan / Goals / Learning Path in `dashboard.html` (escHtml, deep-links) | PASS |
| C5 | Security / isolation tests (`tests/integration/test_p11_api_security.py`, 5) | PASS |
| C6 | Browser E2E (`tests/e2e/test_p11_plan_goals_path_e2e.py`, 1) + P10 NG-3 regression | PASS |
| C7 | Performance: bounded set-based reads, no N+1 on plan that matters | PASS |
| C8 | Full regression: unit+integration 1161 passed, E2E 13 passed | PASS |
| C9 | Observability: P11 metrics counters added (`p11_*`) | PASS |
| C10 | Regression gate (≥ P10 counts, zero failures) | PASS |
| C11 | This report + docs | PASS |
| C12 | Release gate + completion commit | PENDING (commit withheld until user requests) |

## 5. Files Changed (P11)
New:
- `app/models/learning_path.py` (`path_` public prefix), `app/models/learning_goal.py` (`goal_`), `app/models/study_plan.py` (`plan_`) -- ORM over the 0011 tables (UUIDMixin/TimestampMixin + `JSON().with_variant(JSONB())` columns).
- `app/repositories/learning_path_repository.py` (find_active), `learning_goal_repository.py` (list_by_user, get_by_user_and_public_id), `study_plan_repository.py` (find_active_for_date, list_active).
- `app/schemas/plan.py` -- P11 response schemas (TodayPlanResponse, PlanItem, PlanItemCompleteResponse, GoalsResponse/LearningGoalView/GoalCreateResponse/GoalCompleteResponse, PathLesson/LearningPathView/LearningPathCreateResponse).
- `app/services/study_plan_service.py`, `learning_goal_service.py`, `learning_path_service.py` -- deterministic services.
- `app/api/v1/plan.py` (`/me/plan/today`, `/me/plan/today/items/{key}/complete`), `goals.py` (`/me/goals`, `/me/goals/{id}`, `/me/goals/{id}/complete`), `path.py` (`/me/path`).
- `tests/unit/test_p11_plan_goals_path_service.py` (12), `tests/integration/test_p11_api_security.py` (5), `tests/e2e/test_p11_plan_goals_path_e2e.py` (1).

Modified:
- `app/main.py` (mount 3 routers), `app/models/__init__.py` (register new models), `app/observability/metrics.py` (P11 counters).
- `frontend/dashboard.html` (Today Plan / Goals / Learning Path panels + CSS).
- `tests/e2e/test_p10_adaptive_review_e2e.py` (scoped a selector to the review panel so the new P11 plan buttons -- also `reco-btn` -- never collide on the shared dashboard; requested by the release gate's "P10 NG-3 still passes" criterion).
- `app/schemas/personalization.py` -- **unchanged** (its `LearningPathCreateRequest` / `GoalCreateRequest` are reused as-is, wiring the orphaned schemas).

**Zero new database migrations.** Alembic single head remains `0031_review_schedule_concept`.

## 6. Design Decisions

### Today Plan composition (deterministic)
The plan is recomposed fresh on every read so it never drifts from learner truth. Composition order is fixed and documented:

```
overdue reviews → reviews due today → weak-concept practice → current lesson → developing-concept practice
```

- **Reviews** come from the authoritative `ReviewScheduleService.list_due` (the single spaced-repetition queue, including its lazy seeding) -- capped `_MAX_REVIEWS = 100`.
- **Practice** = weak/developing concepts (mastery < 85) from educational memory that are **not already covered by a due review today**, capped `_MAX_PRACTICE = 5`. **Design note (deliberate simplification):** practice selection was simplified from "active schedules not yet due" to "weak/developing concepts not covered by today's due reviews" -- both upcoming and unscheduled concepts are included, keeping the plan a pure read-composition with no second scheduling decision.
- **Current lesson** comes from a single `LearningPathService.get_path` read (the authoritative current position).

Every item carries an existing validated `deep_link` (`/frontend/player.html?lesson=...` or `/frontend/tutor.html?concept=...`), mirroring the P10 actionability contract.

### Item completion (no state drift)
- **Review items** (`review.<schedule_id>`) route through `ReviewScheduleService.complete` (advances interval 1d→3d, item leaves the due queue) -- verified in the browser E2E via the review API.
- **Lesson/practice items** are sticky done-marks in the single-day `study_plans.days` JSONB (idempotent; replay returns "Already completed").

### JSONB datetime serialization (real production fix)
Pydantic `PlanItem.due_at` is a `datetime`, which cannot be stored directly in a SQLite JSON column. `_plan_item_dict(item)` in `study_plan_service.py` converts `due_at` to an ISO string before persisting to the `days` JSONB -- this was a genuine failure caught early and fixed.

### Learning path ordering
Deterministic order key = `(tier, weakest concept mastery asc or _UNKNOWN_MASTERY=101.0, created_at timestamp, public_id)` where tier is `0=not_started, 1=in_progress, 2=completed`. `current_position` = 1-based index of the first non-completed lesson. Exactly one active path per learner; `get_path` auto-creates/reconciles on first read; `create_path` archives any prior active path. Lesson set = owned lessons UNION lessons the learner has sessions on.

### Goals derivation (never client-typed)
| type | derived from |
|---|---|
| `mastery_target` | `profile.average_mastery` |
| `lesson_completion` | `COUNT(DISTINCT learning_sessions.lesson_id)` where completed |
| `quiz_score` | `MAX(percent_score)` where `completed_at` not null |
| `streak_days` | `profile.streak_days` |

Unsupported types → `ValidationError`. Auto-achieve on read when progress ≥ 100%; `complete_goal` → `ConflictError` (409) if < 100%, idempotent once achieved.

## 7. User Isolation / Security
All new endpoints resolve `user_id` exclusively from `get_current_user` (auth context) -- never client-supplied. Cross-user goal/path/plan reads and plan-item completion are **404-equalized**. Verified via `tests/integration/test_p11_api_security.py`: 401 unauthenticated on all six endpoints; owner can read path/plan/goals; User B reading/completing User A's goal → 404; `complete_goal` on an unmet target → 409 then achievable; plan-item completion is learner-scoped (A 200, B → 404).

Frontend: all new dynamic content is `escHtml`-escaped and all CTAs are server-built `deep_link` hrefs (no XSS / no dead links).

## 8. Performance / Bounded Queries
All three services use bounded, set-based queries (no N+1 on the hot plan-read path):
- **Path** (`_resolve_lesson_states`): 4 bounded queries (owned lessons, sessioned lessons, that user's sessions, concept→lesson map) + the cached memory load.
- **Plan**: `ReviewScheduleService.list_due` (bounded ≤ 100) + one batched concept→lesson map + one path read.
- **Goals**: aggregate SQL (`COUNT(DISTINCT ...)`, `func.max`) per derivation. Note: `list_goals` refreshes each goal O(n) where n = the learner's goal count -- bounded by the small number of goals a learner holds, acceptable and documented.

No AI on any read path. Deep-links are server-built and validated.

## 9. Observability
Added P11 counters to `app/observability/metrics.py`, incremented in the services:
- `p11_plan_reads_total`, `p11_plan_items_completed_total` (by item type / idempotency),
- `p11_goal_reads_total`, `p11_goals_created_total` (by type), `p11_goals_completed_total` (by outcome),
- `p11_path_reads_total` (by lesson count).

All rendered by the existing `GET /api/v1/metrics` Prometheus endpoint.

## 10. Database Impact
**Zero.** No migration, no new table, no column change. The 0011 tables were validated against the live ORM and reused as-is. Alembic single head unchanged: `0031_review_schedule_concept`.

## 11. AI / RAG Impact
None. Plan/goal/path generation is fully deterministic; no AI provider was added and no RAG path was touched. Prompt-injection boundary unchanged.

## 12. Browser E2E Flow
Playwright + system Chrome against a real uvicorn server (real sign-in, vanilla `backend/frontend/`). `tests/e2e/test_p11_plan_goals_path_e2e.py` (`test_p11_dashboard_plan_goals_path`) closes the loop in the browser:

1. Register a learner, seed a lesson + in-progress session + weak concept + overdue review + memory (DB only for deterministic seeding).
2. Create a goal via the real API (mastery target above current → shown in progress, not achieved).
3. Dashboard shows: Today Plan (Review + Continue lesson, both real deep-links), Learning Path (loops the seeded lesson, `player.html` deep-link), Goals (derived progress, "in progress").
4. **Complete the review through the plan UI** → routes through P10 → verified via the review API that the schedule exited the due queue.
5. **Complete the lesson through the plan UI** → sticky "done" state → verified via the plan API.
6. P10 NG-3 regression **still passes** (see the `test_p10_adaptive_review_e2e.py` selector-scoping note in §5).

Result: **1 passed** for the new P11 E2E; full E2E suite **13 passed** (`pytest -m e2e`).

## 13. Test Results
- **Unit + integration** (`pytest -q tests/unit tests/integration -m "not postgres"`): **1161 passed** (was 1144 at P10 baseline; the +17 are the new P11 unit + security tests), 1 external StarletteDeprecationWarning, 0 failed.
- **PostgreSQL** (`pytest -q tests -m postgres`): **15 passed** (migration parity + jsonb columns against `postgres:16-alpine`; unchanged from P10).
- **Browser E2E** (`pytest -m e2e`): **13 passed, 0 failed** (P7 dashboard + P8 tutor + P10 NG-1/2/3 + P11 + smoke).
- **Ruff** (`ruff check .`): **All checks passed** (whole repo, no exceptions).
- **Mypy** (`mypy app`): **83 errors / 24 files** -- exactly the authoritative P10 baseline, **zero new P11 errors** (the two P11 service files were type-annotated to hold the floor: `StudyPlan.days` declared as `dict[str, list[dict[str, Any]]]`, `target_date` typed `date | None`).
- **Alembic head**: single head `0031_review_schedule_concept` (unchanged; zero P11 migrations).

## 14. Known Limitations / Notes
- **JSONB datetime serialization** was a real failure caught and fixed during development (`_plan_item_dict`); it is now handled and covered by tests.
- **Practice-selection simplification** (upcoming + unscheduled weak/developing concepts, rather than only "not-yet-due active schedules") is a deliberate, documented choice to keep the plan a pure read-composition.
- **Goal-list refresh** is O(n) in the learner's goal count (one aggregate per goal); acceptable at typical goal counts.
- The P10 E2E selector fix is a test-only scope change (review-panel buttons now scoped to `#reviewPanelBody`) made necessary because the P11 plan panel legitimately adds more `reco-btn` buttons to the shared dashboard; it enforces the NG-3 no-regression gate.

## 15. Exact Commands Used
```
.venv\Scripts\ruff.exe check .                                # All checks passed (whole repo)
.venv\Scripts\python.exe -m mypy app                          # 83 errors / 24 files -- authoritative P10 baseline, 0 new in P11
.venv\Scripts\python.exe -m alembic heads                     # 0031_review_schedule_concept (single, unchanged)
.venv\Scripts\python.exe -m pytest tests/unit tests/integration -q -p no:cacheprovider   # 1161 passed
.venv\Scripts\python.exe -m pytest tests -m postgres -q -p no:cacheprovider              # 15 passed
.venv\Scripts\python.exe -m pytest tests/e2e -m e2e -q -p no:cacheprovider              # 13 passed
# Secret scan (Select-String over every P11 new/changed file): 0 hits.
```

## 16. Final Release-Gate Conclusion
All P11 release gates are **GREEN**:
- NG-5 (plans/goals/learning paths) reachable in the browser and closed against live mastery/review state.
- Every plan item, goal, and path element is learner-scoped, actionable, deep-linked, and `escHtml`-escaped.
- Completing plan items routes through existing flows (review → P10 interval advance; lesson/practice → sticky done) -- no state drift, single source of truth preserved.
- User isolation verified (cross-user → 404) on all new endpoints.
- Deterministic, no AI / no new AI provider / no RAG change / no new scheduler.
- **Zero new migrations** (single alembic head `0031`).
- SQLite regression 1161 passed (> P10 1144). PostgreSQL regression 15 passed. Browser E2E 13 passed (incl. P10 NG-3). Ruff clean (whole repo). Mypy 83/24 baseline, zero new P11 errors.
- Observability counters added. Secret scan: none added. git diff --check: clean.
- Completion commit pending user request (git commit is not performed unless explicitly asked).
