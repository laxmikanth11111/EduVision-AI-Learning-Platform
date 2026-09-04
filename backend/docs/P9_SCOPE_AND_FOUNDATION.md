# P9 Scope & Foundation — Mastery Tutor Hardening & Semantic Grounding

**Authoritative implementation contract for P9.**
**Supersedes the P9 direction implied by earlier phase docs.**
**Status:** PLANNING
**Branch target:** `feature/individual-user-foundation`
**Parent of P9:** audit at HEAD `ea9e10e` (Post-P8 Product & Architecture Decision Audit)
**Type:** Feature phase — implementation occurs **only after** this doc is approved.

---

## 1. TL;DR

The Post-P8 audit confirmed P8 delivered a robust, isolated, XSS-safe mastery tutor with **correct deterministic grounding** — but exposed one **high-severity gap (F1): the tutor's retrieval is positional/bounded, not true semantic RAG** (no query-embedding, no cosine similarity, no `TUTOR_RETRIEVAL_SIMILARITY_THRESHOLD`, no ranking), so the "RAG grounded" claim overstates the implementation. P9 is a **focused hardening phase** that (a) makes tutor retrieval genuinely semantic by reusing the proven `learning_assistant_service` semantic path, (b) surfaces the already-persisted session/history in the UI (resume), (c) makes the browser E2E exercise the **real AI+RAG path** (not just the deterministic fallback), and (d) closes the small hygiene gaps (retention, setting-constant, ORM↔migration index drift). It stays a **vanilla SPA**, keeps learner intelligence **deterministic**, holds **PostgreSQL + SQLite**, appends to the **linear Alembic chain** (head `0029_tutor_sessions`), and keeps the P0–P8 regression contract green.

---

## 2. Objective & Hypothesis

**Objective:** Make the P8 tutor *trustworthy enough to be a primary study surface* — answers that are actually relevant to the question asked (semantic retrieval over the learner's own content), that the learner can continue across sessions (resume), and whose AI grounding is exercised and verified end-to-end in a browser.

**Hypothesis (testable at P9 end):** A learner who asks "why is *Gaussian Distributions* weak for me?" receives an answer whose grounded chunks were selected by **cosine similarity to their actual question** (not merely the first chunks of a content unit); they can re-open their tutor chat and see prior turns; and the browser E2E now drives the **real AIContentService + semantic-RAG path** (seeded with learner content) — with the deterministic fallback still present and correctly exercised when AI/RAG is deliberately cold. No regressions vs. P8's green gates.

---

## 3. Non-Negotiable Architecture (Carried From P0–P8)

- **Backend:** FastAPI (Python, async), SQLAlchemy.
- **Storage:** PostgreSQL **production** + SQLite **test**. SQLAlchemy-only SQL (no PG-only constructs in shared code paths). **Re-establish ORM↔migration index parity.**
- **Frontend:** **vanilla multi-page SPA** in `backend/frontend/`, via FastAPI `StaticFiles`. **No React / TS / Vite / Tailwind / build step.** Shared patterns (`authFetch`, `escHtml`, `localStorage`, `/api/v1`, `res.json().data`). Prefer extracting `authFetch`/`escHtml` into a shared asset to end cross-page drift.
- **AI:** **AIContentService is the mandatory AI path** — never bypassed. Retrieval must be **semantic** (query-embedding + cosine + `TUTOR_RETRIEVAL_SIMILARITY_THRESHOLD` + deterministic ranking), falling back to positional only when embeddings are cold. Learner intelligence stays **deterministic** — no ML/DL.
- **Caches:** bounded (`BoundedCache`), not unbounded.
- **Ownership:** every resource scoped by `user.id` from `get_current_user`, never client-supplied.
- **Migrations:** strictly **linear** Alembic chain; append to head `0029_tutor_sessions` (≤1 additive migration).

---

## 4. P9 Judgment Call (Post-Audit Decision)

| Dimension | Decision | Rationale |
|---|---|---|
| Recommended candidate | **P9 — Mastery Tutor Hardening & Semantic Grounding** | Highest value-per-risk: closes the only high-severity gap (F1) and the trust gap (F5/F2) without new surfaces or schema churn |
| Migration | **YES, ≤1 additive** (only if F6 index alignment requires it) | F6 is a low-risk parity cleanup; keep it additive and idempotent; if avoidable, defer to P10 |
| AI | **YES — make existing tutor retrieval semantic** (reuse `learning_assistant_service` `_retrieve_relevant_chunks_semantic`); deterministic fallback **retained** | Genuine grounding is the core trust fix; stays within the no-ML mandate |
| Frontend migration | **NO** — stay vanilla SPA; add a session-list/resume affordance to `tutor.html` | Framework migration (candidate I) remains rejected |
| Overall scope | Bounded: semantic retrieval + resume UI + real-AI-path E2E + retention/parity hygiene | Avoids sprawl; keeps the P8 green contract intact |

---

## 5. MVP Scope (The Headline Deliverables)

1. **Semantic tutor retrieval (F1 — primary).** Replace `mastery_tutor_service._retrieve_learner_chunks`'s positional/bounded selection with the semantic pattern already proven in `learning_assistant_service._retrieve_relevant_chunks_semantic` (L598-635): embed the user query, compute cosine similarity, filter by `TUTOR_RETRIEVAL_SIMILARITY_THRESHOLD` (0.3), rank deterministically `(similarity desc, position asc, chunk id)`, and keep the positional fallback when embeddings are cold. Reuse/consolidate the shared helper so there is **one** semantic-retrieval implementation.

2. **Real-AI-path browser E2E (F2).** Extend `tests/e2e/test_p8_mastery_tutor_e2e.py` (or add a P9 E2E) to seed a learner-owned `DocumentChunk`/`ContentUnit` **with an embedding**, so the browser run exercises the **live AIContentService + semantic-RAG path** and verifies a grounded, attributed reply whose chunk was chosen by relevance — not merely the deterministic badge.

3. **Session resume & history UI (F5).** Wire `frontend/tutor.html` to the already-present paginated `GET /api/v1/tutor/sessions` and `GET /api/v1/tutor/conversations/{id}/messages` endpoints: a session list, resume-into-an-existing-conversation, and replay of prior turns. Uses the enclosing `escHtml` for all rendered content.

4. **Retention policy (F3).** Enforce the existing `TUTOR_SESSION_IDLE_DAYS`/`TUTOR_CONVERSATION_CLEANUP_DAYS` settings — a bounded cleanup (worker or on-read boundary) so `tutor_messages`/`tutor_sessions` stop growing without bound.

5. **Hygiene (F4, F6).** Use `TUTOR_MAX_HISTORY_MESSAGES` instead of the hardcoded `20`; align the ORM `ix_tutor_conversations_lesson` (composite) with the migration `ix_tutor_conversations_lesson_id` via an idempotent additive migration (or documented removal of the dead composite) to restore SQLite↔PG parity.

6. **Shared SPA helpers (drift).** Extract `authFetch`/`escHtml` into a shared `assets/app.js` used by `tutor.html`, `dashboard.html`, and `player.html` to end the current inline duplication.

---

## 6. Explicitly Out of Scope (P9)

- **Teacher / classroom / parent role** (candidate F) — blocked: no role model.
- **Interactive 2D lesson editor** (candidate G); **advanced visual learning upgrade** (D); **branching lesson model rewrite**; **exam-grade assessment engine**.
- **Frontend framework migration** (candidate I) — rejected.
- **Multi-user sharing of tutor sessions**; **free-form / ungrounded LLM chat**; **parametric ML/DL learner models**.
- **New storage paradigm** — P9 is a hardening phase over P8's schema; changes are additive-only.

---

## 7. Test Plan & Acceptance

- **Unit:** `test_mastery_tutor_rag.py` extended to assert **semantic relevance** (retrieved chunks ranked by cosine; low-similarity chunks excluded by threshold) — not just ownership/attribution. Unit tests for the new resume endpoints and retention boundary.
- **Integration security:** keep the P8 isolation suite green; add (if applicable) a deleted-lesson message-send and restart-persistence check.
- **Browser E2E (P9):** 1/1 over the **real AI+RAG path** (seeded embedding). Keep P8 1/1 and P7 1/1 green.
- **Regression floor (must hold):** SQLite **≥ 1103** (target 1107+); PG **≥ 15**; mypy **≤ 83, zero new**; ruff clean; `git diff --check` clean; Alembic single linear head `0029_tutor_sessions` (or `0030_*` appended); no secrets.

---

## 8. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Semantic retrieval changes test/answer behavior → flaky E2E | Deterministic fallback retained when embeddings cold; assert relevance the same deterministic way; seed a fixed embedding + query so cosine is stable |
| Resume UI adds surface/scope creep | Bound to list + resume + replay (no multi-session merge/search); keep vanilla |
| Retention worker adds operational complexity | Use a bounded on-read/on-session boundary first; document worker as optional |
| Parity cleanup migration | Keep idempotent + additive; verify PG 15 + SQLite 1107 after |
| Scope creep beyond hardening | All items map 1:1 to audit findings F1–F6; anything else requires an approved amendment |

---

## 9. Success Criteria (Definition of Done)

P9 closes when, and only when, all of the following are demonstrated in the repository:
1. Tutor retrieval is **semantic** (query-embedding + cosine + threshold + ranking), with a single shared semantic-retrieval implementation, and the deterministic fallback still documented/shipped.
2. Browser E2E drives the **real AI+RAG path** with a seeded learner embedding and verifies a relevant grounded reply.
3. `tutor.html` allows **listing, resuming, and replaying** persisted sessions via the existing endpoints (XSS-safe).
4. Retention is enforced per the `TUTOR_*` settings; history uses `TUTOR_MAX_HISTORY_MESSAGES`.
5. ORM↔migration index parity restored (SQLite create_all ≡ PG alembic for the tutor tables).
6. Shared `authFetch`/`escHtml` moved to a common asset.
7. All regression gates green: SQLite ≥1103 (target 1107+), PG ≥15, mypy ≤83 zero new, ruff clean, diff clean, single linear Alembic head, secrets clean.
8. Audit produced and committed with a clean tree (report + capability matrix + this contract).
