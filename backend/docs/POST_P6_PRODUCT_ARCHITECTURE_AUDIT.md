# Post-P6 Product + Architecture Audit

Status: **AUDIT / DECISION ONLY — No Implementation**

Author: Senior Product + Architecture Audit (staff backend, security, frontend,
QA, release). All conclusions are traceable to repository evidence at the
post-P6 checkpoint.

---

## 1. Executive Summary

EduVision AI is a well-architected FastAPI monolith (PostgreSQL, SQLite test
path, RAG, bounded caches, deterministic learner intelligence) behind a
**vanilla JavaScript SPA** served from `backend/frontend/`. P0–P6 delivered a
complete single-lesson learning loop: sign in → open lesson → understand →
visualize → practice → assess (interactive quiz) → see mastery + one next
action → leave and resume.

The most important finding of this audit is a **surface gap, not a data gap**.

The backend already contains a fully implemented, deterministic **learner
intelligence stack**: concept-level mastery persistence (educational memory),
a mastery-driven recommendation engine, quiz/assessment/attempt data, learning
events, and researcher-oriented effectiveness/learning-gain endpoints. All of
this is wired to a lesson-scoped player mastery endpoint. **But the learner has
no dashboard — no way to see their overall progress, mastery, history, or
recommendations across lessons.** The only learner-facing intelligence surface
is a small, lesson-scoped sidebar panel inside the player.

The recommended P7 combines Candidate A (Adaptive Learner Intelligence) and
Candidate B (Learner Analytics + Progress Dashboard) into **one coherent
product phase: "Learner Intelligence & Adaptive Progress"** — a learner-facing
dashboard that surfaces the already-existing, deterministic learner
intelligence (mastery, weak/strong concepts, next-best action, history,
trends) across lessons, in the existing vanilla SPA, with **no new AI and
likely no new database migration**.

---

## 2. Starting Commit

```
Branch: feature/individual-user-foundation
HEAD:   8c82a2ca53d52576c03bd03ce68b3a76a6bb3a85  (8c82a2c)
Commit: feat(p6): add interactive quiz-taking UI and complete learning loop
Working tree: CLEAN (verified via git status --short = empty)
```

The audit began from the verified post-P6 release commit. No reset, rebase,
or checkout was performed.

---

## 3. Repository Reality Check

### Architecture tree (actual, read-only)

- **App**: `backend/app/` — FastAPI monolith.
  - `api/v1/` routers: auth, presentations, presentation_folders, storage,
    player, quiz, visual_canvases, simulation, animation, animation_runtime,
    video, video_runtime, assistant, **effectiveness**, exports, health,
    metrics.
  - `services/` — 60+ services including `lesson_player_service`,
    `quiz_attempt_service`, `educational_memory_service`,
    `recommendation_engine`, `effectiveness_service`, `learning_event_service`,
    `feedback_service`, `lesson_generation_service`, RAG/embedding services,
    visual/animation/video/simulation services.
  - `models/` — 50+ models including concept, generated_lesson(_version),
    generated_block, quiz(_version, _content), quiz_attempt, question_attempt,
    educational_memory, learning_session, learning_event, analytics,
    vector_index, assistant_*.
  - `repositories/`, `schemas/`, `security/`, `middleware/`, `observability/`,
    `workers/` (Redis/Celery), `storage/`, `parsers/`, `uploads/`.
- **Frontend (active)**: `backend/frontend/` — vanilla SPA (HTML+JS+CSS).
  - Pages: `index.html`, `signin.html`, `signup.html`, `upload.html`,
    `player.html`, plus `assets/app.js`, `assets/style.css`.
  - **No dashboard/analytics page exists.**
- **Duplicate/inactive frontend**: `EduVision_AI_Frontend/` (repo root) —
  confirmed separate and **not** the served frontend. Ignored for product work.
- **Migrations**: `backend/app/database/migrations/versions/` — 28 files,
  single Alembic head `0028_ws10_idempotency_key_index`.
- **Tests**: `backend/tests/{unit,integration,postgres,e2e,fixtures}`.
- **Infra**: `backend/Dockerfile`, repo-root `docker-compose.yml`,
  `.github/workflows/ci.yml`. Health/readiness checks DB + Redis + storage.

### Evidence note on expected docs

P4 docs `P4_IMPLEMENTATION_AUDIT.md` and `P4_IMPLEMENTATION_FOUNDATION_REPORT.md`
named in the task were **ABSENT / NOT VERIFIED** (not present in
`backend/docs/`). The P4 work is instead represented by `P4_ARCHITECTURE_BASELINE.md`,
`P4_SCOPE_AND_FOUNDATION.md`, and `P4_WS{3,4,5,6,7}*` docs. No fabricated content.

---

## 4. P0–P6 Inheritance Verification

The task asked to verify the docs that exist and reconcile against code. All
named P0–P6 docs are present (see file listing in `backend/docs/`) except the
two P4 implementation docs above. Key claims reconciled against code:

- **P0 security foundation** — verified: `get_current_user` dependency,
  ownership assertions in services (`_assert_lesson_ownership`,
  presentation owner checks), user-scoped queries throughout player/quiz/
  educational-memory paths.
- **P1 ownership/security** — verified: cross-user isolation tested
  (`test_p6_assessment_security.py`, unit quiz/isolation tests).
- **P2 data/runtime** — verified: PostgreSQL prod + SQLite test path, RAG/
  embedding system, models above.
- **P3 hardening** — verified: readiness (DB/Redis/storage), observability/
  metrics, health endpoints.
- **P4 bounded caches / browser foundation** — verified: `BoundedCache`
  (max_size/ttl) in `educational_memory_service`; `cache.py` references
  Redis-backed cache as *future* (deferred).
- **P5 persistent learner journey** — verified: `LearningSession`,
  `lesson_player_service`, journey panel, `test_learner_journey*`.
- **P6 interactive assessment** — verified directly against code + tests
  (Section 5).

---

## 5. P6 Verification (do not redo)

All 16 required P6 capabilities verified against the repository:

| # | Capability | Evidence |
|---|-----------|----------|
| 1 | Quiz checkpoint in journey | `player.html:renderLearnerJourney()` + `GET /lessons/{id}/player/checkpoint` (player.py:112) |
| 2 | "Take Checkpoint" action | `player.html:449` `take` button → `startQuiz` |
| 3 | Quiz overlay opens | `player.html:1797 startQuiz()` `#quizOverlay` |
| 4 | Questions render | `renderQuizQuestion()` |
| 5 | Answer options render | MC radio options |
| 6 | Answers persist while navigating | per-question answer map + `quizChoose()` |
| 7 | Prev/Next works | `quizNav()` |
| 8 | Quiz submission works | `submitQuiz()` → attempt API |
| 9 | Results display | `renderQuizResult()` |
| 10 | Score displayed | score ring |
| 11 | Pass/fail displayed | "Checkpoint passed" vs "keep going" |
| 12 | Mastery updates | P6 C4 test asserts mastery + recommendation; `educational_memory_service.update_concept_mastery` |
| 13 | Next action updates | `refreshLearnerJourney()` re-fetches mastery |
| 14 | Progress persists | `LearningSession` + E2E leave/reopen step |
| 15 | Ownership isolation | `test_p6_assessment_security.py` (User B 404s) |
| 16 | Browser E2E | `tests/e2e/test_p6_full_loop.py` (real browser loop) |

**P6 verification: PASS.** No changes made.

---

## 6. Current Learner Journey

Evidence-based model (from `player.html`, player/quiz routers, services):

```
SIGN IN
  → real form → JWT → authFetch
LESSON
  → upload.html captures a deck → generated lesson → player.html
UNDERSTAND
  → concept slides rendered from generated lesson topics (player.html renderSlide)
VISUALIZE
  → visual slide with type selector (auto/image/animation/video/simulation) + Generate
PRACTICE
  → slide navigation / topic advance (LessonPlayerService.advance_topic)
ASSESS
  → journey panel chip + "Take Checkpoint" → quiz overlay → submit → results
MEASURE
  → lesson progress % bar (panel) + latest quiz score + pass/fail
NEXT ACTION
  → single "Next up:" title from /mastery next_action (recommendation engine)
LEARN AGAIN
  → open lesson again → persisted session + completed attempt restored
```

Per-stage verdict (repository evidence):

| Stage | Implemented | Functional | Persisted | Personalized | Observable | Secure | Browser verified | Missing |
|-------|-------------|-----------|-----------|--------------|-----------|--------|------------------|---------|
| Sign in | YES | YES | YES (JWT) | — | YES | YES | YES | — |
| Lesson | YES | YES | YES | partial (per-user session) | YES | YES | YES | — |
| Understand | YES | YES | YES | partial | YES | YES | YES | richer explanation |
| Visualize | YES | YES | YES (via visual services) | partial (auto pick) | YES | YES | partial | advanced interaction |
| Practice | YES | YES | YES (session) | partial | YES | YES | YES | — |
| **Assess** | **YES (P6)** | **YES** | **YES** | **YES (mastery)** | **YES** | **YES** | **YES** | dashboard of attempts |
| **Measure** | **PARTIAL** | YES | YES | YES | **lesson-only** | YES | **lesson-only** | **cross-lesson view** |
| **Next action** | **PARTIAL** | YES | YES | **YES** | **one action only** | YES | **one action only** | **full recommendation queue** |
| Learn again | YES | YES | YES | YES | YES | YES | YES | cross-lesson history |

**The journey is complete only within a single lesson.** Measure and Next
Action are personalized and persisted **but not surfaced comprehensively**:
the learner sees one bar, one chip, one score, one next-action — and nothing
across lessons.

---

## 7. Product Capability Audit

### A. Lesson / Content — VERIFIED
Presentation ingestion (parsers, uploads, presentations router), PPT
extraction, topic/lesson generation (lesson_generation_service + worker),
explanation + visual content, sequencing, per-user lesson progress/resume
(LearningSession). Browser verified via P5/P6 E2E.

### B. Assessment — VERIFIED
Quiz generation/publishing (quiz routers, quiz_version/content), checkpoint,
attempt/answer submission, scoring, per-question feedback, attempt history
(list-attempts), retakes (available_attempts), question-level performance
(question_attempt), mastery update (educational memory). Browser verified (P6).

### C. Learner Intelligence — VERIFIED (backend) / PARTIAL (surface)
Educational memory (DB-persisted, bounded cache), concept mastery
(mastered/developing/weak categorization + trend + review count + average),
deterministic recommendation engine (weak→simplify, developing→practice,
advanced→challenge, mastered→next), weak/strong concept detection
(`effectiveness` report returns `weak_concepts`/`strong_concepts`).
**Missing a comprehensive learner-facing surface**: the frontend exposes only
one next-action and lesson-scoped counts.

### D. Analytics — PARTIAL
Models exist (`learning_analytics_snapshots`, `learning_events`,
`presentation_analytics`) plus effectiveness endpoints (learning gain,
baseline/post/retention, summary, CSV export, group comparison). These are
**researcher/study-oriented** (P3 study protocol) and are **NOT surfaced as a
learner dashboard**. No learner-facing progress/trend visualization exists.

### E. Visual Learning — PARTIAL
Visual generation/persistence/interaction, animation, video, simulation
routers/services. Instructor/learner can pick visual type and Generate in
player. Advanced interactive/adaptive visual learning not surfaced as a
distinct learner phase.

### F. AI Tutor / RAG — PARTIAL
RAG retrieval, semantic retrieval, ownership isolation (per-user documents),
educational memory context. Assistant/learning_assistant services exist, but a
mastery-aware tutoring surface is not part of the closed learner loop.

### G. Learner Dashboard — **MISSING (the gap)**
The learner currently sees, inside the player sidebar panel: overall-ish
lesson progress %, current-lesson checkpoint chip, latest score, attempts left,
and ONE next-action. There is **no dashboard page** showing overall progress
across lessons, assessment performance, mastery, weak/strong concepts,
recommendations, history, or trends. `index.html` "Dashboard" button links to
`upload.html` (a deck-management page), not a learner analytics view.

### H. Teacher / Instructor — PARTIAL / DEFERRED
Creator/creator-analytics and presentation-analytics exist, but a learner-facing
instructor intelligence product is not warranted at this stage given the
existing architecture and single-user focus.

---

## 8. Technical Capability Audit

- **Backend**: FastAPI + SQLAlchemy async + UoW + repositories + services.
  Clean layering. Ownership enforced in services.
- **Persistence**: PostgreSQL prod (JSONB variants), SQLite test path. Mastery
  stored as a JSON blob in `educational_memories` (per-user row).
- **Recommendation engine**: pure, deterministic, unit-tested
  (`test_recommendation_engine.py`) — no AI calls.
- **Data for a dashboard already queryable deterministically**:
  `GET /lessons/{id}/player/mastery` (average_mastery, mastered/developing/
  weak counts, concept_mastery map, summary, one next_action),
  `GET /effectiveness/summary`, `/effectiveness/learning-gain/{pres}`,
  `/effectiveness/report/{pres}` (weak/strong concepts, concept_improvements),
  quiz list-attempts, learning events.
- **Missing technically**: a **cross-lesson, learner-scoped aggregate**
  endpoint(s) and a **frontend dashboard page** that calls them. The lesson
  player pinpoints mastery to a single lesson; a dashboard needs a learner-wide
  view. Likely small backend addition (reusing existing services), not a new
  subsystem.

---

## 9. Security Audit

Existing controls verified and to be **preserved**:
- `get_current_user` + ownership checks in player/quiz/effectiveness paths.
- 404/403 isolation; never trusting client ownership.
- Educational-memory `user_id` unique + user-scoped; bounded cache keyed per user.
- Quiz/attempt/result isolation tests (P6 C4).
- RAG ownership isolation.

P7 dashboard must:
- Serve each learner **only their own** aggregate (user-scoped queries).
- Not weaken existing lesson/quiz ownership.
- Expose no other user's lessons/quizzes/attempts/mastery/events.
- Reuse the same owner-id patterns as `lesson_player_service`.
No new tier of privilege required.

---

## 10. Database Audit

- **PostgreSQL production** — confirmed (models use `PostgreSQL JSONB`
  variants, `PortableJSONB`, readiness checks DB dialect).
- **SQLite test path** — confirmed (tests run on plain SQLite file).
- **Alembic** — single head `0028_ws10_idempotency_key_index`, 28 migrations.
- Existing learner tables: `learning_sessions`, `educational_memories`,
  `quiz_attempts`, `question_attempts`, `learning_events`,
  `learning_analytics_snapshots`, `concepts`, `generated_lessons`, etc.
- All mastery/attempt/event data a dashboard needs **already exists**.
- **Conclusion: the recommended P7 likely requires NO new migration** — it is a
  query/aggregation + frontend effort. **TO BE DETERMINED** only if a new
  materialized trend/aggregate table is later wanted; document before adding.

---

## 11. Performance / Scale Audit

- Mastery read: bounded cache (5000 entries, 1800s TTL) avoids DB read per hit.
- Lesson player renders only the active slide (scales to any deck).
- Dashboard aggregation must avoid N+1; reuse existing indexed columns
  (`user_id`, `snapshot_date`, `occurred_at`).
- Long-term scale target: per-user dashboards are naturally shardable by
  `user_id`; no distributed architecture needed now.
- No new Redis/Celery required for the recommended P7.

---

## 12. AI / RAG Audit

- RAG + embeddings + vector_index existence confirmed (P4/WS7 docs + models/
  services). Ownership-isolated.
- **No new AI provider, no ML training, no vector DB migration is required for
  the recommended P7.** The intelligence the dashboard surfaces is already
  deterministic (educational memory + recommendation engine). AI is used only
  for lesson/visual generation as today.

---

## 13. Frontend Audit

- Active: vanilla SPA in `backend/frontend/`.
- Capabilities: signin/signup, deck upload, player (slides + journey panel +
  quiz overlay). Bootstrap-less custom CSS; `authFetch` wrapper; JS validated
  with `node --check`.
- **No framework migration is required** to add a dashboard page. A new
  `dashboard.html` (or a dashboard view) in the same vanilla pattern is
  realistic and consistent with existing code.
- The duplicate `EduVision_AI_Frontend/` is NOT the served frontend.

---

## 14. Testing Audit

Existing layers: unit (74 files), integration (16 files), postgres (separate
suite), e2e (3 files incl. learner journey + P6 full loop). Baseline (post-P6):
fast SQLite **1076 passed**, PostgreSQL **15 passed**, e2e **7/7**, Ruff clean,
mypy **83** (zero new), single Alembic head. A dashboard P7 is highly testable
deterministically (mastery/recommendation already unit-tested).

---

## 15. Infrastructure Audit

- `backend/Dockerfile`, repo-root `docker-compose.yml`, `.github/workflows/ci.yml`.
- Health/readiness (DB + Redis + storage), metrics endpoint, logging.
- Redis present (lifespan close + readiness); Celery/workers for async
  generation. Existing bounded-cache infra reused.
- No infra changes needed for the recommended P7.

---

## 16. Remaining Product Gaps (ranked by value)

1. **No learner-facing dashboard** — the learner cannot see their own
   progress/mastery/history/trends across lessons (data exists; surface does not).
2. **Next-action surface is too thin** — only one action in a lesson sidebar,
   not a prioritized queue across concepts.
3. No cross-lesson history / trends (foundation of a persistent "learner story").
4. No tutoring/remediation UI (bigger, depends on RAG/tutor services).
5. Richer visual interaction (advanced animations/simulations).
6. Teacher/instructor analytics product.

---

## 17. Candidate Evaluation

Scored against Learner Value, Educational Value, Differentiation, Readiness,
Complexity, Security Risk, Regression Risk, Infra Cost (each /10):

| Candidate | LV | EV | Diff | Readiness | Cx | Sec | Reg | Infra | Scope | Overall | Rec |
|-----------|----|----|----|----|----|----|----|----|----|----|----|
| A Adaptive Learner Intelligence | 8 | 9 | 8 | 9 | 5 | 2 | 2 | 1 | S–M | **High** | **Merge with B** |
| B Analytics + Progress Dashboard | 9 | 8 | 7 | 9 | 5 | 2 | 2 | 1 | S–M | **High** | **Merge with A** |
| C Advanced Visual Learning | 7 | 7 | 6 | 5 | 7 | 1 | 4 | 2 | L | Medium | Defer |
| D AI Tutor / Mastery-Aware Tutor | 8 | 9 | 8 | 6 | 8 | 3 | 4 | 3 | L | Medium | Defer (riskier) |
| E 2D Learning Editor | 6 | 6 | 7 | 4 | 9 | 3 | 5 | 3 | L | Medium-Low | Defer |
| F Teacher Intelligence | 6 | 6 | 6 | 5 | 8 | 4 | 4 | 4 | L | Low | Defer |
| G Framework migration | 2 | 2 | 1 | 3 | 9 | 3 | 8 | 4 | XL | **Low** | **Reject now** |
| H Knowledge Graph / AI infra | 4 | 6 | 7 | 3 | 9 | 4 | 5 | 5 | XL | **Low** | **Reject now** |

Readiness is the decisive differentiator: **A and B are the only candidates
with near-full architectural readiness** (data + intelligence already built),
low complexity, low risk, and no AI/infra cost. C/D/E/F/H either need new
backend capability, larger scope, or higher risk with no proportional gain now.
G is explicitly an architectural investment, not learner value — reject.

**A and B are complementary and share the same data foundation.** B (the
dashboard) is the *surface*; A (adaptive intelligence) is the *personalization*
the surface reveals. Splitting them forces re-implementing the same load/
aggregate logic twice. They should be **one** P7.

---

## 18. Recommended Direction

**P7 — Learner Intelligence & Adaptive Progress** (one phase):

```
existing learner activity
      → existing attempted assessments
      → existing concept mastery (educational memory)
      → existing learner state (average + mastered/developing/weak)
      → existing deterministic recommendation engine
      → NEW learner-facing dashboard (vanilla SPA)
      → prioritized next-best-action + cross-lesson history/trends
```

This turns already-built, already-persisted, already-deterministic learner
intelligence into visible learner value through a **new frontend surface plus
small learner-scoped aggregate endpoints** — with no new AI and likely no new
migration. See `P7_SCOPE_AND_FOUNDATION.md` for the full plan.

---

## 19. Risks

- Scope creep into a full analytics platform (must stay learner-scoped).
- Aggregation N+1 if not careful (mitigate with indexed user-scoped queries).
- Accidental cross-user data leak in new aggregate endpoints (must reuse
  ownership patterns; add 2-user isolation tests).
- Dashboards can become AI-heavy if not disciplined (keep deterministic).
- Existing player mastery endpoint is lesson-scoped; ensure the dashboard
  endpoint does not duplicate/conflict (reuse `educational_memory_service` +
  `recommendation_engine`).

---

## 20. Deferred Items (explicitly out of P7)

- Advanced visual interaction / simulations (C).
- Mastery-aware tutor UI / remediation (D).
- 2D interactive learning editor (E).
- Teacher/instructor analytics product (F).
- Frontend framework migration (G).
- Knowledge graph / advanced AI infrastructure (H).
- Extra migration unless proven needed by the selected P7.

---

## 21. Conclusion

EduVision's core interactive learning loop is complete and browser-verified
(P0–P6). The single biggest remaining gap — and the highest-value, best-typed,
lowest-risk next product capability — is a **learner-facing surface** for the
already-built adaptive intelligence and progress data. That is P7: **Learner
Intelligence & Adaptive Progress**, combining Adaptive Learner Intelligence and
the Learner Analytics Dashboard into one coherent phase built on existing data,
existing mastery, and the existing deterministic recommendation engine.

Audit is decision-only. **No implementation was started.**
