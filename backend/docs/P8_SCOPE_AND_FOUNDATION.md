# P8 Scope & Foundation — Mastery-Aware AI Tutor

**Authoritative implementation contract for P8.**
**Supersedes the P8 direction implied by earlier phase docs.**
**Status:** PLANNING
**Branch target:** `feature/individual-user-foundation`
**Parent of P8:** audit at HEAD `9b32ecd` (Post-P7 Product & Architecture Decision Audit)
**Type:** Feature phase — implementation occurs **only after** this doc is approved.

---

## 1. TL;DR

P8 closes the largest remaining product loop opened by P7: P7 surfaces *what* is weak and *why*; P8 lets the learner **act** on it through a **Mastery-Aware AI Tutor** — a learner-scoped conversational panel grounded in the learner's real `educational_memory_service` state, the mandated **AIContentService**, and **RAG** over the learner's lesson content — plus a **"Remediate my weak concept"** quick-action. It must stay a **vanilla SPA** in `backend/frontend/`, keep learner intelligence **deterministic**, hold **PostgreSQL + SQLite**, preserve the **linear Alembic chain** (head currently `0028_ws10_idempotency_key_index`), and keep the P0–P7 regression contract green.

---

## 2. Objective & Hypothesis

**Objective:** Give the single learner a trustworthy, grounded conversational tutor that (a) understands their actual mastery/weak concepts, (b) answers over their own generated lessons (via AIContentService + RAG), and (c) proposes the next-best remediation — measurably extracting more value out of the already-built learner intelligence than the passive dashboard alone.

**Hypothesis (testable at P8 end):** A learner can open the tutor, ask "why is *Gaussian Distributions* weak for me?", receive a grounded, attributed walkthrough over their lesson content, and click **"Remediate"** to start practice for that concept — with correct learner-scoping (User B never sees User A's context), a grounded-over-free-form answer, and no regressions.

---

## 3. Non-Negotiable Architecture (Carried From P0–P7)

- **Backend:** FastAPI (Python 3.13, async), SQLAlchemy.
- **Storage:** PostgreSQL **production** + SQLite **test**. SQLAlchemy-only SQL (no PG-only constructs in code paths that also run on SQLite).
- **Frontend:** **vanilla multi-page SPA** served from `backend/frontend/` via FastAPI `StaticFiles`. **No React / TypeScript / Vite / Tailwind / build step.** Shared patterns: `authFetch`, `escHtml`, `localStorage` auth (`user`/`access_token`/`refresh_token`), API base `/api/v1`, response envelope `res.json().data`.
- **AI:** **AIContentService is the mandatory AI path** — never bypassed. RAG over the learner's content store. Learner intelligence (mastery/recommendation) stays **deterministic** — no ML/DL for learner adaptation.
- **Caches:** bounded (`BoundedCache`), not unbounded.
- **Ownership:** every resource scoped by `user.id`, resolved from auth (`get_current_user`), never from the client.
- **Migrations:** strictly **linear** Alembic chain; append to head `0028_ws10_idempotency_key_index`.

---

## 4. P8 Judgment Call (Post-Audit Decision)

| Dimension | Decision | Rationale |
|---|---|---|
| Recommended candidate | **C — Mastery-Aware AI Tutor** | Closes the P7 "view → action" loop; highest user value per architecture risk; E2E-browser-verifiable |
| Migration | **NO** | PostgreSQL + SQLite already hold parity; no new storage paradigm needed |
| AI | **YES, bounded & grounded** (via AIContentService + RAG + deterministic memory); deterministic fallback **required**; config-flag `OPTIONAL` allowed but NOT the recommended default | Demonstrates the full closed loop convincingly while respecting the no-ML mandate |
| Frontend migration | **NO** — stay vanilla SPA; P8 adds a plain HTML/JS chat panel | Framework migration (candidate I) explicitly rejected |
| Overall scope | Bounded: 1 chat surface + 1 remediation trigger + persistence + E2E | Avoids sprawl; keeps phase reviewer-verifiable in a browser |

---

## 5. MVP Scope (The Headline Deliverables)

1. **Mastery-Aware Tutor chat surface** — a vanilla HTML/JS panel (modal/dock) reachable from `dashboard.html` (and optionally `player.html`), reusing the SPA patterns. Supports ask → grounded answer → continue.
2. **Learner-scoped grounding context** — each request is resolved to `user.id` via `get_current_user`; the tutor reads the learner's `educational_memory_service` state (weak/developing concepts) and bounded recent attempts to bias the answer towards actual gaps.
3. **Grounded answer generation** — responses are produced through **AIContentService** using **RAG** over the learner's own lesson content; include **attribution** (source lesson/section) and a **confidence** hint; **deterministic fallback** whenever RAG/AI is cold or unavailable (return a grounded, memory-driven explanation + recommendation instead of free-form text).
4. **"Remediate weak concept" quick-action** — from the dashboard's weak-concept chip (and/or `recommendations`), a button seeds the tutor conversation with a walkthrough for that concept, converting P7's passive output into an actionable next step.
5. **Persistence** — minimal **tutor conversation / session tables** (1 new migration appended to the chain), learner-scoped by `user.id`; bounded history (subset for context), no unbounded growth.
6. **Browser E2E journey** — sign in (real form) → dashboard → open tutor → ask a grounded question → verify a grounded/attributed reply and the remediation trigger. Must keep the P7 E2E pattern (pop the conftest `get_current_user` override; clear `_ems._memories`) so the real auth + DB-seeded memory path is exercised.

---

## 6. Out-of-Scope For P8 (Explicit Exclusions)

- **Teacher / classroom / parent role** (candidate F) — blocked: no role model exists (G-5).
- **Interactive 2D lesson editor** (candidate G).
- **Advanced visual learning upgrade** (candidate D).
- **Frontend framework migration** (candidate I) — rejected.
- **Free-form / ungrounded LLM chat**; **parametric ML/DL learner models**.
- **Multi-tenancy / sharing of tutor sessions** between users.
- **Re-architecting lesson content model** (branching / forking) — deferred; the tutor *compensates*, not rewrites, the linear-block model.
- **Any change to assessment's exam-grade engine** beyond grounding the tutor on attempts.

---

## 7. Backend Design (Service + API)

**New service:** `app/services/mastery_tutor_service.py` — `MasteryTutorService` responsible only for composition:
- Resolve learner context: `educational_memory_service.load_from_db(session, user_id)` + bounded recent attempts (reuse `LearnerProgressService` query patterns / `_attempt_history`) + `recommendation_engine` output.
- Extract top weak/developing concepts → grounding signal.
- Build the bounded prompt/retrieval plan → call **AIContentService** + **RAG** (authorized retrieval over the learner's own content).
- Wrap attribution + confidence; **fallback path** to deterministic memory-driven response on cold AI.
- Persist the bounded conversation (new `TutorSession`/`TutorMessage` tables).

**New router:** `app/api/v1/tutor.py` — `tutor_router`, prefix `/api/v1/tutor`, every route `Depends(get_current_user)` + `Depends(get_unit_of_work)`:
- `POST /tutor/sessions` → open/seed a session (optionally for a target concept id).
- `POST /tutor/sessions/{id}/messages` → send a learner message, get grounded answer.
- `GET /tutor/sessions` (or `/tutor/sessions/current`) → resume latest learner session.
- `POST /tutor/remediate` → create a seeded session for a given weak concept id.
All learner-scoped; never accept a user_id from the body/query.

**Schemas:** `app/schemas/tutor.py` — `TutorSessionOut`, `TutorMessageIn/Out` (with `attribution`, `confidence`, `source_kind`), `RemediateRequest`.

**Wiring:** `app/main.py` — `include_router(tutor_router, prefix="/api/v1")`.

---

## 8. Frontend Design (Vanilla, In `backend/frontend/`)

- **`dashboard.html`** — add an **"Ask your tutor"** affordance + per-weak-concept **"Remediate"** buttons wired to the new endpoints (reuse `authFetch`, `escHtml`).
- **New `tutor.html`** (OR a reusable chat modal injected into existing pages) — chat UI: message list, input box, streaming-ish rendering, source/confidence chips. Kept vanilla: inline JS, no build step, same envelope + `localStorage` auth.
- Reuse existing navigation: `index.html`/`player.html` link patterns; `player.html` already hosts the learner-journey panel pattern to copy for responsive chat.

---

## 9. Persistence & Migrations

- Add **1 linear migration**, e.g. `0029_tutor_sessions`, appending to head `0028_ws10_idempotency_key_index`:
  - `tutor_sessions` (id, user_id FK, status, target_concept_id, created/updated).
  - `tutor_messages` (id, session_id FK, role, content, attribution_json, confidence, created_at + partial index).
- **Ownership:** `user_id` on `tutor_sessions`; enforced by `get_current_user`.
- **Bounded history:** context window capped to the most recent N messages; older rows may be trimmed.
- SQLAlchemy-only, portable to both PG and SQLite (no PG-only types).

---

## 10. Query / Performance Contract (Carried From P7)

- Every tutor request costs a **bounded, set-based** set of queries (context read + retrieval + persist) — **no N+1**.
- All lists bounded by service-level caps (mirror `learner_progress_service.py` pattern).
- Bounded conversation context; no unbounded growth in a single request path.

---

## 11. Regression Contract (Baseline to Carry Forward)

| Metric | Required floor at completion & every checkpoint |
|---|---|
| Fast suite (SQLite) | **≥ 1103 passed** |
| PostgreSQL suite (`-m postgres`, testcontainer `postgres:16-alpine`) | **≥ 15 passed** |
| Browser P7 E2E | **3/3 passed** (keep green) |
| New P8 browser E2E | **author-defined** (tutor journey), 100% pass |
| mypy (`app`) | **≤ 83 errors, zero new** (`[tool.mypy] exclude=["tests/"]`) |
| `ruff check .` | **clean** |
| `git diff --check` | **clean** |
| Secret scan | **clean** (only dummy/placeholder creds) |
| Alembic | single linear head `0029_tutor_sessions`; `alembic heads` unique |

Any **regression** above P7's numbers blocks the P8 checkpoint (see §13).

---

## 12. Test Strategy

- **Unit:** `tests/unit/test_mastery_tutor_service.py` — grounding extraction, fallback path, bounded context, recommendation hand-off; assert response shape (attribution/confidence), no external AI mocked to unconditional success.
- **Integration / Security:** `tests/integration/test_mastery_tutor_security.py` — 401 without auth; own-data only; **User B never sees User A's session/messages**; empty-state; content assertions not just status.
- **Browser E2E:** `tests/e2e/test_p8_mastery_tutor_e2e.py` — must preserve the P7 root-cause fixes: pop the conftest autouse `get_current_user` override to hit real JWT auth, and clear `educational_memory_service._memories` before seeding so DB-seeded memory is read. Test remains `def` (sync), not `async def` (async test defs break `pytest-playwright`).
- Keep `_ems._memories` cache clear across tests and seed synchronously (`create_engine(sqlite:///...)` + `Session`, not `asyncio.run()`).

---

## 13. Checkpoints C0–C6

| Checkpoint | Deliverable | Acceptance gate |
|---|---|---|
| **C0** | P8 plan approved from this doc; repo at `9b32ecd` clean | Plan sign-off; clean tree |
| **C1** | Backend: tutor schemas + service (grounding, fallback) + migration `0029`; wired `app/main.py` | Unit + integration security tests green; migration appends linear chain |
| **C2** | API router `tutor.py` fully learner-scoped | Integration cross-user isolation tests pass |
| **C3** | Frontend: vanilla chat panel + dashboard "Remediate" affordance | Manual browser smoke; reuses `authFetch`/envelope |
| **C4** | Browser E2E journey green | New P8 E2E 100%; P7 E2E still 3/3 |
| **C5** | Full regression run | SQLite ≥1103; PG ≥15; mypy ≤83; ruff clean; head `0029` unique |
| **C6** | Final report + this chain updated | Report doc; `git diff --check` clean; commit |

Each checkpoint includes the root-cause E2E pattern guards (§12). No P8 implementation begins before C0 sign-off.

---

## 14. Browser-First Validation Journey

The phase is accepted **in-browser**, not just by unit tests:
1. Fresh learner signs up / in via real form.
2. Uploads a document → lesson generated via **AIContentService**.
3. Completes lesson + quiz loop so `educational_memory_service` marks a concept **weak**.
4. Opens the dashboard → sees the weak-concept chip + a **"Remediate"** affordance.
5. Clicks **"Remediate"** (or asks a free question) → tutor opens a seeded conversation.
6. Receives a **grounded, attributed, confidence-tagged** answer over their own lesson; verifies it references the actual weak concept.
7. Verifies **User B** (a separate sign-in) sees none of User A's tutor context.

---

## 15. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Hallucination / off-topic answers | Ground via RAG over learner's own content + memory; require attribution + confidence; bounded context; deterministic cold-path fallback |
| Chat UI complexity on vanilla stack | Reuse existing SPA patterns; bound the surface (one panel + one trigger) |
| AI cost runaway | Strict context window, caching, deterministic fallback, bounded conversation length |
| Cross-user leakage in chat history | Scope every session/message by `user.id`; mirror P7 isolation tests |
| Regression of P0–P7 | Locked regression contract at each checkpoint (C0–C6) |
| Cache freshness (G-4) | Accept single-learner TTL (1800s); document; revisit only if multi-replica required |

---

## 16. Migration Decision (Restated)

**NO migration.** PostgreSQL production + SQLite test. P8 adds no storage paradigm. The only P8 schema change is an **appended linear Alembic migration** (`0029_tutor_sessions`) — this is a schema *add*, not a storage migration. Deliberate reasoning documented in the Post-P7 Audit §14.

---

## 17. AI Decision (Restated)

**YES, bounded & grounded** for the tutor, governed by:
- **Must** route through **AIContentService**; **no bypass**.
- Grounded in **learner memory + learner's own RAG content**.
- **Deterministic fallback** required when AI/RAG is cold or disabled.
- No ML/DL for mastery/recommendation; those remain **deterministic**.
- Optional deployment toggle: `AI=OPTIONAL-behind-flag` acceptable, but **YES** is the recommended default (per Post-P7 Audit §15). **AI=NO** is not recommended (insufficient value).

---

## 18. Frontend Decision (Restated)

**NO migration — stay vanilla SPA in `backend/frontend/`.** P8 adds a plain HTML/JS chat panel + dashboard affordance. Candidate I (framework migration) explicitly rejected. (Post-P7 Audit §16.)

---

## 19. Security & Ownership Contract

- Every tutor route uses `Depends(get_current_user)`; `user_id` **derived from auth only**, never accepted from client payload.
- Cross-user isolation enforced and tested (User B never sees A's sessions/messages).
- Secrets stay out of the repo; secret scan remains clean.
- OAuth (Google) and existing auth unchanged.

---

## 20. Performance & Caching Contract

- Bounded contexts and result sets everywhere (mirror P7 caps).
- No N+1 in tutor context reads.
- Reuse `BoundedCache` for hot learner-context reads.
- Deterministic fallback keeps latency and cost predictable when AI is busy/cold.

---

## 21. Exclusions (Recheck Before C0 Sign-Off)

Also excluded, to keep P8 lean: teacher intelligence (F); interactive 2D editor (G); visual learning upgrade (D); frontend framework migration (I); branching lesson model rewrite; exam-grade assessment engine; multi-user sharing of tutor sessions; free-form ungrounded chat; ML learner models. Any item not listed as in-scope in §5 is out of scope unless explicitly added via an approved amendment.

---

## 22. Rollback Plan

- **Code:** P8 is additive (new service/router/migration/frontend panels). Rolling back = reverting the P8 commits; existing P0–P7 behavior unchanged (tutor is opt-in surface).
- **Schema:** `0029_tutor_sessions` is append-only additive with no changes to existing tables; downgrade via `alembic downgrade -1` removes the tutor tables without touching existing data.
- **Feature flag:** gate the tutor behind a config/env flag so it can be disabled without schema rollback if a runtime issue is found.
- **Data safety:** tutor sessions are learner-owned, isolated, and trimmable; no shared/mutable global data introduced.

---

## 23. Definition of Done

P8 is complete when:
1. Tutor backend (service + router + schemas + migration `0029`) is merged, wired under `/api/v1/tutor`, learner-scoped.
2. Vanilla chat UI + dashboard "Remediate" affordance render without build step.
3. Browser E2E journey (real-auth, DB-seeded memory) passes; P7 E2E still 3/3.
4. Full regression contract green: SQLite ≥1103; PG ≥15; mypy ≤83 new-free; ruff clean; `git diff --check` clean; head `0029_tutor_sessions` unique.
5. Isolation test proves User B never sees User A's tutor context.
6. Deterministic fallback verified (AI cold / disabled → grounded memory-driven answer).
7. This chain carries an updated `P8_IMPLEMENTATION_REPORT.md` and a `POST_P8_*` audit (following the established per-phase pattern).
8. Committed with `git status --short` clean and no secrets.