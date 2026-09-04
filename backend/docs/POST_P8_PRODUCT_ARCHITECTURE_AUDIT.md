# Post-P8 Product & Architecture Decision Audit

**Phase:** P8 (Mastery-Aware AI Tutor)
**Type:** Audit only — NO P9 implementation
**Branch:** `feature/individual-user-foundation`
**Audited HEAD:** `ea9e10e` (`ea9e10ed3f6acd49b21fdff0301259e4efeb867a`)
**P7 baseline (before P8):** `9b32ecd`
**Date:** 2026-09-04

---

## 1. Purpose & Scope

This document is a **decision audit** produced after the completion of P8. Its purpose is to:

1. **Verify the P8 implementation against its claimed baseline.** The P8 report (`P8_IMPLEMENTATION_REPORT.md`) is treated as *claimed* evidence only — every verification gate is re-run against the actual repository (not trusted from the report).
2. Produce an **authoritative next-phase direction** — whether to proceed to P9, and if so, which candidate(s), based on the gaps actually observed.
3. Record the **regression contract** that P9 must carry forward.

This is a **read-only, audit-only** deliverable. No source, frontend, test, migration, CI, Docker, dependency, or config file is modified. The only artifacts produced are this audit, the capability matrix (`POST_P8_CAPABILITY_MATRIX.md`), and (conditionally) a P9 scope contract (`P9_SCOPE_AND_FOUNDATION.md`).

---

## 2. Repository State (Verified Directly)

| Item | Expected | Verified | Evidence |
|---|---|---|---|
| Branch | `feature/individual-user-foundation` | ✅ | `git branch --show-current` |
| HEAD | `ea9e10e` | ✅ | `git rev-parse HEAD` → `ea9e10ed3f6acd49b21fdff0301259e4efeb867a` |
| Working tree | Clean | ✅ | `git status --short` → empty |
| P8 commit order | `681879d` → … → `ea9e10e` | ✅ | `git log --oneline -15` |
| P7 docs baseline | `9b32ecd` (post-P7 audit + P8 scope) | ✅ | `git log` |
| P6 implementation baseline | `8c82a2c` | ✅ | `git log` |

```
ea9e10e docs(p8): add implementation report
653be67 test(p8): scope rag fixture cleanup so global rag-index count assertions stay valid
9b5f9f8 fix(p8): use sqlalchemy Column in 0029 migration and bump postgres expected head
8772a78 test(p8): add mastery tutor browser acceptance
e3e46f7 feat(p8): add vanilla mastery tutor ui
7ad955b feat(p8): ground tutor with ai content service and rag
1dc8728 feat(p8): add learner-scoped tutor api
681879d feat(p8): add mastery tutor domain foundation
c15ceeb docs: add post-p7 product architecture audit and p8 scope
9b32ecd docs(p7): add learner intelligence implementation report
```

**Conclusion:** Repository state fully matches the stated P8 baseline. No drift, no unreviewed changes. P8 produced exactly **7 commits** (1 domain foundation, 1 API, 1 AI+RAG grounding, 1 UI, 1 browser acceptance, 1 fix, 1 report).

---

## 3. Verification Gates (Independently Re-Run)

Every gate below was re-executed against the actual repository during this audit, not taken from the report.

| Gate | Reported | Independently re-run result | Verdict |
|---|---|---|---|
| Fast suite, SQLite (`tests/unit tests/integration -m "not postgres"`) | 1107 passed | **1107 passed, 0 failed**, 1 warning in 304s | ✅ **CONFIRMED** |
| PostgreSQL suite (`tests/postgres -m postgres`) | 15 passed | **15 passed**, 0 failed, 31s (PG 16-alpine, testcontainers, migrations to head) | ✅ **CONFIRMED** |
| P8 browser E2E (`tests/e2e/test_p8_mastery_tutor_e2e.py -m e2e`) | 1/1 passed | **1 passed** (15.2s) | ✅ **CONFIRMED** |
| P7 browser E2E (`tests/e2e/test_p7_dashboard_e2e.py -m e2e`) | 1/1 passed (3x pattern kept) | **1 passed** (13.9s) | ✅ **CONFIRMED for 1x** (see §3.1) |
| Ruff | clean | **All checks passed** | ✅ **CONFIRMED** |
| Mypy | 83 errors in 24 files, zero new | **83 errors in 24 files** (checked 285 files); zero errors in any `tutor`/`mastery` module | ✅ **CONFIRMED** |
| Alembic single linear head | `0029_tutor_sessions` | **`0029_tutor_sessions (head)`**, single; `0001→…→0028→0029` linear history | ✅ **CONFIRMED** |
| `git diff --check` | clean | **exit 0** | ✅ **CONFIRMED** |
| Secret scan (committed keys/tokens/private keys) | clean | only match is a regex pattern inside `.github/workflows/ci.yml:204` (the scanner itself); no tracked `.env`/`.pem`/`.key` | ✅ **CONFIRMED** |

### 3.1 Documentation Truth Audit — HEAD discrepancy

The P8 report's "Final result line" (line 19) states `HEAD : 653be67`, but the audited repository HEAD is **`ea9e10e`**.

- The **report document itself is commit `ea9e10e`** (`docs(p8): add implementation report`), which is the *last* commit on the branch.
- The report's "head" line (`653be67`) reflects the state at which the verification was captured — i.e. the last **test/implementation** commit before the report doc was added.
- **Verdict:** benign and self-consistent (the report was authored on top of the commit it names), but must be noted for the record. All other numeric claims in the report were independently reproduced exactly.

> **Discrepancy logging:** the report claims `653be67`; actual HEAD `ea9e10e`. No functional impact; the implementation commits named in the report (`9b5f9f8`, `653be67`) are all present and in order.

---

## 4. P8 Architecture Findings (Decision-Relevant)

### 4.1 ◆ KEY FINDING — Tutor retrieval is positional, not semantic RAG

The P8 report and scope contract describe a "**grounded answer generation … using RAG over the learner's own lesson content," "authorized retrieval over the learner's own content,"** and the scope contract explicitly required **"RAG over the learner's content store."**

The implementation does **not** perform semantic (vector-similarity) retrieval in the tutor path:

- `mastery_tutor_service.py:623-636` — `_retrieve_learner_chunks` calls `DocumentChunkRepository.list_embedded_pairs_for_content_units(...)` limited to `TUTOR_EMBEDDING_SEARCH_LIMIT` (200), then returns `c.content[:500] for c, _ in pairs` **in repository/pairs order, with no query-embedding, no cosine similarity, no similarity threshold, and no ranking.** Effective selection is effectively `pairs[:top_k]` — the *first* chunks the repository returns for the learner's content units.
- The **pre-existing** `learning_assistant_service` (which the tutor could have reused) *does* implement true semantic retrieval: `_retrieve_relevant_chunks_semantic` (L598-635) embeds the query, computes `_cosine_similarity`, filters with `settings.TUTOR_RETRIEVAL_SIMILARITY_THRESHOLD` (0.3), and sorts deterministically by `(similarity desc, position asc, chunk id)`.

**Consequence:** the tutor grounds on whatever chunks happen to come first in the learner's content units (crudely bounded, learner-scoped) rather than the chunks **semantically relevant to the specific question asked.** The gap is amplified because the tutor also passes the user query through the AI prompt, so answers are plausible — but the "retrieval" does not confer the relevance the P8 report's "RAG grounded retrieval" implies.

**Rationale for the over-claim:** the RAG tests (`tests/unit/test_mastery_tutor_rag.py`) assert **ownership/isolation** and that the *attribution string* (`"Source" in reply["content"]`) is present — they never assert semantic relevance, cosine thresholding, or ranking of the returned chunks. Warm RAG ≠ *semantic* RAG. **This is the single most important P8 gap.**

### 4.2 P8 browser E2E exercises only the deterministic fallback

`tests/e2e/test_p8_mastery_tutor_e2e.py` seeds `Concept` + `EducationalMemoryRecord` via `_seed_tutor_data` but **not** a `DocumentChunk`/`ContentUnit`. Because the tutor's RAG context is cold during E2E, the browser run exercises only the **deterministic, mastery-driven fallback** path — the real AI + RAG prompt path is never exercised end-to-end in a browser. The shell/tutor smoke is green, but it does not prove the grounded-AI path works through the browser.

### 4.3 History/cache bounds are context-only, not storage

- The **AI context window** is bounded: `_load_history(conversation_id, limit=20)` (L681) feeds at most 20 prior messages into the prompt; context text is also cut by `TUTOR_MAX_CONTEXT_CHARS` (16000).
- **However**, `tutor_messages`/`tutor_sessions` rows **accumulate without bound** in the DB. The settings `TUTOR_CONVERSATION_CLEANUP_DAYS=90` and `TUTOR_SESSION_IDLE_DAYS=30` are **defined but not enforced** — no cleanup worker, scheduled job, or delete-on-read boundary exists in this flow. For a single learner this is low-impact, but it violates the "bounded result sets" discipline P7 established and is a latent growth/reliability issue.
- Minor: the effective history limit is a **hardcoded `20`**, not `settings.TUTOR_MAX_HISTORY_MESSAGES` (`12`) — the dedicated setting is unused.

### 4.4 Persistence exists but is not surfaced in the UI

The backend exposes paginated `GET /tutor/sessions` and `GET /tutor/conversations/{id}/messages` (learner-scoped), but `frontend/tutor.html`:
- Always creates a **new** session on load (`POST /tutor/sessions`) and never calls the list/history GETs.
- There is **no session list, resume, or conversation-replay UI.** History is persisted in the DB but is effectively invisible to the learner after a reload. (Gamma of the "persistent tutor" vision is DB-correct but UI-incomplete.)

### 4.5 ORM ↔ migration index drift (SQLite test vs PostgreSQL production)

- The test DB is built with `Base.metadata.create_all` (SQLite, `tests/conftest.py:79`), so the **ORM schema** governs what SQLite sees.
- Production/Postgres is built from the **Alembic migration** (validated by the `-m postgres` suite, which runs `alembic upgrade head`).
- `app/models/tutor_conversation.py` declares `Index("ix_tutor_conversations_lesson", "lesson_id", "status")` (composite), but `0013_ai_tutor.py:149` creates `ix_tutor_conversations_lesson_id` on **`lesson_id` alone**. **Name and column-set differ.** The ORM's composite index is therefore never created on Postgres, while SQLite tests carry it — an asymmetry against the project's PostgreSQL↔SQLite parity contract. Non-fatal (queries still function; both sides have an index on `lesson_id`), but it is a real schema drift that should be aligned in a future cleanup migration.

### 4.6 Confirmed strengths (no action needed)

- **AI abstraction holds** — the tutor routes exclusively through `get_ai_content_service()` (L421-452) → `service.generate(...)`; no direct Gemini/OpenAI SDK in the tutor service (confirmed by regex scan across the service and factory). `LocalMockProvider` (`app/ai/providers/local.py`) returns a deterministic hash; no source echo — attribution is appended separately as `_Source`.
- **Ownership & cross-user isolation are robust.** All six endpoints resolve `user_id` from `get_current_user` (never from the client); `learning_assistant_service`-style isolation is replicated in `tests/integration/test_mastery_tutor_security.py`: 401, cross-user 404-equalization (B vs A sessions/screens), malformed/nonexistent IDs.
- **Deterministic learner intelligence preserved.** The tutor reuses `educational_memory_service` (weak/developing concepts feed context) and `generate_recommendations` from `recommendation_engine` (L555) for the remediation affordance — no ML/DL introduced.
- **Migration `0029_tutor_sessions` is strictly additive and correct.** It adds `tutor_sessions.target_concept_id`, `tutor_messages.source_kind`, `.attribution`, `.confidence`, plus `ix_tutor_messages_source_kind`; revision/`down_revision` correct (`0028_ws10_idempotency_key_index`); idempotency guards (`_columns`, `_index_exists`) present; linear single head confirmed.
- **Frontend XSS-safe.** `tutor.html`/`dashboard.html` escape all user-/assistant-content with `escHtml` and use `encodeURIComponent` for the concept deep-link (`?concept=…`). `authFetch` handles 401→refresh→retry with a signin redirect. Weak-concept picks on the dashboard deep-link to the tutor ("Ask tutor").
- **Bounded AI context**, paginated endpoints, committed-with-clean-tree history all hold.

---

## 5. Regression Contract for P9

P9 (if pursued) **must** preserve:

1. **Fast SQLite floor** ≥ 1103 (currently **1107**).
2. **Postgres suite** ≥ 15 (currently **15**).
3. **Browser E2E**: P8 1/1 and P7 1/1 staying green (a genuine P8 AI-path E2E is desired, see §7).
4. **Mypy** at 83 errors / 24 files with **zero new** (P8 modules contribute none).
5. **Ruff clean**; `git diff --check` clean; no secrets committed.
6. **Alembic linear single head** (currently `0029_tutor_sessions`), with `0001→…→0029` unchanged unless a cleanup migration is explicitly authorized.
7. **AI via `AIContentService` only** (never a direct SDK bypass); **deterministic** learner intelligence (no ML/DL).
8. **PostgreSQL ⟷ SQLite parity** — no PG-only SQL in shared code paths.

---

## 6. Summary of Findings

| # | Finding | Severity | Recommendation |
|---|---|---|---|
| F1 | Tutor retrieval is **positional, not semantic** (no query-embedding / cosine / threshold), despite "RAG grounded" claim | **High** (capability truth) | Either wire `_retrieve_learner_chunks` to the semantic path (embed query + cosine + `TUTOR_RETRIEVAL_SIMILARITY_THRESHOLD` + deterministic ranking), or explicitly re-scope the claim to "learner-scoped bounded retrieval." |
| F2 | P8 browser E2E only exercises the deterministic fallback (RAG cold — no chunk seeded) | Medium | Add a seeded `DocumentChunk`/`ContentUnit` to the E2E so the grounded-AI path is browser-verified. |
| F3 | `tutor_messages`/`tutor_sessions` **grow unbounded**; `TUTOR_*_CLEANUP_DAYS` not enforced | Medium | Add a retention/cleanup policy (or document it as deferred) in a later phase. |
| F4 | History hardcoded to `20`, not `TUTOR_MAX_HISTORY_MESSAGES=12` | Low | Use the setting (consistency). |
| F5 | Persistence (GET sessions/messages) exists but no UI resume/replay | Medium | Surface a session list/resume affordance (product decision). |
| F6 | ORM `ix_tutor_conversations_lesson` (composite) vs migration `ix_tutor_conversations_lesson_id` (single) drift | Low/Medium | Align in a future cleanup migration; note SQLite-vs-PG asymmetry. |
| F7 | Report HEAD line `653be67` vs actual `ea9e10e` | Low | Documentary; recorded in §3.1. |
| F8 | P7 E2E "3x pattern" not re-run at 3x in P8 (only 1x confirmed here and in report) | Low | Cosmetic; 1x confirmed. |

**Overall:** P8 delivers a genuinely useful, isolated, XSS-safe, schema-clean mastery tutor with **correct deterministic grounding** and a **bounded context window** — but the headline claim of **semantic RAG grounding** is stronger than the implementation supports (F1). The product works; the retrieval story needs honest re-scoping or a small semantic-retrieval change.

---

## 7. Next-Phase Direction (P9 Recommendation)

Recommended: **proceed to P9, but as a focused "tutor grounding & UX hardening" phase** (Candidate "P9 — Mastery Tutor Hardening"), rather than a broad new surface. Rationale:

- The platform now has a complete learner loop (create → set → lesson → quiz → progress → tutor → remediate). The highest-value next increment is to close the three gaps that most undermine the tutor's *trust* and *utility*: **F1 (semantic grounding)**, **F2 (E2E over the real AI path)**, and **F5 (session resume)**, with **F3/F6** as low-risk hygiene.
- A broad new phase (new roles, 2D editor, visual upgrade, framework migration) would risk the hard-won green regression contract for marginal near-term value.

P9 candidates are ranked and a scope contract is produced separately in `P9_SCOPE_AND_FOUNDATION.md` (filed because the requested candidates are genuinely well-formed and the audit recommends proceeding).
