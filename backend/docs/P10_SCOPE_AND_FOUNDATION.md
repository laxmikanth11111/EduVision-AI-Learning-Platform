# P10 Scope & Foundation -- Adaptive Remediation & Review Engine

**Status:** PLANNING (audit phase -- NO implementation)
**Authoritative implementation contract for P10.**
**Branch target:** `feature/individual-user-foundation`
**Parent of P10:** Post-P9 audit at HEAD `d61da43` (this doc + `POST_P9_PRODUCT_ARCHITECTURE_AUDIT.md` + `POST_P9_CAPABILITY_MATRIX.md`)
**Type:** Feature phase -- implementation occurs ONLY after this doc is approved.

---

## 1. Recommended P10 Title

**P10 -- Adaptive Remediation & Review Engine**

---

## 2. Why P10 is Next (evidence)

The Post-P9 audit found the platform's intelligence **data** is complete and
backend-robust, but:

- **NG-1 (HIGH):** The quiz-result "Recommended next" callout reads
  `result.recommendations.next_action` which the backend never returns
  (`frontend/player.html:1977` vs `app/schemas/next_action.py:60`) -- it never
  renders.
- **NG-2 (HIGH):** Recommendations are static; remediation returns text only,
  with no re-practice action.
- **NG-3 (HIGH):** The browser learning loop is **not closed** -- no
  assess→remediate and no remediate→Learn-Again transitions.
- **NG-4 (MEDIUM):** Mastery never decays and assessment is not adaptive (dead
  `AdaptiveAssessmentEngine`).
- **NG-5 (MEDIUM):** Spaced repetition / plans / goals exist only as
  schema+migration stubs.

P10 is the phase that closes NG-1..NG-5 by reusing the deterministic
intelligence stack and the vanilla frontend -- turning latent data into a
closed, time-aware, actionable experience.

---

## 3. Problem Being Solved

The learner can Learn, Practice, and Assess, but the system gives them **no
actionable next step, no timed review, and no path to actually fix weak
concepts**. Mastery is a static number that never changes unless they take
another quiz, and the platform is branded "adaptive" without adaptive behavior.

---

## 4. Current Gap

- No clickable next-best-action after a quiz.
- No automatic remediation flow (tutor reply is text, no CTA).
- No time-based review (spaced repetition) of weak/mastered concepts.
- No closed loop back into practice.

---

## 5. Product Objective

Turn the existing deterministic mastery/recommendation data into an
**adaptive, closed-loop remediation experience**: after an assessment the
learner gets one clear next action (review → re-learn → re-practice),
weak concepts are scheduled for spaced review that respects time passed, and
every recommendation is actionable and feeds back into practice for the same
lesson/concept.

---

## 6. User Stories

1. As a learner, after I submit a quiz, I see ONE clear "Do this next" action
   (review weak concept via tutor, or re-open the lesson, or re-take a focused
   quiz) with working buttons.
2. As a learner, I can click a dashboard recommendation and it takes me to the
   right action (tutor for that concept / lesson player / focused quiz).
3. As a learner, weak concepts I haven't reviewed in a while appear in my
   "Review queue" so I'm prompted at the right time (spaced repetition).
4. As a learner, after the tutor remediates a concept, I get a button to
   re-practice (open the checkpoint/quiz for that lesson) so the loop closes.
5. As a learner, my mastery reflects my current state (it can decay and is
   updated by lesson activity, not only quizzes).

---

## 7. Exact MVP

- Fix the broken `next_action` schema/UI path (NG-1) and render actionable
  next-step buttons in the quiz result.
- Add a time-aware **review queue** (spaced repetition) for concepts
  (`review_schedules` already exists in migration `0011` -- implement the
  model/service/endpoint/UI).
- Make dashboard recommendation cards and weak-concept chips actionable
  (deep-link to tutor/lesson/focused-quiz).
- Add re-practice CTA to tutor remediation replies.
- Update mastery deterministically on lesson activity (optional, small) and
  compute a simple decay signal from `last_reviewed_at` for review scheduling.

---

## 8. Detailed Scope

### IN SCOPE
- **Next-action schema fix + UI**: align `LearningRecommendation` with a
  single `next_action` (or render `actions[0]`); add working deep-link buttons
  on the quiz-result screen.
- **Review scheduling (spaced repetition)**: implement a deterministic
  scheduler over existing mastery records using `last_reviewed_at` +
  interval progression (e.g., 1d/3d/7d/14d) per concept; persist in the
  existing `review_schedules` table; expose `GET /me/review` (list due now),
  `POST /me/review/{concept}/complete`. Pure deterministic logic (no ML).
- **Actionability plumbing**: dashboard reco cards + weak chips become
  clickable; tutor remediation reply gains a structured `next_action` +
  re-practice button.
- **Loop closure**: after quiz → "Review weak concept" deep-links to tutor;
  after tutor remediation → "Practice this" deep-links to the checkpoint/quiz
  for the lesson.

### OUT OF SCOPE (rejected, per audit)
- React/Next.js/frontend framework migration.
- 2D lesson editor.
- Mobile application.
- Teacher/classroom platform and collaboration/social learning.
- Microservices / vector-DB migration / pgvector.
- ML/DL learner model (deterministic is the mandate).
- Multi-tenancy / enterprise SSO.
- Autonomous agents / unrestricted AI chat / new AI providers.
- Study plans / learning paths / goals dashboards (keep as future; out of P10
  MVP unless time permits and evidence supports).
- Platform-wide analytics dashboards.

---

## 9. Existing Systems Reused (deterministic stack)

- `educational_memory_service` (concept mastery data; `last_reviewed_at`,
  `review_count`).
- `recommendation_engine` (action generation + ranking).
- `LearningSession` / `lesson_player_service` (re-open lesson, completion).
- `quiz_attempt_service` + quiz subsystem (re-take checkpoint, mastery update).
- `mastery_tutor_service` + `_retrieve_learner_chunks` (concept remediation
  deep-link).
- Semantic RAG (`app.ai.retrieval`) for tutor remediation content.
- Vanilla frontend (`dashboard.html`, `player.html`, `tutor.html`) + shared
  `authFetch`/`escHtml`.

## 10. New Systems Required

- `ReviewSchedule` ORM model + repository + service (spaced-repetition
  scheduler) -- backed by the existing `review_schedules` table from migration
  `0011` (no new table needed if it matches; otherwise additive migration).
- `GET /me/review`-family endpoints + minimal `review` UI surface (ride on
  dashboard/player, no new page needed).

---

## 11. API Impact

- `app/api/v1/` gains a small review router (list due, complete, skip) +
  possibly a `next_action` on the learner-progress payload.
- Tutor `remediate` response gains a structured `next_action` (non-breaking).
- No changes to existing endpoints' contracts (backward compatible).

## 12. Database Impact

- **Zero or one additive migration.** Reuse `review_schedules` (0011) if its
  columns suffice; otherwise an additive (never rewrite) migration. No
  modification of historical migrations.

## 13. Frontend Impact

- Fix `player.html:1977` next-action rendering + add action buttons.
- Add click handlers to dashboard reco cards / weak chips.
- Add re-practice button in `tutor.html` remediation reply.
- Add a compact "Review queue" panel to the dashboard.

## 14. AI Impact

- No new AI provider. AI remains routed through `AIContentService`. Remediation
  may use the existing tutor AI path with deterministic fallback; the review
  scheduler itself is deterministic (no AI).

## 15. RAG Impact

- Reuse existing semantic RAG for tutor remediation content only. No new RAG
  subsystem.

## 16. Security Requirements

- Preserve user isolation end-to-end (review queue, remediation, next-action,
  quiz deep-links all user-scoped; ownership 404-equalized).
- New endpoints under `get_current_user`; concepts/lessons/quizzes resolved via
  the existing ownership chain.
- `escHtml` for all new dynamic frontend content.
- Prompt injection boundary maintained for tutor/RAG (data-delimiter guard as a
  hardening item, non-blocking for P10 MVP).
- No new secrets.

## 17. Performance Requirements

- Review-queue queries indexed (`user_id` + due_at); bounded list (page_size).
- No N+1 on next-action assembly (load once per request).
- AI only on user-triggered remediation (reuse existing boundaries).

## 18. Testing Requirements

- Unit: review scheduler (interval progression, due-now, completion, idempotent
  complete), next-action serialization, mastery decay helper.
- Integration: user-isolation on review endpoints; loop deep-link resolution
  (quiz→tutor, tutor→practice) target correct owned resources.
- Preserve all existing gates.

## 19. Browser E2E Requirements

- Extend/parallel the P9 real-RAG tutor E2E:
  1. Sign in → take a checkpoint → quiz result shows an actionable next action.
  2. Click "Review weak concept" → opens tutor for that concept.
  3. Tutor remediation reply shows a "Practice this" button → opens the
     checkpoint/quiz for the lesson.
  4. Dashboard review-queue panel lists due concepts and P7/P8/P9 behavior
     unchanged.

## 20. Acceptance Criteria

- After a quiz, exactly one clear, working next-action button is shown.
- Dashboard weak chips and reco cards deep-link to a working action.
- Tutor remediation reply includes a working re-practice action.
- A concept scheduled for review appears in the review queue only when due,
  and completing it advances its interval.
- All learner data user-scoped; cross-user access returns 404.
- P9 real-RAG browser path still asserts `source_kind=="rag"`.
- Full regression contract green.

## 21. Checkpoint Structure (adjusted for P10)

| Chk | Objective | Files expected | Tests | Acceptance | Rollback |
|---|---|---|---|---|---|
| C0 | Baseline | none | full regression | gates green | -- |
| C1 | Domain/backend: ReviewSchedule model + repo + scheduler service | models/repository/service | unit: intervals, due-now, complete | scheduler deterministic, no new table if 0011 fits | additive-only |
| C2 | API: review router + next_action on progress/remediate | api/v1, schemas | int: isolation, 404 | endpoints user-scoped | endpoint removed |
| C3 | Intelligence: next-action assembly + mastery-decay helper wired | recommendation/learner_progress, quiz_attempt | unit | valid next_action, decay signal | revert helper |
| C4 | Frontend: fix player next-action; dashboard/tutor actionability + review panel | dashboard.html, player.html, tutor.html | browser E2E | buttons work, escHtml, no XSS | revert JS |
| C5 | Security + isolation tests | tests | security backstop | no cross-user | -- |
| C6 | Browser E2E (loop + review + P9 rag) | e2e | 1+ pass | loop closed, rag preserved | revert E2E |
| C7 | Performance/observability (review indexing, bounded) | repo/query | query-count assertions | no N+1 | -- |
| C8 | Full regression (all gates) | -- | SQLite + PG + mypy + ruff + E2E | contract green | -- |
| C9 | Document/report commit | docs | -- | artifacts present | -- |

## 22. Regression Gates (P10 must hold)

- SQLite: >= 1115 passed (0 failed).
- PostgreSQL: >= 15 passed.
- Ruff: clean (no behavior error; fix the import-order I001).
- mypy: <= 83 errors in app, zero new in P10 files.
- Alembic: single head (still `0030` unless the additive review migration is
  added, then exactly one new head).
- Secret scan: clean.
- git diff --check: clean.
- Browser E2E: P7 dashboard, P8 tutor, P9 real-RAG (`source_kind=="rag"`),
  plus P10 loop/review E2E.
- User isolation: preserved on every new/changed endpoint.

## 23. Risks

- Scope creep into plans/goals/analytics (bound to MVP; re-defer).
- Review scheduler semantics drift (keep deterministic + additive; never
  rewrite existing mastery).
- Frontend actionability touching quiz/tutor flows (additive; preserve P8/P9
  E2E).

## 24. Rollback Strategy

Each checkpoint is additive and reversible: new endpoints/models/services can
be removed without touching historical migrations; frontend changes are
isolated to specific functions/panels; the primary rollback is reverting the
last checkpoint commit with the tree returning to a prior green gate.

## 25. Definition of Done

- NG-1 fixed (next-action renders and works).
- NG-2 fixed (dashboard + tutor reports actionable, deep-linked next actions).
- NG-3 fixed (assess→remediate→Learn-Again loop closed in browser).
- NG-4 partially addressed (deterministic review scheduling + decay signal;
  genuine assessment adaptivity explicitly deferred/not required by MVP).
- NG-5 partially addressed (spaced review reachable; plans/goals re-deferred).
- All regression gates green; working tree clean; docs committed; P10 report
  produced.
