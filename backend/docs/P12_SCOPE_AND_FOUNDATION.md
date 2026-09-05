# P12 Scope & Foundation — Genuine Adaptive Assessment with PostgreSQL Attempt-Path Repair

**Status:** PLANNING (audit phase — NO implementation)
**Authoritative implementation contract for P12.**
**Branch target:** `feature/individual-user-foundation`
**Parent of P12:** Post-P11 audit at HEAD `30e3bbd` (this doc + `POST_P11_PRODUCT_ARCHITECTURE_AUDIT.md` + `POST_P11_CAPABILITY_MATRIX.md`)
**Type:** Feature phase — implementation occurs ONLY after this doc is approved.

---

## 1. Recommended P12 Title

**P12 — Genuine Adaptive Assessment (NG-4) with mandatory PostgreSQL attempt-path repair**

Two mandatory parts:
- **P12-A1 (Foundation/Repair)** — one additive schema-consistency migration that aligns migration `0005` with the live ORM on `quiz_attempts` / `question_attempts`, plus **PostgreSQL behavioral tests that execute the live attempt flow** against the migrated schema (fixes the empirically-verified CRITICAL drift).
- **P12-A2 (Product)** — deterministic adaptive delivery of the existing question bank (mastery-tuned ordering/selection driven by stored `difficulty`/`bloom_level` and the learner's mastery), plus retirement of the dead VisualQuestion engine.

---

## 2. Why P12 is Next (evidence)

- P11 closed NG-5 and is fully re-verified this audit: SQLite 1161, PG 15, E2E 13, Ruff clean, mypy 83/24, single head `0031`, clean tree.
- The **only remaining explicitly-deferred NG** from the P10/P11 contracts is **NG-4 (genuine adaptive assessment)**.
- The audit **empirically proved** (on a real `postgres:16-alpine` via testcontainers + `alembic upgrade head`) that the live quiz attempt path **cannot run on a migrated PostgreSQL** — three failure classes on `quiz_attempts`/`question_attempts` (§12.2 of the audit). A naive "un-stick the dead `AdaptiveAssessmentEngine`" phase would inherit this broken spine.
- Therefore P12's foundation work is *also* the de-risking: fix the drift + prove the attempt flow on PG (A1), then build adaptivity on the repaired spine (A2). One phase, two mandatory checkpoints, one coherent product outcome.

---

## 3. Learner Problem (objective)

**"The checkpoint I take is a fixed rack of questions, not a guide."** Every learner gets the same question order regardless of mastery; weak areas do not surface earlier or at appropriate difficulty, and the stored `difficulty`/`bloom_level` metadata is never used. P12 answers: *"next checkpoint, the order and emphasis of my questions is tuned to my current mastery — deterministically — while my score stays comparable and fair."* Foundationally, it also replaces the current *latent* state where taking a checkpoint against the production database fails outright with a verified-correct assessment spine.

---

## 4. Current Gap

- **Verification gap (CRITICAL)**: `QuizAttempt` and `QuestionAttempt` inserts fail on migrated PostgreSQL (NOT NULL columns absent/unset; `feedback` JSONB vs `Text`). The 15-test PG suite never inserts attempts, so it cannot see the defect.
- **Product gap (NG-4)**: fixed-order delivery (`quiz_repository.py:151 order_by(Question.position)`); `shuffle_questions` stored but never honored; the only "adaptive" artifacts are a dead engine built on the incompatible `schemas/visual_assessment.py` `VisualQuestion` type and unused `difficulty` columns.

---

## 5. User Stories

1. As a learner, when I start a checkpoint my server-built question order reflects my current mastery and the stored difficulty/bloom profile of the bank — deterministically, no AI (NG-4).
2. As a learner, my attempt (attempt + per-question rows) is **persisted reliably on the production PostgreSQL database**, and the platform can prove it with automated tests on the migrated schema.
3. As a creator, questions I tag with `difficulty`/`bloom_level` actually influence delivery rather than being decorative.
4. As a learner, adaptive delivery is additive: existing quizzes keep a deterministic, re-runnable order option; nothing about scoring is per-learner-randomized.
5. As a product owner, the dead VisualQuestion/adaptive engine and orphaned assessment schemas are retired or repurposed so the "adaptive" signal in the codebase reflects reality.

---

## 6. Exact MVP

### P12-A1 — PostgreSQL attempt-path repair (MANDATORY, first)
- **One additive Alembic migration** (new head, no edits to historical migrations) that makes migration `0005` and the ORM agree on `quiz_attempts` and `question_attempts`:
  - `quiz_attempts.max_score` → nullable (model already nullable) OR add server default + backfill; choice at implementation with data-safety review (any existing rows).
  - `quiz_attempts.time_spent_seconds` → nullable OR server default + backfill, and **mapped on the ORM** if the service should set it.
  - `question_attempts.public_id` → **add the mapping** on `QuestionAttempt` (with a `qatt_`-style generator like `QuizAttempt`) so rows carry the NOT NULL value; or make the column nullable after backfill — decisively one option, per migration discipline.
  - `question_attempts.time_spent_seconds` → map it or make it nullable (same rule).
  - `question_attempts.feedback` → align ORM typing with `jsonb` (`JSON().with_variant(JSONB())` + matching serialize/deserialize or a JSON-column pattern already used elsewhere), so the INSERT bind matches the schema type.
  - Add any missing indexes the ORM expects (mirror existing parity discipline from 0030/0031 style).
- **PG behavioral tests** (extend `tests/postgres/`, same testcontainers harness):
  - `start_attempt` through the live service against the migrated schema persists `QuizAttempt` + `QuestionAttempt` rows (≥ 2 questions).
  - `submit_answer` + `submit_quiz` persist grading fields and produce a `ScoreSummary`.
  - Resume path re-loads an in-progress attempt.
  - Cross-user attempt access → 404-equivalent (ownership preserved on PG).
  - SQLite suite continues to pass (dual-dialect parity).
- **No behavior change** to scoring or to any existing endpoint contract.

### P12-A2 — Deterministic adaptive delivery (NG-4)
- **Mastery-tuned ordering/selection**: at `start_attempt`, derive a deterministic question order for the chosen `quiz_version` from stored `Question.difficulty` + `Question.bloom_level` and the learner's current concept mastery (from `educational_memory_service`, same public-ID keying P10 uses). Composition rules:
  - Weak concepts → earlier, lower-difficulty questions first (build confidence), advanced/`bloom` higher only after a correct answer within the same attempt (deterministic counter, no AI).
  - Mastered/developing concepts → mixed difficulty, nearer the learner's demonstrated level.
  - Deterministic tie-breakers (position, public_id) so identical inputs always yield identical order.
- **Adaptive metadata**: response payload adds `adaptive: true/false` + a short deterministic rationale (e.g. "Ordered to your mastery: weak concepts first at matched difficulty") rendered as a label in the quiz overlay; `shuffle_questions` flag behavior becomes explicit (honored or documented as disabled for adaptive mode).
- **Fallback**: non-adaptive mode (fixed order, `adaptive: false`) remains default-off-static and always available; adaptive mode never randomizes scoring.
- **Retirement scope (safe)**: `adaptive_assessment_engine.py` and `visual_question_generator.py` (dead, VisualQuestion-based) and the orphaned assessment schemas (`schemas/adaptive.py`, `schemas/visual_assessment.py` if unused elsewhere, `schemas/director.py`, `schemas/teaching_strategy.py`) are either deleted (with confirmation they have zero imports and zero doc references that matter) or explicitly marked retired in a `RETIRED.md` listing — decided at implementation, no partial wiring of incompatible schemas.

**Out of MVP (explicit):** AI-generated adaptive questions, per-question visual regeneration, inter-attempt difficulty adaptation beyond ordering, elo/IRT models, analytics dashboards, retention scheduling, any new AI provider, any RAG change, framework migration.

---

## 7. Detailed Scope

### IN SCOPE
- One additive migration (head `0032_*`) + ORM alignment on the two attempt tables (A1).
- PG behavioral tests running the live attempt flow (A1).
- Adaptive ordering service/function (deterministic, unit-testable) + integration into `start_attempt` delivery (A2).
- `adaptive` metadata in attempt responses + minimal quiz-overlay label in `player.html` (A2).
- Retirement/deprecation of dead adaptive services + orphaned assessment schemas (A2; delete-only-if-zero-refs, documented).
- Regression/observability: an `p12_*` counter (e.g. adaptive orders issued, PG drift-gate test present), following P10/P11 pattern.

### OUT OF SCOPE (rejected, per audit)
- Learner analytics / insights (follow-up phase).
- Tutor 2.0 (main follow-up candidate, §17/§19 of the audit).
- Mastery decay persistence.
- Animation/video runtime frontend completion.
- Spaced-repetition 2.0.
- Plan/Goal/Path 2.0.
- UX completion niche (fold individual items opportunistically).
- Pure tech-debt/hardening phase beyond A1 (the drift repair IS the hardening A1 provides).
- Framework migration, 2D editor, mobile, classroom/collaboration, microservices/vector-DB, ML/DL models, multi-tenancy/SSO, autonomous agents, new AI providers, large-scale infra rewrite, unrelated historical mypy fixes (all AG-1..11 carried).

---

## 8. Existing Systems Reused

- `quiz_attempt_service.start_attempt` / `submit_answer` / `submit_quiz` (repair + extend; the spine).
- `quiz_repository` / `question_repository` (bank reading; `order_by` becomes deterministic-adaptive-path-capable).
- `educational_memory_service` + public-ID concept keying (P10) for mastery input.
- `Question.difficulty` / `Question.bloom_level` (already persisted; currently unused).
- PortableJSONB dual-dialect + testcontainers PG harness (`tests/postgres/conftest.py`).
- `player.html` quiz overlay (additive label only).
- `observability/metrics.py` P10/P11 counter patterns.

## 9. New Systems Required

- Adaptive ordering module (pure function, e.g. `app/services/adaptive_ordering.py`) — may replace/absorb the dead engine namespace without importing its VisualQuestion types.
- One additive migration + model edits on `QuizAttempt`/`QuestionAttempt`.
- PG behavioral test file(s) under `tests/postgres/`.
- Optional `RETIRED.md` (dead-service retirement ledger) if deletion is chosen.

---

## 10. API Impact

- **Backward compatible**: existing quiz/attempt endpoints keep contracts; `start_attempt` response gains an additive `adaptive` field (+ rationale).
- No contract changes to grading, resume, or `/me/*` surfaces.
- New/changed behavior is observable: attempt creation now succeeds on PostgreSQL (A1).

## 11. Database Impact

- **Exactly one additive migration** — `0032_*` — aligning `quiz_attempts`/`question_attempts` (nullable/default/backfill + feedback typing + mapped columns). No historical migration edits. Single head `0032_*` after applying.
- PG behavioral tests are the acceptance gate that the migration is correct.

## 12. Frontend Impact

- Minimal: an adaptive-mode label in the quiz overlay (`player.html`) driven by the new `adaptive` field; `escHtml`/`escSvg` preserved; no new page; no build step.

## 13. AI Impact

- **None.** Adaptive ordering is deterministic over stored metadata + mastery. No new AI provider, no new AI calls, no AI on the scoring path. The dead engine's AI-visual-generation idea stays rejected.

## 14. RAG Impact

- None. RAG untouched.

## 15. Security Requirements

- Preserve ownership/isolation on every touched endpoint (cross-user attempt access stays 404-equivalent; verified again in the new PG behavioral tests).
- No client-supplied user ids anywhere in adaptive ordering (mastery read is auth-scoped).
- No new secrets; no change to rate-limit route overrides for quiz/attempt/adaptive-quiz.
- `escHtml` for the new overlay label.

## 16. Performance Requirements

- Adaptive ordering is O(n log n) over the version's question bank (bounded bank); no extra DB round-trips beyond the existing delivery reads.

## 17. Testing Requirements

- **PG behavioral**: start → submit → resume → submit_quiz → ScoreSummary on migrated PG (the gate that would have caught the CRITICAL drift).
- **Unit**: deterministic ordering properties (same input → same order; weak-first at matched difficulty; tie-break stability; boundaries) + fallback mode.
- **Dual-dialect**: full SQLite regression stays green (≥ 1161).
- Security: cross-user → 404 on the new PG behavioral path.

## 18. Browser E2E Requirements

1. Seeded learner with mixed-difficulty bank → checkpoint returns `adaptive:true` with mastery-tuned order (assert first-question selection).
2. Quiz overlay shows the adaptive label; answering + submit produces a normal score (P6 full-loop style).
3. P6 full loop and P10 NG-3 regressions stay green in the browser.

## 19. Acceptance Criteria

- `alembic upgrade head` on a fresh PG then running the live attempt flow succeeds end-to-end (start → answers → submit → ScoreSummary) — **automated**, not manual.
- Adaptive mode is deterministic, mastery-aware, additive, with `adaptive` field in the payload and a visible overlay label.
- Scoring semantics unchanged; fallback (fixed order) available.
- Dead adaptive engine/schemas retired or documented-with-ledger.
- Full regression contract green (≥ 1161 SQLite, ≥ 15 PG — now including the new catch-the-drift tests, E2E 13+1, Ruff clean, mypy 83/24 zero-new, single head `0032_*`, secret scan clean, git diff --check clean).

---

## 20. Checkpoint Structure

| Chk | Objective | Files expected | Tests | Acceptance | Rollback |
|---|---|---|---|---|---|
| C0 | Baseline / contract (re-verify P11 gates) | none | full regression | gates green | -- |
| C1 | **A1 migration + ORM alignment** (attempt tables) | migration 0032 + models | PG: live-flow insert/grade/resume | drift gone; SQLite parity | additive only |
| C2 | **A1 PG behavioral tests** | `tests/postgres/` | new PG tests | start→submit→score green on migrated PG | revert tests |
| C3 | **A2 adaptive ordering** (pure, deterministic) | `adaptive_ordering.py` + delivery integration | unit: determinism/weak-first/bounds | deterministic, no AI | revert service |
| C4 | Adaptive metadata + overlay label + retirement ledger | `player.html`, schemas, `RETIRED.md` | E2E label; dead-code zero-ref check | additive UI; deletions zero-ref | revert JS/docs |
| C5 | Security/isolation re-check | tests | cross-user 404 on PG path | no regressions | -- |
| C6 | Browser E2E (P12 + regressions) | `tests/e2e/` | P12 E2E + P6/P10 regressions | green | revert E2E |
| C7 | Performance (bounded ordering, no new round-trips) | query/order | assertions | O(n log n) bounded | -- |
| C8 | Observability (`p12_*` counters) | `observability/metrics.py` | -- | present | -- |
| C9 | Full regression (all gates + PG behavioral) | -- | all suites | contract green | -- |
| C10 | Regression gate (≥ P11 counts, zero new mypy) | -- | full | ≥1161/≥15/E2E≥13 | -- |
| C11 | Documentation + report | docs (P12 report) | -- | artifacts present | -- |
| C12 | Release gate + completion commit | -- | all green | final report + clean tree | -- |

## 21. Regression Gates (P12 must hold)

- SQLite: ≥ 1161 passed (0 failed).
- PostgreSQL: ≥ 15 passed **plus the new attempt-flow behavioral tests green** (the drift gate).
- Browser E2E: ≥ 13 passed plus the new P12 adaptive E2E.
- Ruff: clean. mypy: ≤ 83 errors in app, zero new in P12 files.
- Alembic: exactly one new head (`0032_*`), single head.
- Secret scan: clean. git diff --check: clean.
- User isolation preserved on every new/changed endpoint.
- No new AI/RAG changes.

## 22. Risks

| Risk | Mitigation |
|---|---|
| Migration touches sensitive attempt tables | Additive-only; data-preserving choices (nullable/default+backfill) reviewed against existing rows; PG behavioral gate |
| Adaptive ordering regresses P6 UX | Additive metadata + retained fallback; E2E regression on P6 full loop |
| Scope creep into AI-question-gen or analytics | Bound to A1+A2; explicitly re-defer B/C |
| Dead-engine ambiguity | Zero-ref check before deletion; `RETIRED.md` ledger |
| mypy floor | Zero-new policy; pure ordering module typed |

## 23. Rollback Strategy

Additive and reversible per checkpoint: revert the migration (new head only), revert model/service edits, revert the overlay label and ledger; primary rollback is reverting the last checkpoint commit without touching historical migrations.

## 24. Explicit Non-Goals (P12)

- NO AI content/question generation; NO new AI providers; NO RAG changes.
- NO inter-attempt adaptive persistence beyond ordering; NO elo/IRT/ML learner modeling.
- NO learner analytics dashboards; NO Tutor 2.0; NO mastery decay persistence; NO spaced-repetition 2.0; NO plan/goal/path 2.0.
- NO framework migration, 2D editor, mobile, classroom/collaboration, microservices, vector-DB, multi-tenancy, SSO, autonomous agents, large-scale infra rewrite, or unrelated historical mypy fixes.
- NO change to scoring semantics or existing endpoint contracts.
- NO retention scheduling; NO Redis/Celery integration-harness work (documented ops debt).

## 25. Definition of Done

- The live quiz attempt flow runs and is **automatically verified** on a migrated PostgreSQL database (start → answer → resume → submit → ScoreSummary).
- Quizzes can be delivered deterministically adaptive (mastery+difficulty/bloom ordering, `adaptive` flag, overlay label) with unchanged scoring and a preserved fixed-order fallback.
- Dead VisualQuestion-based engine/schemas retired or ledgered; no misleading "adaptive" surface remains in the codebase.
- All regression gates green, tree clean, docs committed, P12 report produced.