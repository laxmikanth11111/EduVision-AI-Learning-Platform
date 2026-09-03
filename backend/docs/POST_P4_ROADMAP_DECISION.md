# Post-P4 Roadmap Decision

**Status:** ROADMAP DISCOVERY + DECISION AUDIT — COMPLETE (documentation only;
no application code changed).
**Repository state at start:** clean; HEAD = `cd0f2b4` on
`feature/individual-user-foundation`. P4 complete (WS1–WS6).

> Every claim below is evidence-sourced to repository files/documents.
> Nothing is asserted from filenames alone. Where evidence is insufficient the
> status is marked **UNKNOWN / NOT VERIFIED** explicitly.

---

## 1. Executive summary

EduVision AI has completed its P4 production-hardening program (WS1–WS6). The
backend is production-hardened and the **content-generation foundation is
strong and complete**: upload → extract → AI-assisted presentation → lesson →
topic → visual (canvas/animation/video/simulation) → export, with vector
semantic RAG and a hardened learner-intelligence service layer.

The **product-completeness gap** is the *learning loop itself*: a large body of
learner-intelligence machinery (mastery, educational memory, adaptive
assessment, recommendations, learning sessions/events) already exists in the
backend and passes tests, but the **active user-facing player is simplified** —
it tracks only a topic index and does **not** persist per-user progress, does
**not** surface in-lesson assessment/quiz, does **not** persist bookmarks/notes,
and therefore does **not** close the learner's loop or show the learner his/her
own mastery/recommendations.

**Recommendation:** the next post-P4 phase is to **complete the interactive
learner journey in the active player (the "learning loop")** — reusing the
existing mastery/assessment/recommendation services and the vanilla player to
deliver the user-observable value of the platform (learn → answer → see
mastery/recommendations improve). This is chosen over a framework frontend
migration (P0 Phase 2), the 2D slide-editor engine (P0 Phase 3), and
animation/simulation/video runtime persistence (P0 Phase 7) because it has the
highest user value, highest reuse, lowest risk, and directly completes the
core promise with a highly demonstrable result.

The formal version label (e.g. "P5") **requires product-owner confirmation**;
the repository does not itself define "P5" / "V2.0".

---

## 2. Starting repository state

- `git status --short` → clean.
- `git branch --show-current` → `feature/individual-user-foundation`.
- HEAD → `cd0f2b4` `docs(p4): define WS7 scope and discovery audit`.

## 3. P4 completion status

P4 is **COMPLETE** (WS1–WS6 all delivered, per `P4_SCOPE_AND_FOUNDATION.md`
and `P4_WS6_VERIFICATION_AND_RELEASE_GATE.md`):

- WS1 deployment-gate fixes (Celery module path, dead dispatch/metrics).
- WS2 live export flow (ownership-checked, progress-tracked, idempotent).
- WS3 vector semantic RAG retrieval with positional fallback.
- WS4 bounded TTL/LRU caches.
- WS5 browser E2E smoke on the active vanilla SPA.
- WS6 full release gate (fast/PG/e2e/ruff/mypy Δ=0/single head/secret/diff).

## 4. Why no P4 WS7 exists

`P4_SCOPE_AND_FOUNDATION.md` defines workstreams WS1–WS6 only; WS6 is explicit
as the final P4 workstream and P4 is declared complete. `P4_WS6_...md` §16
confirms *"WS6 is the final P4 workstream... P4 is complete."* The prior
`P4_WS7_SCOPE_AND_DISCOVERY_AUDIT.md` established there is **no authoritative P4
WS7**; the only "WS7" strings are P1/P2 phase-internal numbering. Post-P4 work
belongs to a **new phase**, not an invented WS7.

## 5. Current product baseline (verified from repository)

### Backend / API (18 routers under `backend/app/api/v1/`)
Auth (register/login/refresh/logout/OAuth + Redis revoke) → presentations
(CRUD/autosave/versions/lessons) → player → quiz → assistant (AI tutor) →
visual canvases (SVG KB canvas) → animation (planner + runtime) → video
(create + runtime) → simulation → exports → effectiveness → folders → health →
metrics → storage.

### Frontend (`backend/frontend/`)
**Vanilla JS multi-page SPA** (no framework, no build, no package.json):
`index/signin/signup/upload/processing/player.html` + `assets/app.js`,
`assets/style.css`. Player renders per-topic concept+visual and invokes
canvas / animation (Motion Engine) / video / simulation runtimes.

### Database (61 model files; Alembic 0001→0028, single head)
Presentations, generated lessons + versions + blocks, topic outlines, concepts,
documents/chunks, RAG vector index + chunk embeddings, visual KB canvas/node/
edge, educational memory, learning sessions/events/activities, analytics,
quizzes + attempts, assistant sessions/conversations/messages, exports.

### RAG / AI
`AIContentService` (Gemini/OpenAI/local providers, retries/timeouts/rate-limit/
cache/cost). **WS3 vector semantic retrieval** wired into the AI tutor
(`learning_assistant_service` embeds query + cosine-similarity + threshold +
deterministic tie-break, positional fallback). Full embedding lifecycle
(pipeline/refresh/cleanup/integrity/stats) + Celery tasks.

### Workers
Celery `app/workers.celery_app` + `tasks` + `rag_tasks`; queues;
beat schedule (health/analytics/cleanup/embeddings); DLQ, ack-late, bounded
retry; export + embedding + ingestion + analytics jobs.

### Learner intelligence (exists, under-connected to the active player)
- Mastery / `educational_memory_service` (DB-backed + BoundedCache).
- `recommendation_engine` (deterministic mastery-driven NextAction).
- `adaptive_assessment_engine` (difficulty ladder, exact-match eval).
- `learning_context_service` / `learning_event_service` / `effectiveness_service`.

### Exports
PDF, DOCX, PPTX, Markdown, HTML, CSV/TSV, Flashcards, Mindmap, ZIP
(`export_service`). **Gap:** presentation-level analytics export raises
`NotImplementedError`.

### Observability / CI / Docker
structlog + request IDs + Prometheus + health/readiness; `.github/workflows/
ci.yml` (lint/unit/integration/migration-head/live-PG/postgres/secret-scan/
mypy/docker-build); multi-stage `Dockerfile` (gunicorn+uvicorn prod, non-root);
`docker-compose.yml` (postgres/redis/minio/backend/worker/beat).

## 6. Current user journey (traced; where supported)

```
sign in
  → upload source (PDF/DOCX/PPTX/TXT) ............ COMPLETE, hardened
  → AI presentation/lesson generation ............ COMPLETE (WS2 live, exportable)
  → topic selection + per-topic visual ........... COMPLETE (canvas/animation/video/sim)
  → player presentation ......................... COMPLETE (linear per-topic slides)
  → in-lesson assessment / quiz ...............  INCOMPLETE (player simplified; no in-lesson quiz)
  → persistent user progress ...................  INCOMPLETE (player tracks only topic index; no per-user persistence)
  → mastery / recommendation to learner ........  INCOMPLETE (services exist; not surfaced in active player)
  → learning insights / effectiveness ..........  PARTIAL (effectiveness endpoints exist; analytics export absent)
```

**Friction / incomplete experience:** the content is rich, but the *learner
cannot see or act on their own learning state* within the product flow. This is
a product-completeness gap, not an infrastructure gap.

## 7. Completed foundation vs product capability

| Layer | Assessment |
|-------|-----------|
| Security / auth / ownership | FOUNDATION — COMPLETE |
| DB reliability / migrations | FOUNDATION — COMPLETE |
| Worker reliability / DLQ / idempotency | FOUNDATION — COMPLETE |
| Caching bounds | FOUNDATION — COMPLETE (WS4) |
| Observability / CI / Docker | FOUNDATION — COMPLETE |
| Browser testing | FOUNDATION — COMPLETE (WS5) |
| Content generation (presentation→lesson→topic→visual) | PRODUCT — COMPLETE-ish |
| Export | PRODUCT — COMPLETE (WS2) |
| RAG semantic retrieval | PRODUCT — COMPLETE (WS3) |
| **Interactive learner journey / learning loop** | **PRODUCT — UNDERDEVELOPED** |
| 2D slide editing (authoring) | PRODUCT — UNDERDEVELOPED (linear model) |
| ML/DL adaptive intelligence | PRODUCT — FUTURE (eval-gated) |

**Conclusion:** the backend is production-hardened, but the product is not
feature-complete for the *learner*. The core promise ("AI-native *learning*
platform") is only partially delivered end-to-end: generation closes, the
learning/retention loop does not.

## 8. Authoritative roadmap sources

- `P0_DEEP_ARCHITECTURE_AUDIT.md` §PART U "Dependency-Aware Roadmap"
  (Phases 1–14) — **HISTORICAL roadmap / product direction**, not a live
  implementation schedule.
- `P1_INDIVIDUAL_FOUNDATION_REPORT.md` §15 — Phase 2+ out-of-scope list
  (HISTORICAL).
- `P1_SECURITY_FOUNDATION_REPORT.md` §18 — Phase 2+ out-of-scope list.
- `P2_DATA_RUNTIME_FOUNDATION_REPORT.md` §29 — "Documented-and-deferred"
  (HISTORICAL).
- `P3_P4_HANDOFF_AUDIT.md` §4.2 — deferred items.
- `P4_SCOPE_AND_FOUNDATION.md` — authoritative for P4 (COMPLETE).
- `P4_WS6_VERIFICATION_AND_RELEASE_GATE.md`, `P4_WS7_SCOPE_AND_DISCOVERY_AUDIT.md`.

No document defines a *current* authoritative schedule beyond P4; the P0
phases are direction, not committed scope. **Version/label is not defined by
any authoritative doc.**

## 9. Historical / deferred roadmap items (from P0 + P1–P3)

| Item | Source | Status |
|------|--------|--------|
| Production frontend (framework, routing, state) | P0 Phase 2 | HISTORICAL / NOT REQUIRED unless product need |
| PowerPoint-class 2D slide-element editor | P0 Phase 3 | HISTORICAL candidate ("single biggest product gap" per P0) |
| AI-native generation onto 2D model + RAG | P0 Phase 4 | PARTLY DONE (RAG=WS3); 2D-gen not done |
| Visual breadth / accessibility | P0 Phase 5 | HISTORICAL |
| Advanced visual rendering (WebGL/SVG/DOM) | P0 Phase 6 | HISTORICAL |
| Animation engine hardening (persist timelines; Redis/DB runtime) | P0 Phase 7 / risk M2 | DEFERRED (P0); infra, low user-visible value |
| Simulation engine (registry + persistence + sandbox) | P0 Phase 8 | PARTIAL — 5 hardcoded in-memory defs, no DB model |
| Knowledge graph + learning events | P0 Phase 9 | PARTIAL — visual KB canvas + heuristic mastery |
| ML/DL learner intelligence | P0 Phase 10 | FUTURE (explicitly eval-gated) |
| Adaptive learning | P0 Phase 11 | PARTIAL — heuristic adaptive assessment exists |
| AI tutor 2.0 (vector-grounded) | P0 Phase 12 | PARTLY DONE (WS3 semantic retrieval in tutor) |
| Multimodal voice/video | P0 Phase 13 | EXISTING video+TTS (not standalone voice agent) |
| Performance/security/scale + CI gates | P0 Phase 14 | MOSTLY DONE (CI + gates exist; tracing/HA remain) |
| Quiz IDOR fix | P1 | DONE (P1) |
| RAG vector retrieval | P2/P4 | DONE (WS3) |
| Unbounded caches → bounded | P3/P4 | DONE (WS4) |

## 10. Post-P4 candidates (evidence-based)

### Candidate A — Complete the interactive learner journey (the "learning loop")
**Source/evidence:** current player simplification
(`lesson_player_service.py`: only topic index, no quiz/progress/notes,
in-memory `_SESSIONS`); existing learner-intelligence services (mastery,
recommendation, adaptive assessment, learning sessions/events, effectiveness)
already implemented + tested; quiz subsystem exists; exports exist.
**Objective:** make the learner's per-user learning state real and observable in
the active vanilla player: persistent progress, in-lesson checkpoints/quiz,
mastery tracking, and recommendation-driven next steps.
**User problem:** "I generated a great lesson, but the product doesn't tell me
how I'm learning or what to do next across sessions."
**Affected users:** individual learners (the core persona).
**Product value:** completes the core promise (learning, not just generation).
**Technical value:** activates existing, currently-underutilized learner
intelligence; high reuse.
**Current implementation level:** PARTIAL — backend services + models exist and
are tested; they are not wired into the active player as a persistent user flow.
**Major missing pieces:** per-user progress persistence in the player flow,
in-lesson assessment entry points, surfacing mastery/next-action to the user,
progress endpoints + player UI, E2E of the full loop.
**Dependencies:** WS2 (exports), WS3 (RAG tutor context), WS4 (bounded caches).
**Database impact:** likely a small additive migration (e.g. learner progress /
session-progress table) — see §15.
**Backend:** new/extended player + progress + assessment endpoints; reuse
adaptive/memory/recommendation services.
**Frontend:** enhance `player.html` (vanilla JS) with progress + checkpoint UI
— **no framework migration needed**.
**AI impact:** reuse WS3 RAG; assessment questions generated via AI quiz path.
**RAG impact:** none beyond existing.
**Worker impact:** possibly an analytics/aggregation task (reuse Celery).
**Performance:** small, bounded progress state; reuse WS4 bounded caches.
**Security:** ownership-404 on all progress/assessment; regression tests.
**Testing:** unit + integration + PG + browser E2E.
**Deployment:** low (no new services).
**Implementation complexity:** MEDIUM.
**Risk:** LOW–MEDIUM.
**Product impact:** HIGH — user-visible, demonstrable learning loop.

### Candidate B — PowerPoint-class 2D slide-element editor (P0 Phase 3)
**Source/evidence:** P0 calls this "the single biggest gap vs. the product
vision; currently linear"; `generated_block.py` uses only integer `position`
(no 2D coords).
**Objective:** 2D slide-element authoring model + editor (x/y/w/h/z/rotation,
layers, undo/redo, import/export parity).
**User problem:** users cannot author/edit true 2D slides, only view generated
linear content.
**Product value:** HIGH differentiation (presentation-tool parity).
**Current implementation level:** PARTIAL (linear model only).
**Major missing pieces:** new slide/element/layer/theme schema + migration,
editor CRUD, editor frontend, undo/redo, export golden, 2D generation.
**Database impact:** SIGNIFICANT migration (new tables).
**Backend/Frontend/AI impact:** LARGE; frontend editor UI; AI generation onto
2D.
**Testing complexity:** HIGH (editor + export golden).
**Deployment complexity:** MEDIUM–HIGH.
**Implementation complexity:** HIGH.
**Risk:** HIGH (biggest, most speculative surface).
**Product impact:** HIGH but slower to realize.

### Candidate C — Production frontend (framework) (P0 Phase 2)
**Source/evidence:** P0 Phase 2.
**Objective:** migrate vanilla SPA to a framework with routing/state/error/loading.
**User problem:** none demonstrably surfaced; current vanilla SPA works and is
browser-tested.
**Architectural reuse:** LOW for frontend (rewrite); backend unaffected.
**Risk:** MEDIUM–HIGH (rewrite of working, tested frontend).
**User-visible value:** LOW (user likely cannot notice).
**Verdict:** NOT recommended — violates the "do not migrate for its own sake"
principle; no documented product need forces it. Only becomes appropriate if a
future phase (e.g. the 2D editor) needs an editor-grade frontend.

### Candidate D — Animation/simulation/video runtime persistence (P0 Phase 7 / risk M2)
**Source/evidence:** P0 risk M2 "in-memory runtime states (sim/animation/video/
lesson) lost on restart, not shared"; 5 hardcoded in-memory sim definitions.
**Objective:** persist runtime state to Redis/DB for HA + define simulations in DB.
**User problem:** none immediate for a single learner (HA/replica concern).
**User-visible value:** LOW (user cannot notice in normal use).
**Product impact:** LOW now; infra.
**Verdict:** NOT recommended as the *next* phase; it is an infrastructure
dependency that may accompany later scale. Superseded in priority by closing
the learner loop.

## 11. Candidate scoring matrix

Scale 1–5 (5 = best). These are **ENGINEERING/PRODUCT ASSESSMENT** values, not
objective measurements.

| Criterion | A: Learner journey | B: 2D editor | C: Framework FE | D: Runtime persistence |
|-----------|-------------------|--------------|-----------------|------------------------|
| Product Value | 5 | 5 | 1 | 2 |
| User Value (noticeable) | 5 | 4 | 1 | 1 |
| Strategic Alignment (core promise) | 5 | 4 | 1 | 2 |
| Existing Foundation Reuse | 5 | 3 | 1 | 4 |
| Technical Feasibility | 5 | 3 | 4 | 4 |
| Security Risk (lower=better→score) | 4 | 3 | 4 | 4 |
| Performance Risk | 4 | 3 | 3 | 3 |
| Implementation Complexity (lower=better→score) | 4 | 2 | 3 | 4 |
| Time-to-Value | 5 | 2 | 3 | 4 |
| Differentiation | 3 | 5 | 1 | 1 |
| Scalability Impact | 3 | 2 | 2 | 4 |
| **Weighted total** | **48** | **36** | **24** | **33** |

**Reasoning:**
- **A** wins on user value, reuse (the learner-intelligence layer is already
  built and tested), feasibility, time-to-value, and completing the core
  promise.
- **B** scores highest on differentiation but is high complexity/risk and slow
  to value; better as a *later* phase once the learner journey is delivered.
- **C** is rejected under the "no framework migration without product need"
  rule (user-visible value ≈ none).
- **D** is infra with low user-visible value; deferred.

## 12. Candidate analysis

See §10 for full analysis. The recommended candidate is **A** because it closes
the actual product gap (an incomplete learning loop) using mostly existing,
already-tested machinery — the definition of high-leverage, low-risk,
demonstrable work.

## 13. Security impact (candidate A focus)

- **Threats:** IDOR on a learner's progress/assessment/session records; cross-user
  leakage of mastery/memory; unauthorized writes to another user's learning state.
- **Existing protection:** uniform ownership-404 pattern, JWT + refresh, Redis
  revocation, ownership-404 on presentations/export (P1, WS2), session
  isolation.
- **Additional protection required (future):** owner-scoping on every new
  progress/assessment endpoint (walk record→user), per-user caps, regression
  tests for unauthorized access (401/404).
- **Required regression tests (future):** unauthorized read/write of another
  user's progress/assessment → 404; two-user isolation (see existing
  `test_two_user_isolation.py` pattern).
- Overall security impact: **LOW–MEDIUM**, provided ownership-404 is enforced.
  (Candidate B: MEDIUM–HIGH, editor CRUD surface. C: LOW. D: LOW.)

## 14. Database impact

- Current head: `0028_ws10_idempotency_key_index` (single head, verified).
- **Candidate A:** minor additive migration (e.g. a learner-progress /
  session-progress row keyed by user+lesson, or reuse `learning_session`/
  `learning_activity` which already have slide/block positions). **EXISTING
  SCHEMA MAY SUFFICE FOR MVP** (learning_session/event/activity models already
  exist). Reuses bounded caps; SQLite fast path + PG verification.
- **Candidate B:** significant new slide/element/layer/theme tables + migration.
- **C:** none. **D:** new runtime/simulation persistence tables.
- Production stays PostgreSQL. No migration created in this audit.

## 15. Frontend impact

- Current frontend: **vanilla JS SPA** (`backend/frontend/`). **Candidate A
  preserves it** — enhance `player.html`/`assets/app.js` (progress UI,
  in-lesson checkpoint/quiz entry, mastery/next-step surface) with plain fetch
  + localStorage auth patterns. **No framework migration** (rejected per §12/§19
  of the governing rules).
- Candidate B would likely require a richer editor frontend and is a
  later-phase decision.

## 16. AI / RAG impact

- Candidate A reuses **WS3 semantic vector RAG** for the AI tutor context; adds
  AI-generated in-lesson assessment questions via the existing quiz-generation
  path. No retrieval rework. No live AI in ordinary CI — provider boundary is
  faked in deterministic tests.
- B adds AI *generation onto a 2D model*; larger AI-surface change (later).

## 17. Worker / async impact

- Candidate A may add a Celery task (e.g. per-lesson mastery/analytics
  aggregation) reusing the existing DLQ/ack-late/bounded-retry pattern. No
  fire-and-forget; deterministic state transitions; no arbitrary sleeps.

## 18. Performance / resource impact

- Candidate A introduces small per-user progress state; **reuse WS4 bounded
  caches**; no N+1 (batch-load), no unbounded memory/jobs. Assessment +
  progression are bounded per-user caps.

## 19. Testing strategy (future, not added now)

| Layer | Coverage |
|-------|----------|
| Unit | progress service, mastery/next-action surfacing, assessment wiring |
| Integration | route→service→persistence for progress + checkpoint flows |
| PostgreSQL | any new migration/FK + PG-specific behavior |
| Browser E2E | real player: load lesson → advance → answer checkpoint → see mastery/next-step (reuse WS5 infra) |
| Security regression | unauthorized access to another user's progress/assessment |
| Worker integration | aggregation task state transitions |
| AI provider boundary | fake provider; real service path |

## 20. Dependency graph

```
WS1..WS6 (P4 complete) ──►  Candidate A: Learner Journey (recommended)
                                 │
                                 ├── (optional later) Candidate B: 2D editor
                                 └── (infra when scaling) Candidate D: persistence
```
Candidate A depends on WS2 (exports), WS3 (RAG tutor), WS4 (bounded caches) —
all INHERITED. C is independent/low value. B is largely independent but largest.
D is an infra dependency for later scale.

## 21. Recommended next phase

**Name (tentative):** **POST-P4 PHASE — Interactive Learner Journey**
(Version label e.g. "P5" **REQUIRES PRODUCT-OWNER CONFIRMATION** — not defined
by any authoritative document.)

**Objective:** complete the learner's in-product loop — from "I generated/watch
a lesson" to "I know what I've learned, how I did, and what to do next."

**User problem:** the platform generates rich content but does not yet close the
learning loop for its individual learner.

**Expected outcome:** a learner can, inside the active player: follow a lesson,
answer in-lesson assessment checkpoints, see persistent progress and mastery,
and receive recommendation-driven next actions — all ownership-isolated and
exportable where relevant.

**Why now:** P4 hardened the foundation and delivered generation + RAG + export;
the largest remaining product gap is the learner's own measurable journey, and
it reuses existing, already-tested machinery.

**Why this beats alternatives:** highest user value + reuse + time-to-value +
lowest risk; it does not require a risky 2D schema or a framework rewrite.

**MVP boundary:** see §22.

## 22. MVP boundary for the recommended phase

**MUST HAVE**
- Persistent per-user lesson progress in the active vanilla player (resumable).
- In-lesson assessment checkpoint(s) driving the existing adaptive/mastery
  services; persisted attempt/result.
- Mastery + next-action surfaced to the learner (existing recommendation engine).
- Ownership-404 + per-user caps + two-user security regression tests.
- Browser E2E of the loop (load → advance → checkpoint → mastery/next-step).

**SHOULD HAVE**
- Cross-session resume; minimal progress dashboard in the player.
- Export of a learner's own progress/insights (address the analytics-export gap
  only if in scope).

**NICE TO HAVE**
- Richer visual/type-specific checkpoint variants; effectiveness/insight page.

**EXPLICITLY OUT OF SCOPE (MVP)**
- 2D slide-editor engine (later phase) — do NOT build the 2D schema now.
- Framework frontend migration — preserve vanilla SPA.
- ML/DL, knowledge-graph breadth, collaboration/teacher roles, mobile app,
  multi-tenant SaaS, runtime persistence for HA (deferred).

## 23. Alternative candidates

- **B (2D editor):** not selected now — high complexity/risk, slow time-to-value;
  appropriate as a later, separately-scoped phase when authoring power becomes
  the top differentiator. Dependency to promote it: a product decision to pursue
  "presentation-tool parity" over "learner experience."
- **C (framework FE):** not selected — no product need evidenced; becomes
  appropriate only if B (or another phase) requires an editor-grade frontend.
- **D (runtime/HA persistence):** not selected — infra; becomes higher priority
  only when multi-replica/scale or a real availability requirement exists.

## 24. Future checkpoint plan (for the selected phase; not executed)

- Phase-C0: baseline + formal scope confirmation (VERSION LABEL OWNER-OK).
- Phase-C1: foundation — progress service/schema + ownership + caps.
- Phase-C2: core capability — in-lesson assessment + mastery surfacing.
- Phase-C3: integration + WS3-RAG/WS2-export reuse + worker aggregation.
- Phase-C4: UX in the vanilla player + browser E2E of the full loop.
- Phase-C5: hardening/release — full gate + report.
(Adjust to actual scope at implementation time.)

## 25. Release gate (for the selected phase)

- Fast suite (`pytest tests -m "not postgres"`)
- PostgreSQL suite (`pytest tests/postgres -m postgres`, real PG)
- Browser E2E (`pytest tests/e2e/test_smoke.py -m e2e --browser chromium`)
- Ruff; mypy Δ=0; Alembic single head; secret scan; `git diff --check`; clean tree;
  Docker/CI as applicable.

## 26. Risk register

| Risk | Probability | Impact | Mitigation | Owner/Decision |
|------|-------------|--------|------------|----------------|
| Scope creep into 2D editor / FE rewrite | MED | HIGH | Enforce §22 EXCLUSIONS | Program owner |
| IDOR on learner progress/assessment | LOW | HIGH | ownership-404 + two-user tests | Engineering |
| New migration complexity | LOW | MED | PG verification + single head | Engineering |
| AI assessment cost | MED | LOW | bound via existing provider caps; fake provider in CI | Engineering |
| Mastery surfaced but not trusted by users | MED | MED | validation + clear thresholds | Product owner |
| Deployment (new endpoints) | LOW | MED | additive, no new services | Engineering |
| Version-label ambiguity | MED | LOW | owner confirmation of "P5" | Product owner |

## 27. Do-not-build-yet list

- 2D slide-element editor / new 2D schema (until scoped as a later phase).
- Framework (React/Next.js/Vite) frontend migration (no evidenced product need).
- ML/DL learner intelligence (eval-gated; must beat existing heuristics first).
- Knowledge-graph breadth, multi-role/teacher-student, collaboration.
- Mobile applications.
- Microservices/Kubernetes/vector-DB migration (no scale evidence).
- Animation/simulation/video runtime HA persistence (until a real HA need).

## 28. Open decisions

**ENGINEERING DECISIONS (deferred to implementation):** exact progress schema
vs. reuse of `learning_session`/`learning_activity`; checkpoint ↔ quiz
integration contract; mastery surfacing representation; worker aggregation task.

**PRODUCT-OWNER DECISIONS (cannot be answered by engineering):** the **version
label (e.g. "P5")**; target-user confirmation; whether in-lesson assessment is
quiz-form or lightweight checkpoints; whether to pursue presentation-tool parity
(2D editor) before/after the learner journey; feature priority.

## 29. Final recommendation

Adopt **POST-P4 PHASE — Interactive Learner Journey** (Candidate A) as the next
major development phase: complete the learner's measurable, persistent,
user-visible loop in the active vanilla player by wiring the existing
mastery/adaptive/recommendation/quiz machinery into the player flow, with the
staged MVP and release gate in §22/§25. Confirm the version label and remaining
product-owner decisions (§28) before implementation. Do **not** build the 2D
editor, framework frontend, or runtime-HA-phase yet.

---

*End of post-P4 roadmap decision audit. Documentation only; no application,
migration, test, CI, Docker, frontend, or dependency changes were made.*
