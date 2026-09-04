# P11 Scope & Foundation — Personalized Study Plans, Goals & Adaptive Learning Paths

**Status:** PLANNING (audit phase — NO implementation)
**Authoritative implementation contract for P11.**
**Branch target:** `feature/individual-user-foundation`
**Parent of P11:** Post-P10 audit at HEAD `aa2da2f` (this doc + `POST_P10_PRODUCT_ARCHITECTURE_AUDIT.md` + `POST_P10_CAPABILITY_MATRIX.md`)
**Type:** Feature phase — implementation occurs ONLY after this doc is approved.

---

## 1. Recommended P11 Title

**P11 — Personalized Study Plans, Learning Goals & Adaptive Learning Paths**

---

## 2. Why P11 is Next (evidence)

The Post-P10 audit found the platform's **loop is now closed and time-aware**:

- Learn → Understand → Visualize → Practice → Assess → Measure → Review → Remediate → Re-practice → Re-assess → update mastery/review state → next action is **browser-verified** (P10 NG-3; 11/14 transitions CONNECTED, no high-severity break).
- NG-1, NG-2, NG-3 are CLOSED. NG-4/NG-5 were explicitly deferred by the P10 MVP contract.

The single largest remaining product gap is **NG-5 (structure layer)**: the learner has content, lessons, quizzes, mastery, actionable recommendations, a RAG tutor, and spaced review — but **no plan, goal, or path connecting those into a coherent daily program**. A learner who asks "what should I do today?" still has to piece together the dashboard's scattered signals.

The evidence that this is cheap to build well:
- Tables already exist: `learning_paths`, `learning_goals`, `study_plans` (migration `0011`, FKs + full index set).
- Enums already exist: `LearningPathStatus`, `LearningGoalType/Status`, `StudyPlanStatus`, `StudyPlanItemType/Status`, `ReviewScheduleStatus` in `shared/constants/__init__.py`.
- Schemas already exist (orphaned): `personalization.py` (create/response models for paths, goals, study plans, review schedules, personalization overview).
- The live P10 review engine provides due-queue + intervals that a plan can schedule against.
- `learner_progress_service` (read-composition over lessons/sessions/quizzes/memories) provides the query shapes for deterministic plan generation.
- P10 actionability (deep-links to player/tutor/review) means plan items can be real, clickable, and complete-able.

---

## 3. Learner Problem (objective)

**"I don't know what to study today."** The learner has weak concepts, due reviews, and unfinished lessons — but no single, dated, actionable answer to "what should I do next on my path to mastery?" P11 provides exactly that: a deterministic **today's plan** (and a short-horizon study plan), **learning goals** (mastery / lesson-completion / streak targets), and an **adaptive learning path** (ordered lessons by priority) — all driven by the learner's live mastery/review state and fully actionable through the existing player/tutor/review flows.

---

## 4. Current Gap

- No learning path (ordered sequence of lessons the learner should follow).
- No measurable goals (mastery targets, completion targets, streaks).
- No daily/short-term study plan scheduling lessons and due reviews.
- No "today" surface on the dashboard.

---

## 5. User Stories

1. As a learner, my dashboard shows a **"Today" plan**: what to review (due), what to practice (weak/developing), what to learn next (path), each deep-linked to the existing player/tutor/review action. (NG-5 Partial)
2. As a learner, I can **create/activate a learning path** (or the system suggests one from my lessons) and see my position/progress along it. (NG-5)
3. As a learner, I can set **goals** (e.g., master concept X ≥ 85%, finish N lessons, keep a 7-day streak) and see progress auto-updated from real activity. (NG-5)
4. As a learner, generating a **study plan** gives me dated daily items (lesson / review / quiz) for the next 1–7 days; completing an item calls the existing review/mastery flows so state stays consistent. (NG-5)
5. My **mastery/review state remains the single source of truth** — plans/goals/paths are read-compositions over it, never a second scheduler that drifts.

---

## 6. Exact MVP

- **Deterministic study-plan generation**: `GET /me/plan/today` (or a plan engine) producing a bounded list of dated items derived from live state:
  - due reviews (from P10 `review_schedules`),
  - weak + developing concepts (from `educational_memories`),
  - unfinished lessons (from `learning_sessions`/`generated_lessons`),
  each with an existing, validated deep-link (player/tutor/review) and priority.
- **Item completion**: `POST /me/plan/{plan_id}/items/{item_key}/complete` that routes to existing flows (review complete / lesson open / quiz) and updates the plan row — no new scheduler.
- **Goals**: `GET /me/goals`, `POST /me/goals`, `POST /me/goals/{id}/complete` — tracked against mastery/lesson/streak state; progress derived, not manually entered.
- **Learning path**: `GET /me/path` returning an ordered sequence of lessons (mastery-ascending, review-aware) with position/progress; activation is default (single active path per user).
- **Frontend**: a compact "Today / Plan" panel + Goals panel on `dashboard.html` (ride the existing page; no new page required), all dynamic content `escHtml`ed, all CTAs deep-linked like P10.
- **Reuse**: 0011 tables + `personalization.py` schemas + `shared/constants` enums; `learner_progress_service` query shapes; P10 review/service patterns; vanilla frontend.

**Out of MVP (explicit):** AI-written plan narratives, calendar UI, browser notifications, multi-week planning, plan editing UX beyond complete/skip, adaptive assessment (NG-4), analytics dashboards, retention scheduling.

---

## 7. Detailed Scope

### IN SCOPE
- `StudyPlan` / `LearningPath` / `LearningGoal` ORM models over the existing 0011 tables (additive; no new tables unless a plan-item→lesson/review link column proves necessary — prefer JSONB in `study_plans.days`).
- Deterministic plan generator service (read-composition over `review_schedules`, `educational_memory`, `learner_progress`); bounded to a small horizon (1–7 days).
- Goals service with derived progress (mastery target, lesson completion, streak from `educational_memories.streak_days`/`review_count` if present — otherwise from activity rows).
- Learning-path service returning an ordered, mastery-prioritized lesson sequence (reuse `recommendation_engine` priorities).
- `plan` + `goals` routers under `/me/` (list today, complete item, list/create goals, list path). All user-scoped via `get_current_user`, ownership 404-equalized.
- Dashboard "Today / Goals" panel(s) with actionable deep-links + `escHtml`.

### OUT OF SCOPE (rejected, per audit)
- Frontend framework migration.
- 2D editor / content authoring.
- Mobile app.
- Teacher/classroom platform, collaboration/social.
- Microservices / vector-DB / pgvector.
- ML/DL learner model.
- Multi-tenancy / enterprise SSO.
- Autonomous agents / unrestricted AI chat / new AI providers.
- Platform-wide analytics dashboards.
- Genuine adaptive assessment (NG-4) — deferred to a later phase (consumes the same mastery data P11 produces/reads).
- Retention scheduling / global AI cost controls (documented ops debt; separate).

---

## 8. Existing Systems Reused

- `review_schedule_service` / `review_scheduler` (due queue, intervals) — plan "review today" items.
- `educational_memory_service` (concept mastery, weak/developing/mastered, `streak_days`/`review_count` fields) — goal + path state.
- `learner_progress_service` (lesson progress read-composition) — plan "learn next" items + path position.
- `recommendation_engine` (priority ordering) — path ordering and plan prioritisation.
- `generated_lesson` / `learning_session` models — item targeting + completion detection.
- `quiz_attempt_service` / `quiz_repository` — quiz-session completion for goal/plan progress.
- Vanilla frontend (`dashboard.html`, shared `authFetch`, `escHtml`, P10 actionability patterns).
- `personalization.py` schemas + `0011` tables + `shared/constants` enums (currently orphaned — P11 wires them).

## 9. New Systems Required

- `StudyPlanService` (generator + item lifecycle), `LearningGoalService`, `LearningPathService` (deterministic).
- `plan.py` + `goals.py` routers.
- `StudyPlan`, `LearningGoal`, `LearningPath` ORM models (mapping to 0011 tables) + repositories.
- Dashboard "Today / Goals / Path" panel(s) in `dashboard.html`.

---

## 10. API Impact

- New routers (additive): `GET/POST /me/plan/...`, `POST /me/plan/{id}/items/{key}/complete`, `GET/POST /me/goals`, `POST /me/goals/{id}/complete`, `GET /me/path`.
- No changes to existing endpoints' contracts (backward compatible). `/me/progress` and `/me/review` stay authoritative.

## 11. Database Impact

- **Zero or one additive migration.** Reuse 0011 tables if their columns suffice (they appear to — FK to `learning_paths`, JSONB `days`, per-user indexes). If a plan-item→review/lesson anchor is needed and cannot be expressed in JSONB, one additive migration (columns or indexes only, no rewrite).
- **No modification of historical migrations.**

## 12. Frontend Impact

- Add a compact "Today" plan panel, a Goals panel, and a Path strip to `dashboard.html`. All new dynamic content escaped; all CTAs deep-linked (player / tutor / review) using the P10 patterns. No new page required; no build step.

## 13. AI Impact

- **No new AI provider.** Plan/goal/path generation is deterministic. At most an optional AI *summary* behind the existing `AIContentService` (default OFF for the MVP; deterministic text otherwise).

## 14. RAG Impact

- None. Reuse existing semantic RAG only for any optional tutor-suggested items (default OFF in MVP).

## 15. Security Requirements

- Preserve user isolation end-to-end: plans/goals/paths are `user_id`-scoped from auth; ownership 404-equalized; plan items resolve to learner-owned lessons/reviews only.
- `escHtml` for all new dynamic frontend content.
- Prompt-injection boundary unchanged (no new AI surface in MVP).
- No new secrets.

## 16. Performance Requirements

- Plan/today generation is bounded read-composition (≤5 queries, mirroring `learner_progress_service`); exclude N+1 on item assembly.
- Bounded horizons (default 7 days); bounded list sizes.
- No AI on non-user-triggered paths.

## 17. Testing Requirements

- Unit: plan generator (due/weak/unfinished composition, priority order, horizon cap, determinism), goals progress derivation (mastery/lesson/streak), path ordering.
- Integration: user isolation on new endpoints (cross-user plan/goal → 404); plan-item completion routes to existing flows without double-scheduling.
- Preserve all existing gates.

## 18. Browser E2E Requirements

- Extend/parallel the P10 E2E:
  1. Dashboard shows a "Today" panel listing a due review + a weak concept with real deep-links.
  2. Completing a plan review item advances the review interval and updates the panel (state consistency).
  3. Creating/listing a goal reflects real mastery progress.
  4. Path strip lists lessons in priority order and deep-links to the owned player.
  5. P10 NG-3 path still passes (no regression to review loop).

## 19. Acceptance Criteria

- Dashboard "Today" lists due reviews, weak/developing concepts, and next lesson — each an actionable, owned deep-link.
- Completing a plan item updates the underlying review/lesson state (no drift; single source of truth).
- Goals show correctly derived progress (never user-typed).
- A learning path returns a deterministic, mastery-ordered sequence with correct position/progress.
- All plan/goal/path data user-scoped; cross-user access returns 404.
- Full regression contract green.

---

## 20. Checkpoint Structure

| Chk | Objective | Files expected | Tests | Acceptance | Rollback |
|---|---|---|---|---|---|
| C0 | Baseline / contract | none | full regression | gates green | -- |
| C1 | Domain foundation: `StudyPlan`/`LearningGoal`/`LearningPath` ORM over 0011 + repositories | models, repositories | unit: mapping, isolation | reuses 0011; no new table unless proven needed | additive only |
| C2 | Services: plan generator, goals, path (deterministic) | services | unit: composition/order/horizon/determinism | bounded queries, no drift | revert service |
| C3 | API: `plan`/`goals`/`path` routers | api/v1, schemas | int: isolation, 404, completion routing | endpoints user-scoped | remove router |
| C4 | Frontend: dashboard Today/Goals/Path panels | dashboard.html | browser E2E | panels render, escHtml, deep-links work, no XSS | revert JS |
| C5 | Security + isolation tests | tests | security backstop | no cross-user | -- |
| C6 | Browser E2E (plan + goals + path + P10 NG-3 regression) | e2e | 1+ pass | panels actionable; NG-3 intact | revert E2E |
| C7 | Performance (bounded plan generation, no N+1) | service/query | query-count assertions | ≤ bounded queries | -- |
| C8 | Full regression (all gates) | -- | SQLite + PG + mypy + ruff + E2E | contract green | -- |
| C9 | Observability (plan/goal metrics + logs, masked) | observability | -- | metrics present | -- |
| C10 | Regression gate | -- | full suite | ≥ P10 counts | -- |
| C11 | Documentation + report | docs | -- | artifacts present | -- |
| C12 | Release gate + completion commit | -- | all green | final report + clean tree | -- |

## 21. Regression Gates (P11 must hold)

- SQLite: ≥ 1144 passed (0 failed).
- PostgreSQL: ≥ 15 passed.
- Ruff: clean.
- mypy: ≤ 83 errors in app, zero new in P11 files.
- Alembic: single head (unchanged `0031` unless the proven single additive migration is added → exactly one new head).
- Secret scan: clean.
- git diff --check: clean.
- Browser E2E: P7 dashboard, P8 tutor, P9 real-RAG, P10 NG-1/2/3, plus P11 plan/goals/path E2E.
- User isolation: preserved on every new/changed endpoint.

## 22. Risks

- Scope creep into analytics / adaptive assessment / calendar UI (bound to MVP; re-defer).
- Plan/goal/path drift from live mastery (mandate single source of truth; plan derives from, never overrides, mastery/review state).
- Orphaned 0011 schemas not matching the live `review_schedules` shape (validate columns against 0011 before codegen; additive fix if needed).
- mypy floor (zero-new policy).

## 23. Rollback Strategy

Each checkpoint is additive and reversible: new endpoints/models/services can be removed without touching historical migrations; frontend changes are isolated to specific panels; primary rollback is reverting the last checkpoint commit.

## 24. Explicit Non-Goals (P11)

- NO adaptive assessment (NG-4).
- NO AI plan-writing narratives (deterministic text only; AI summary OFF by default).
- NO new AI providers / RAG changes.
- NO frontend framework migration / build step.
- NO new database tables (unless an additive column is proven necessary for plan-item anchors).
- NO calendar, notifications, or multi-week planning UI.
- NO teacher/classroom, collaboration, mobile, 2D editor, microservices, vector-DB, ML model, multi-tenancy, SSO, or analytics dashboards.
- NO change to the existing review/mastery scheduler semantics.
- NO unrelated historical mypy fixes (maintain 83/24 zero-new).

## 25. Definition of Done

- NG-5 (plans/goals/learning paths) reachable in the browser and closed against live mastery/review state.
- Every plan item, goal, and path element is learner-scoped, actionable, and deep-linked.
- Completing plan items routes through existing flows (no state drift).
- All regression gates green; working tree clean; docs committed; P11 report produced.