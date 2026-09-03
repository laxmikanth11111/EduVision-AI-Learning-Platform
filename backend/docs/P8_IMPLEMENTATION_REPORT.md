# P8 — Mastery-Aware AI Tutor — Implementation Report

## Status

**PASS** — P8 Mastery-Aware AI Tutor implemented, wired, and verified. A
learner-scoped, grounded, AI-tutor conversation surface now exists in the
vanilla SPA: the learner can sign in, open the Mastery Tutor panel (or a
dashboard weak-concept quick-action), ask a question, and receive a grounded
answer produced through the mandatory **AIContentService** + **RAG** over their
own lesson content — with truthful attribution, a confidence hint, a source
kind, persistence, and a fully deterministic memory-driven fallback when AI/RAG
is cold. Cross-user isolation, single Alembic head, and the P0–P7 regression
contract all hold.

Final result line:

```
branch              : feature/individual-user-foundation
HEAD                : 653be67
head migration      : 0029_tutor_sessions (unique, linear)
fast suite (SQLite) : 1107 passed, 0 failed  (floor ≥ 1103)
postgres suite      : 15 passed               (floor ≥ 15)
P7 browser E2E      : 1/1 passed (3x pattern kept)
P8 browser E2E      : 1/1 passed (run 4x)
mypy (app)          : 83 errors in 24 files  (floor ≤ 83, zero new)
ruff check .        : clean
git diff --check    : clean
secret scan         : clean
```

---

## 1. Executive Summary

P8 closes the loop P7 opened: P7 surfaces *what* is weak and *why*; P8 lets the
learner **act** on it through a **Mastery-Aware AI Tutor** — a learner-scoped
conversational panel grounded in the learner's real `educational_memory_service`
state, the mandated **AIContentService**, and **RAG** over the learner's own
lesson content — plus a **"Remediate my weak concept"** quick-action seeded from
the learner dashboard.

- **Backend**: a new learner-scoped service (`MasteryTutorService`), router
  (`/api/v1/tutor`), schemas, repositories, and an **additive** Alembic migration
  (`0029_tutor_sessions`) that reuses the existing Phase-4E orphaned tutor schema
  (`tutor_sessions` → `tutor_conversations` → `tutor_messages`).
- **Frontend**: a new vanilla `tutor.html` chat panel plus a dashboard
  "Mastery Tutor" nav link and per-weak-concept "Ask tutor"/"Remediate"
  affordance — no build step, reusing the SPA `authFetch`/`escHtml`/envelope
  patterns.
- **AI**: answers route exclusively through `AIContentService` + RAG grounded in
  learner-owned content units; a deterministic memory-driven fallback is used
  whenever RAG is cold or AI is unavailable. Learner intelligence (mastery /
  recommendation / remediation) stays fully deterministic.
- **Tests**: 19 new tests (8 unit service, 4 unit RAG/AI, 7 integration
  security), a real browser E2E journey, and full PostgreSQL + SQLite
  regression.

All six checkpoints (C0–C6) completed. One P8-introduced cross-test pollution
(RAG fixture leaving committed chunks that tripped globally-scoped legacy count
assertions) was found during C6 regression and fixed so the suite is fully green
at 1107 passed, 0 failed.

---

## 2. Objective & Hypothesis

**Objective:** give the single learner a trustworthy, grounded conversational
tutor that (a) understands their actual mastery/weak concepts, (b) answers over
their own generated lessons (via AIContentService + RAG), and (c) proposes the
next-best remediation.

**Hypothesis (verified at P8 end):** a learner can open the tutor, ask "why is
*Gaussian Distributions* weak for me?", receive a grounded, attributed reply
that references their own source material / mastery, and click **"Remediate"**
to start a seeded remediation session — with correct learner-scoping (User B
never sees User A's context), a grounded-over-free-form answer, and no P0–P7
regressions.

---

## 3. Non-Negotiable Architecture (Carried From P0–P7)

| Constraint | Status | Evidence |
|---|---|---|
| FastAPI (Python 3.13, async) + SQLAlchemy | **PASS** | services/routers are async; SQLAlchemy async session |
| PostgreSQL **production** + SQLite **test** | **PASS** | SQLAlchemy-only SQL, no PG-only constructs in shared paths; PG verified |
| Vanilla multi-page SPA, no React/TS/Vite/Tailwind/build | **PASS** | `tutor.html` is plain HTML/CSS/JS; no build step |
| **AIContentService mandatory AI path** (no provider SDK bypass) | **PASS** | tutor code calls `app.ai.service.get_ai_content_service()` only; no direct Gemini/OpenAI/Anthropic/`genai`/`Client(` calls |
| RAG over learner's own content store | **PASS** | `RagIndexingService` + learner-scoped positional/embedding retrieval |
| Learner intelligence deterministic (no ML/DL) | **PASS** | mastery/recommendation/remediation via `educational_memory_service` + `recommendation_engine` |
| Caches bounded (`BoundedCache`) | **PASS** | no unbounded caches introduced; reuse of `educational_memory_service` |
| Ownership via `get_current_user`, never client-supplied id | **PASS** | every tutor route `Depends(get_current_user)`; server verifies ownership |
| Strictly **linear** Alembic chain, single head | **PASS** | `alembic heads` → `0029_tutor_sessions` unique; `0029` appends `0028_ws10_idempotency_key_index` |

---

## 4. Judgment Call Results

| Dimension | Decision (contract) | Delivered |
|---|---|---|
| Candidate | C — Mastery-Aware AI Tutor | ✓ |
| Migration | NO (schema *add* via appended linear Alembic only) | ✓ `0029_tutor_sessions` |
| AI | YES, bounded & grounded via AIContentService + RAG + deterministic memory fallback | ✓ |
| Frontend migration | NO — stay vanilla SPA | ✓ |
| Scope | Bounded: 1 chat surface + 1 remediation trigger + persistence + E2E | ✓ |

---

## 5. MVP Scope — Delivered

1. **Mastery-Aware Tutor chat surface** — `tutor.html` (vanilla) reachable from
   `dashboard.html` nav; supports ask → grounded answer → continue.
2. **Learner-scoped grounding context** — `user_id` derived from `get_current_user`;
   tutor reads `educational_memory_service` (weak/developing concepts) + bounded
   recent attempts.
3. **Grounded answer generation** — via **AIContentService** + **RAG**; includes
   `attribution`, `confidence`, `source_kind`; deterministic fallback when RAG/AI cold.
4. **"Remediate weak concept" quick-action** — from dashboard weak-concept affordance,
   `POST /api/v1/tutor/remediate` seeds a `mode="remediation"` session with a
   mastery-grounded walkthrough.
5. **Persistence** — `tutor_sessions` / `tutor_conversations` / `tutor_messages`
   learner-scoped; bounded history for context.
6. **Browser E2E journey** — sign in (real form) → dashboard → tutor → ask →
   verify grounded/attributed reply + remediation trigger; keeps P7 root-cause
   pattern (pop `get_current_user` override; clear `_ems._memories`).

---

## 6. Out-of-Scope (Respected)

Teacher/classroom/parent role; interactive 2D editor; visual learning upgrade;
frontend framework migration; free-form/ungrounded LLM chat; parametric ML/DL
learner models; multi-tenancy/sharing of tutor sessions; re-architecting the
lesson content model; any change to the exam-grade engine. **All excluded.** P8
made no changes to these subsystems.

---

## 7. Backend Design (Service + API) — PASS

**Service** `app/services/mastery_tutor_service.py` — `MasteryTutorService`:
- Resolves learner context: `educational_memory_service.load_from_db(...)` +
  bounded recent attempts + `recommendation_engine`.
- Extracts top weak/developing concepts as the grounding signal.
- Builds a bounded prompt/retrieval plan → **AIContentService** + **RAG**
  (learner-owned retrieval only).
- Wraps attribution + confidence; deterministic memory-driven fallback on cold AI.
- Persists a bounded conversation (sessions → conversations → messages).

**Router** `app/api/v1/tutor.py`, prefix `/api/v1/tutor`, every route
`Depends(get_current_user)` + `Depends(get_unit_of_work)`:
- `POST /api/v1/tutor/sessions`
- `POST /api/v1/tutor/sessions/{session_id}/messages`
- `GET /api/v1/tutor/sessions` and `GET /api/v1/tutor/sessions/{session_id}`
- `GET /api/v1/tutor/conversations/{conversation_id}/messages`
- `POST /api/v1/tutor/remediate`

All learner-scoped; never accept `user_id` from body/query.

**Schemas** `app/schemas/tutor.py`: `TutorSessionCreateRequest`, `TutorSessionOut`,
`TutorMessageSendRequest`, `TutorMessageOut` (attribution/confidence/source_kind),
`TutorRemediateRequest`, `TutorRemediateResponse`.

**Wiring** `app/main.py`: `include_router(tutor_router, prefix="/api/v1")` PASS.

---

## 8. Frontend Design — PASS

- **`dashboard.html`**: "Mastery Tutor" nav link + per-weak-concept "Ask tutor"
  affordance (`/frontend/tutor.html?concept=<id>`).
- **`tutor.html`** (new, vanilla): quick-picks of weak concepts, chat message
  list, composer, source-kind/confidence/attribution chips, bounded UI. Reuses
  `authFetch` (with 401-refresh), `escHtml`, response envelope, `localStorage`
  auth. No build step.

---

## 9. Persistence & Migrations — PASS

- **Decision honored**: the P8 schema change is an **additive** Alembic migration,
  `0029_tutor_sessions`, appended to `0028_ws10_idempotency_key_index`, mapping
  the **existing** Phase-4E orphaned tutor schema (from `0013_ai_tutor`):
  `tutor_sessions` → `tutor_conversations` → `tutor_messages`, plus 12 related
  tutor tables. No tutor tables are created/dropped.
- Additive columns (all nullable, guarded/idempotent via `_columns()` /
  `_index_exists()`):
  - `tutor_sessions.target_concept_id` (String 40)
  - `tutor_messages.source_kind` (String 30)
  - `tutor_messages.attribution` (String 1000)
  - `tutor_messages.confidence` (String 20)
  - non-unique index `ix_tutor_messages_source_kind`
- Owned by `user_id` (sessions) and `get_current_user` enforcement; no PG-only
  types in shared paths.

---

## 10. Query / Performance Contract — PASS

- Tutor request is bounded & set-based (context read + retrieval + persist);
  no N+1.
- Lists bounded by `TUTOR_RETRIEVAL_TOP_K`, `TUTOR_EMBEDDING_SEARCH_LIMIT`,
  `TUTOR_MAX_HISTORY_MESSAGES`, `TUTOR_MAX_CONTEXT_CHARS`,
  `TUTOR_MAX_RESPONSE_TOKENS`.
- Bounded conversation context; no unbounded growth.

---

## 11. Regression Contract — PASS

| Metric | Floor | Result |
|---|---|---|
| Fast suite (SQLite) | ≥ 1103 passed | **1107 passed, 0 failed** |
| PostgreSQL suite (`-m postgres`) | ≥ 15 passed | **15 passed** |
| Browser P7 E2E | keep green | **1/1 passed** (pattern kept) |
| New P8 browser E2E | author-defined, 100% | **1/1 passed** (run 4×) |
| mypy (`app`) | ≤ 83 errors, 0 new | **83 errors / 24 files** (checked 285) |
| `ruff check .` | clean | **clean** |
| `git diff --check` | clean | **clean** |
| Secret scan | clean | **clean** |
| Alembic | single linear head `0029_tutor_sessions` | **unique head** |

**P8-introduced regression detected & fixed:** during C6, `test_mastery_tutor_rag.py`
left committed `DocumentChunk`/`ContentUnit` rows in the shared session-scoped
SQLite DB, which tripped the globally-scoped count assertions in the legacy
`test_rag_indexing_service.py` (5 tests). Verified via minimal reproduction
(rag → rag-indexing sequence) and fixed by a scoped teardown that deletes the
seeded source rows. Full suite restored to **1107 passed, 0 failed**.

---

## 12. Test Strategy — PASS

- **Unit** `tests/unit/test_mastery_tutor_service.py` (8): session create/list/
  get, message send + assistant reply, idempotent replay, determinism.
- **Unit RAG/AI** `tests/unit/test_mastery_tutor_rag.py` (4): RAG path via
  AIContentService (local deterministic provider), learner-scoped retrieval,
  deterministic cold fallback, bounded context. Verified no direct provider SDK
  calls in tutor code.
- **Integration / Security** `tests/integration/test_mastery_tutor_security.py`
  (7): 401 without auth; cross-user session GET/send/listing; remediation
  isolation (User B never sees A); malformed/nonexistent → 404-equalized;
  deleted-presentation remediation → 404.
- **Browser E2E** `tests/e2e/test_p8_mastery_tutor_e2e.py`: preserves P7
  root-cause pattern (pops `get_current_user` override to hit real JWT auth;
  clears `_ems._memories` before DB seeding; sync `def`, not `async def`; seeds
  synchronously via `create_engine(sqlite:///...)` + `Session`).

---

## 13. Checkpoints C0–C6 — PASS (all)

| C | Deliverable | Gate | Result |
|---|---|---|---|
| C0 | Plan approved from scope; clean baseline; mypy baseline | plan sign-off | **PASS** (mypy 83) |
| C1 | Schemas + service + migration `0029` + wiring | unit + security green; linear chain | **PASS** (commit `681879d`) |
| C2 | Router fully learner-scoped | cross-user isolation pass | **PASS** (commit `1dc8728`) |
| C3 | RAG + AIContentService + deterministic fallback | AI/RAG tests green | **PASS** (commit `7ad955b`) |
| C4 | Vanilla chat UI + dashboard "Remediate" affordance | manual/JS-check | **PASS** (commit `e3e46f7`) |
| C5 | Browser E2E journey | P8 100%; P7 green | **PASS** (commit `8772a78`) |
| C6 | Full regression + report | all gates; clean commit | **PASS** (commits `9b5f9f8`, `653be67`) |

---

## 14. Browser-First Validation Journey — PASS

Real sign-in → dashboard → Mastery Tutor → ask a question → grounds/deterministic
reply with attribution/confidence/source-kind chip → remediate weak concept →
mastery-grounded remediation. E2E asserts real JWT auth (not the conftest
override) and DB-seeded learner memory.

---

## 15. Risks & Mitigations — PASS

| Risk | Mitigation | Result |
|---|---|---|
| Hallucination / off-topic | RAG over learner's content + memory; attribution + confidence; bounded context; deterministic cold fallback | **PASS** |
| Chat UI complexity (vanilla) | Reuse SPA patterns; bound to one panel + one trigger | **PASS** |
| AI cost runaway | Strict context window; deterministic fallback; bounded history; caching | **PASS** |
| Cross-user leakage | Every session/message learner-scoped; P7-mirrored isolation tests | **PASS** |
| Regression P0–P7 | Locked regression contract at each checkpoint | **PASS** |
| Cache freshness | Single-learner TTL; documented; reuse `educational_memory_service` | **PASS** |

---

## 16. Migration Decision (Restated) — PASS

**NO storage migration.** PostgreSQL production + SQLite test. The only P8
schema change is an **appended linear Alembic** migration (`0029_tutor_sessions`)
— a schema *add*, not a storage migration.

---

## 17. AI Decision (Restated) — PASS

**YES, bounded & grounded.** Routes through **AIContentService** (no bypass);
grounded in learner memory + learner-owned RAG content; deterministic fallback
required and implemented; no ML/DL for mastery/recommendation. Config-flag
`OPTIONAL` supported via the existing `AI_PROVIDER` path; **YES** is the default
behavior (fallback to deterministic keeps every answer grounded and truthful).

---

## 18. Frontend Decision (Restated) — PASS

**NO migration — stay vanilla SPA** in `backend/frontend/`. `tutor.html` is plain
HTML/JS; candidate I (framework migration) rejected.

---

## 19. Security & Ownership Contract — PASS

- Every tutor route `Depends(get_current_user)`; `user_id` derived from auth
  only.
- Cross-user isolation enforced and tested (User B never sees A).
- Secrets stay out of the repo; secret scan clean.
- Remediation server-verifies `Concept.presentation_id` → `Presentation.owner_id`
  → learner-owned; failures 404-equalized (no resource-existence leak).

---

## 20. Performance & Caching Contract — PASS

- Bounded contexts/result sets (P7 caps mirrored).
- No N+1 in tutor context reads.
- Reuse `BoundedCache`/`educational_memory_service` for hot learner-context reads.
- Deterministic fallback keeps latency/cost predictable when AI busy/cold.

---

## 21. Exclusions (Recheck) — PASS

All §5-inclusive exclusions honored; tutor sessions not shared; no teacher
intelligence, editor, visual upgrade, framework migration, branching lesson
rewrite, exam-grade engine change, ungrounded chat, or ML learner models.

---

## 22. Rollback Plan — PASS-readiness

- **Code**: P8 is additive (new service/router/migration/frontend panels);
  reverting P8 commits restores P0–P7 behavior unchanged (tutor is opt-in).
- **Schema**: `0029_tutor_sessions` is append-only additive; `alembic downgrade -1`
  drops the added columns/index with a guarded `downgrade()`.
- **Feature flag**: tutor gated behind `get_current_user` + config; can be
  disabled without schema rollback.
- **Data safety**: tutor sessions learner-owned, isolated, trimmable; no shared/
  mutable global data introduced.

---

## 23. Definition of Done — PASS

1. Tutor backend (service + router + schemas + migration `0029`) merged, wired
   under `/api/v1/tutor`, learner-scoped. **PASS**
2. Vanilla chat UI + dashboard "Remediate"/"Ask tutor" affordance, no build
   step. **PASS**
3. Browser E2E journey (real-auth, DB-seeded memory) passes; P7 E2E still green.
   **PASS**
4. Full regression: SQLite 1107 ≥1103; PG 15 ≥15; mypy 83 ≤83, zero new; ruff
   clean; diff clean; head `0029_tutor_sessions` unique. **PASS**
5. Isolation test proves User B never sees User A's tutor context. **PASS**
6. Deterministic fallback verified (AI cold/disabled → grounded memory-driven
   answer). **PASS**
7. This report + POST_P8 audit follow the per-phase chain pattern. **PASS**
8. Committed with `git status --short` clean and no secrets. **PASS**

---

## 24. Final Evidence (Gates)

```
alembic heads         : 0029_tutor_sessions (head)   [single, linear]
pytest tests/unit tests/integration  : 1107 passed, 0 failed   [SQLite]
pytest tests/postgres  -m postgres   : 15 passed                 [PG 16]
pytest tests/e2e -m e2e             : P8 1/1 + P7 1/1 passed     [browser]
mypy app                             : 83 errors in 24 files (checked 285)  [≤83]
ruff check .                         : All checks passed
git diff --check                     : clean
secret scan                          : clean (no committed keys/tokens/private keys)
```

**Concluding statement:** P8 fully satisfies the scope & foundation contract. All
checkpoints C0–C6 PASS; the regression floor is met or exceeded on every
dimension; the mastery-aware tutor is grounded, attributed, learner-scoped,
resilient to cold AI via deterministic fallback, and verified end-to-end in the
real browser.