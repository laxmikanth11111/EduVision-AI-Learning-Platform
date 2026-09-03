# P7 — Learner Intelligence & Adaptive Progress — Scope and Foundation

Status: **PLANNING DOCUMENT (decision)** — the authoritative P7 scope. Approved
implementation begins only after this document is reviewed and explicitly
approved.

Baseline at planning time: `8c82a2c` (post-P6 release), working tree clean.

---

## 1. P7 Name

**Learner Intelligence & Adaptive Progress**

One phase that unifies **Adaptive Learner Intelligence (A)** and the **Learner
Analytics + Progress Dashboard (B)**, because they share the same data
foundation and the same missing artifact (a learner-facing surface).

## 2. Objective (one sentence)

Surface EduVision's already-built, already-persisted, deterministic learner
intelligence — concept mastery, weak/strong concepts, prioritized next-best
actions, attempt history, and progress trends — as a coherent, learner-scoped
progress view across lessons, in the existing vanilla SPA.

## 3. Problem Statement

The learner's data is rich and complete (mastery, recommendations, attempts,
events), but the learner cannot see it. The only intelligence surface is a
lesson-scoped sidebar panel showing one progress bar, one checkpoint chip, one
score, and one next-action. There is **no dashboard page**: no cross-lesson
progress, no mastery breakdown, no weak/strong concepts, no history, no trends.
The product's intelligence is invisible.

## 4. Product Hypothesis

If the learner can see their overall mastery, weak/strong concepts, and a
prioritized next-best action across lessons (rather than a single in-lesson
hint), they will stay oriented, know what to study next, and complete more of
their learning loop — turning existing deterministic intelligence into learner
value with no new AI.

## 5. Target Learner Experience

1. Sign in → land on a **Progress page** (`dashboard.html`).
2. See **overall progress**: lessons completed / in progress, average mastery,
   mastered/developing/weak concept counts.
3. See **mastery breakdown**: per-concept mastery (already computed by the
   recommendation/educational-memory layer).
4. See **weak & strong concepts** (already computed by effectiveness report +
   educational memory).
5. See **prioritized next-best actions** (the deterministic recommendation
   engine's full queue, not just one).
6. See **recent assessment performance** and **attempt history** (existing quiz
   attempt data).
7. See **progress/performance trend** across lessons (computed from existing
   sessions/attempts/events).
8. Click into a lesson to resume; the player journey panel continues to work as
   today (P5/P6 preserved).

## 6. MVP Scope

- **Frontend**: new `backend/frontend/dashboard.html` (or a dashboard view)
  in the existing vanilla-SPA pattern, plus dashboard navigation from
  `index.html`/`upload.html`.
  - Overall progress + mastery summary (counts + average).
  - Concept mastery list (weak/developing/mastered).
  - Weak/strong concept panels.
  - Prioritized next-best-action list (reuse deterministic engine).
  - Recent attempts + scores.
  - Basic trend (e.g., score over recent attempts).
- **Backend**: one new **learner-scoped, read-only aggregate** endpoint (e.g.,
  `GET /me/progress` or `/learner/dashboard`) that composes existing
  `educational_memory_service` + `recommendation_engine` + quiz-attempt +
  session/event queries. Ownership enforced with the same patterns as
  `lesson_player_service`.
- **Reuse**: do NOT create a new analytics engine. Compose existing services.
- **Tests**: unit (aggregate composition), integration + 2-user isolation,
  Postgres, and a browser E2E that signs in, opens the dashboard, and sees
  mastery/recommendations per the deterministic seed. Deterministic — no AI.

## 7. Explicit Exclusions (non-MVP / out of P7)

- New AI providers, ML training, vector-DB migration, recommendation algorithm
  redesign. The engine is already deterministic and correct.
- Advanced visual learning (Candidate C), mastery-aware tutor UI (D), 2D
  editor (E), teacher analytics product (F), framework migration (G),
  knowledge graph (H).
- Full research/study analytics UI (baseline/post/retention cohort views,
  group comparison) — those remain backend/researcher surfaces, not the learner
  dashboard.
- A new data warehouse / event bus / distributed cache / microservices.

## 8. Architecture Design

Direction (matching the task's preferred non-destructive path, and supported by
repository evidence):

```
existing learner activity (learning_events/sessions)
      → existing assessment attempts (quiz_attempts/question_attempts)
      → existing concept mastery (educational_memories)
      → existing learner state (average + mastered/developing/weak)
      → existing deterministic recommendation_engine
      → NEW learner-scoped aggregate endpoint (composes existing services)
      → NEW dashboard.html surface (vanilla SPA)
```

No new database engine, no new AI provider, no framework change. The backend
intelligence layer is reused verbatim.

## 9. Existing Components Reused

- `educational_memory_service` (load_from_db, update_concept_mastery, cached).
- `recommendation_engine.generate_recommendations` (deterministic NextActions).
- `lesson_player_service.get_mastery_and_next_action` shape (counts, mastery map,
  next_action) — the dashboard generalizes this to cross-lesson.
- Quiz attempt/score query paths (`quiz_attempt_service`, list-attempts).
- `LearningSession` for progress/resume; `learning_events` for activity/trend.
- `effectiveness` report weak/strong concepts.
- Frontend `authFetch`, existing CSS/JS conventions, `node --check` validation.

## 10. New Components Required

- Backend: one learner-scoped aggregate service + router endpoint
  (and its DTO/schema).
- Frontend: `dashboard.html` + JS functions; small nav wiring in
  `index.html`/`upload.html`.

## 11. Database Impact

- **No new migration is required for the MVP** — every required field exists
  (educational_memories, quiz_attempts, question_attempts, learning_sessions,
  learning_events, concepts). Reindex only if benchmarks show a need.
- **TO BE DETERMINED (do not create now):** only if the MVP later wants a
  pre-aggregated trend/analytics table would a migration be justified. Document
  the rationale before adding; single Alembic head must be preserved.

## 12. API Impact

- Add `GET /me/progress` (name TBD at C1) — learner-scoped, read-only.
  - Returns: lessons_completed/in_progress, average_mastery,
    mastered/developing/weak counts, per-concept mastery, weak/strong lists,
    prioritized actions, recent attempts, trend series.
  - Must 404/403 cross-user access exactly like existing ownership.
- No change to existing player/quiz routes (preserve P5/P6).

## 13. Frontend Impact

- New dashboard page in vanilla JS (consistent with existing SPA).
- Reads via `authFetch`; renders progress, mastery, weak/strong, actions,
  attempts, trend. No framework, no build step.
- Existing `player.html` journey panel unchanged.

## 14. AI Impact

- **None required.** All surfaced intelligence is deterministic. If a natural
  language summary is ever desired, it is a DEFERRED enhancement, not MVP.

## 15. Security Model

- Every aggregate query is `WHERE user_id = current_user.id`.
- Reuse `get_current_user` and the service-level ownership assertion pattern.
- No client-provided ownership authority.
- Cross-user isolation tests (User B must get 404/empty for User A's data).

## 16. Performance Considerations

- The dashboard is per-user and indexed by `user_id`; small cardinality.
- Respect the existing bounded-cache for educational memory.
- Aggregate with set-based queries to avoid N+1 (limit recent attempts, cap
  trend window).

## 17. Test Strategy

- **Unit**: aggregate/service composition (deterministic, given seeded memory/
  attempts). Reuse `test_recommendation_engine` fixtures.
- **Integration (SQLite fast)**: dashboard endpoint returns expected summary;
  empty-state; user isolation (2 users); malformed/foreign access.
- **Postgres**: dashboard endpoint against PostgreSQL.
- **Security**: cross-user 404/403 for dashboard.
- **Regression**: existing fast 1076 + PG 15 + e2e 7/7 preserved.

## 18. Browser E2E Strategy

- One new E2E (`tests/e2e/test_p7_dashboard.py`): seed a succeeded lesson +
  quiz attempt + mastery via synchronous test session; sign in via real form;
  open dashboard; assert mastery counts, weak/strong, next actions, attempt
  history, and a value into a lesson from the dashboard. Deterministic — no AI.

## 19. Checkpoints

| ID | Objective | Implementation boundary | Tests | Acceptance | Exit gate |
|----|-----------|--------------------------|-------|------------|-----------|
| C0 | Baseline / repository verification | verify HEAD `8c82a2c`, clean tree | git status/log | baseline intact | clean tree |
| C1 | Aggregate service + endpoint | backend aggregate service + `GET /me/progress` (or named per plan) | unit + integration + PG + 2-user isolation | endpoint returns learner-scoped summary deterministically | tests pass |
| C2 | Determine migration need | verify no migration needed; document if TBD | alembic heads | single head, no new migration for MVP | head unchanged |
| C3 | Dashboard frontend | `dashboard.html` + nav; renders summary/mastery/weak-strong/actions/attempts/trend | JS `node --check` | page loads data from aggregate endpoint | no JS errors |
| C4 | Security + integration tests | cross-user isolation for dashboard | integration security tests | User B cannot read User A dashboard | tests pass |
| C5 | Browser acceptance | full dashboard E2E | e2e `test_p7_dashboard.py` | sign in → dashboard shows seeded mastery/actions/history | E2E passes (repeat ≥3) |
| C6 | Regression + release gate | full suite | fast + PG + e2e + ruff + mypy + alembic + diff check + secret scan | baselines preserved (1076/15/7/83) | green |

## 20. Regression Contract

Preserve: PostgreSQL prod DB · SQLite test path · single Alembic head ·
P0 security/ownership · P1 isolation fixes · P2 data/runtime · P3 hardening ·
P4 bounded caches/browser foundation · P5 persistent learner journey · P6
interactive assessment · existing browser E2E · RAG ownership · health/
readiness · observability · CI/static checks.

## 21. Definition of Done

- Learner can see, in a real browser, their cross-lesson progress, mastery
  (weak/strong), prioritized next actions, and attempt history.
- Dashboard is learner-scoped (User B cannot see User A's data).
- No new migration introduced unless C2 documents a justified need.
- Regression gates: fast SQLite (baseline 1076, +new), PG (baseline 15, +new),
  e2e (7 + new), Ruff clean, mypy zero-new vs baseline 83, single Alembic head,
  secret scan clean, `git diff --check` clean, working tree clean.
- Docs updated.

## 22. Risks

- Scope creep toward a full analytics platform → keep learner-scoped MVP.
- N+1 aggregation → cap queries, set-based.
- Cross-user leak → reuse ownership pattern + 2-user tests (high priority).
- Drift into AI/heavy dashboard → deterministic only.

## 23. Rollback Strategy

- P7 is additive (new endpoint + new page + tests). Rollback = revert the P7
  commit; existing player/quiz paths unchanged. No data-migration rollback
  needed (no schema change in MVP).

## 24. Future Extensions (deferred, not P7)

- Mastery-aware tutor/remediation UI (Candidate D).
- Richer adaptive visuals (Candidate C).
- Teacher/instructor analytics (Candidate F).
- Trend pre-aggregation table (migration) if scale demands.
- Natural-language learner summary (AI, gated).

## 25. Why This Is the Correct Next Phase

1. **Biggest product gap** — the learner cannot see their own progress/mastery/
   history/trends; only lesson-scoped hints.
2. **Maximal readiness** — mastery, educational memory, and the deterministic
   recommendation engine already exist and are tested; only a surface + small
   aggregate endpoint is missing.
3. **Lowest risk / cost** — no AI, no migration (MVP), no framework change, no
   new infra; fully deterministic and testable.
4. **Best value-for-effort** — options C/D/E/F/H require new backend capability,
   larger scope, or higher risk with no proportional learner value now; G is
   an architectural investment, not learner value.
5. **Architecture preserved & non-destructive** — follows the preferred
   EXISTING DATA → MASTERY → RECOMMENDATION → NEW SURFACE path.

---

This is a planning document only. **No P7 implementation was started.**
