# P4 / WS7 — Scope & Discovery Audit

## 0. Status and Purpose

**DISCOVERY / SCOPE AUDIT — COMPLETE (see WS7 DISCOVERY STATUS in the
handoff).**

This document is the evidence-based output of the WS7 **discovery phase only**.
No WS7 application code, migrations, tests, CI, Docker, or frontend changes
were made. It exists so the next engineering agent has a trustworthy,
implementation-ready definition of WS7 — or, failing that, an explicit,
evidence-backed statement that WS7 is **not defined** by the authoritative
documentation so that scope can be confirmed before any implementation.

## 1. Executive summary

- The authoritative P4 scope document (`P4_SCOPE_AND_FOUNDATION.md`) defines
  **exactly WS1–WS6**. WS6 is explicitly the **final P4 workstream**
  ("Verification & release gate"), and P4 is declared **complete** at WS6.
- **No authoritative definition of a "P4 WS7" (or "P4-C7") exists anywhere in
  this repository.**
- The only literal "WS7" strings in the repo belong to **Phase 1 / Phase 2
  phase-internal workstream numbering** (P1-WS7 = "Final security foundation
  report"; P2-WS7/WS12 = "Bounded worker retry + DLQ"). These are unrelated to
  a P4 WS7 and are already delivered.
- The only forward-looking roadmap is in `P0_DEEP_ARCHITECTURE_AUDIT.md`
  (§PART U, "Dependency-Aware Roadmap", Phases 1–14). These are **post-P4
  product phases**, none of which is labelled "WS7".
- Consequently, the correct, honest classification of "WS7" per the
  authoritative documentation is:

      NOT SPECIFIED BY AUTHORITATIVE DOCUMENTATION (UNKNOWN)

  This audit documents the gap and, for context, records the post-P4 roadmap
  candidates from `P0` — clearly labelled as **NOT authoritative WS7 scope** —
  so the program owner can formally define WS7 before any implementation.

## 2. Starting repository state

Verified at the start of this audit:

- `git status --short` → empty (clean working tree).
- `git branch --show-current` → `feature/individual-user-foundation`.
- HEAD → `454014a` `docs(p4): add WS6 verification and release-gate report`.

The repository is **complete through WS6** and clean. No unexpected working
tree changes were present, so nothing was reset/cleaned/stashed/overwritten.

## 3. Authoritative sources

Read and used as evidence for this audit (actual repository files):

| Document | Status |
|----------|--------|
| `backend/docs/P3_P4_HANDOFF_AUDIT.md` | EXISTS (read) |
| `backend/docs/P4_SCOPE_AND_FOUNDATION.md` | EXISTS — authoritative P4 scope (read) |
| `backend/docs/P4_IMPLEMENTATION_AUDIT.md` | **NOT FOUND** (does not exist) |
| `backend/docs/P4_IMPLEMENTATION_FOUNDATION_REPORT.md` | **NOT FOUND** (does not exist) |
| `backend/docs/P4_WS5_E2E_SMOKE_VERIFICATION.md` | EXISTS (read) |
| `backend/docs/P4_WS6_VERIFICATION_AND_RELEASE_GATE.md` | EXISTS (read) |
| `backend/docs/P0_DEEP_ARCHITECTURE_AUDIT.md` | EXISTS — post-P4 roadmap context (read) |
| `backend/docs/P1_SECURITY_FOUNDATION_REPORT.md` | EXISTS — P1 phase-internal numbering |
| `backend/docs/P2_DATA_RUNTIME_FOUNDATION_REPORT.md` | EXISTS — P2 phase-internal numbering |
| `backend/docs/P4_ARCHITECTURE_BASELINE.md` | EXISTS |

Per the discovery rules, the two documents listed in the task prompt that do
not exist were **recorded as NOT FOUND and NOT fabricated**. Their absence was
documented in `P4_WS6_VERIFICATION_AND_RELEASE_GATE.md` §14 and is unchanged.

## 4. WS7 authoritative definition

**Determination: WS7 is NOT DEFINED by the authoritative documentation.**

- `P4_SCOPE_AND_FOUNDATION.md` §6 defines workstreams WS1–WS6 only. §WS6 is the
  final workstream. §13 "Definition of complete" enumerates the six
  workstreams required for P4 completion.
- `P4_WS6_VERIFICATION_AND_RELEASE_GATE.md` §16 states verbatim: *"WS6 is the
  final P4 workstream per `P4_SCOPE_AND_FOUNDATION.md`. P4 is complete; further
  work is WS7+ and out of scope for this checkpoint."*
- Therefore **every** "WS7 required deliverable / dependency / implementation
  requirement / database / security / frontend / backend / AI / RAG / worker /
  observability / performance / testing / CI / Docker / documentation / exit
  criteria / non-goal / deferred-work / WS8-boundary" category in the task's
  §4 extraction list is:

      NOT SPECIFIED BY AUTHORITATIVE DOCUMENTATION

  (rather than being guessed or invented).

### 4.1 The only forward references (context, NOT authoritative WS7)

For program planning only, the repository's forward roadmap lives in
`P0_DEEP_ARCHITECTURE_AUDIT.md` §PART U (Phases 1–14). Relevant post-P4
candidates (none labelled "WS7", none part of P4 scope):

- **Phase 2 — Production frontend** (framework, routing, state, error/loading;
  remove orphaned mock).
- **Phase 3 — PowerPoint-class engine** (2D slide-element model, editor,
  undo/redo, layers, thematic states, import/export parity; new
  slide/element/layer/theme tables + migrations). P0 calls this "the single
  biggest gap vs. the product vision; currently linear".
- **Phase 4 — AI-native generation onto 2D model + RAG vector retrieval**.
- **Phase 7 — Animation engine hardening** (persist timelines, multi-object,
  state-driven; move in-memory runtime → Redis/DB).
- **Phase 14 — Performance/security/scale + CI gates** (tracing/alerting/HA
  runtime).

These are labelled **NOT AUTHORITATIVE WS7** in this document. Any of them may
be candidates for a formally-defined future workstream, but defining which (if
any) is "WS7" is a program-owner decision, not an assumption an agent may make.

### 4.2 Verification commands run (read-only)

- `uv run alembic heads` → single head `0028_ws10_idempotency_key_index`.
- `backend/frontend/` → vanilla HTML SPA (`index.html`, `signin.html`,
  `signup.html`, `upload.html`, `processing.html`, `player.html`).
- `backend/tests/e2e/` → `conftest.py`, `test_smoke.py`, `__init__.py`
  (WS5 pytest-playwright infra).
- Migration lineage `0001_initial.py` … `0028_ws10_idempotency_key_index.py`
  (linear, single head).

## 5. Document conflict analysis

| Topic | Document A | Document B | Resolution |
|-------|-----------|-----------|------------|
| P4 workstreams | `P4_SCOPE_AND_FOUNDATION.md` — WS1..WS6, WS6 final | `P4_WS6_...md` — WS6 final, P4 complete | **Consistent.** No conflict. Both agree P4 ends at WS6; no WS7. |
| Post-P4 roadmap | `P0_DEEP_ARCHITECTURE_AUDIT.md` Phases 1–14 | P4 scope docs (no post-P4 P4 workstream) | **Consistent.** P0 phases are product roadmap, not P4 workstreams; no WS7 overlap. |
| "WS7" string | P1/P2 phase-internal numbering (WS7 = security report / worker retry) | P4 docs (no P4 WS7) | **Consistent.** Different phase numbering; unrelated to P4 WS7. |
| `P4_IMPLEMENTATION_AUDIT.md` / `P4_IMPLEMENTATION_FOUNDATION_REPORT.md` | referenced by task prompt | absent from repo | **NOT FOUND** (recorded, not fabricated). No contradiction resolvable — files do not exist. |

**Scope conflict: NONE.** The documents do not conflict; they are consistent
that P4 terminates at WS6 and that **no P4 WS7 is defined**. The gap is one of
**absence**, not contradiction.

## 6. Inherited WS1–WS6 state

Recorded as **INHERITED** (not modified, not re-verified beyond what is needed
for this read-only audit):

| Item | State |
|------|-------|
| WS1 (Celery/module/metrics hardening) | COMPLETE (INHERITED) |
| WS2 (export/idempotency/runtime) | COMPLETE (INHERITED) |
| WS3 (vector semantic RAG) | COMPLETE (INHERITED) |
| WS4 (bounded TTL/LRU caches) | COMPLETE (INHERITED) |
| WS5 (browser E2E, vanilla SPA) | COMPLETE (INHERITED) |
| WS6 (release gate) | COMPLETE (INHERITED) |
| PostgreSQL = production DB | INHERITED |
| SQLite = fast test path | INHERITED |
| FastAPI backend | INHERITED |
| vanilla SPA frontend | INHERITED (verified: 6 HTML pages, no framework) |
| pytest-playwright browser E2E | INHERITED (verified: `tests/e2e/`) |
| semantic RAG (WS3) | INHERITED |
| bounded caches (WS4) | INHERITED |
| Alembic single head `0028` | VERIFIED this audit |

The repository is complete through WS6 and in its documented post-release
state. **Nothing in this discovery phase changed it.**

## 7. WS7 dependency graph

Because WS7 is not authoritatively defined, a definitive dependency graph
**cannot be constructed**. The honest classification for every candidate
dependency is:

      UNKNOWN (WS7 not defined)

For completeness, the *existing* P4 dependency graph (from `P4_SCOPE_...` §7)
is:

```
WS1 ──► WS2 ──► WS3          WS4 [independent]
WS5 [anytime]
WS6 [last]
```

If the program owner later defines WS7, its dependencies would be built on the
inherited foundation above; which specific WS1–WS6 items it depends on is
**UNKNOWN until WS7 is formally scoped**.

## 8. WS7 requirement matrix

| ID | WS7 Requirement | Evidence | Current State | Classification | Required in Implementation |
|----|-----------------|----------|---------------|----------------|----------------------------|
| R1 | Any WS7 functional requirement | none in repo | — | **UNKNOWN / NOT SPECIFIED** | No (cannot be required absent a definition) |

Because the authoritative documentation does not define WS7, **no WS7
requirement can be classified as REQUIRED with authoritative support**. Any
fabricated matrix entry would violate the "do not invent requirements" rule.
The matrix is therefore intentionally empty except for the explicit
NOT-SPECIFIED record, per rule §8 ("Do not classify something as REQUIRED
without authoritative support").

## 9. Repository gap audit

Per authoritative WS7 requirements — **none exist**, so there is no
implementable gap to audit for "WS7". For the *post-P4 roadmap only*
(recorded as context, NOT authoritative WS7), the repository currently
lacks, e.g.:

- A framework-based production frontend (current: vanilla SPA) — P0 Phase 2.
- A 2D slide-element/editor model (current content model is linear) — P0
  Phase 3.
- Animation-runtime persistence to Redis/DB (current: in-memory bounded
  caches) — P0 Phase 7.

Each item above is labelled **P0-roadmap context / NOT WS7** and would require
its own formal scope before implementation.

## 10. Security impact

- **No authoritative WS7 security requirements exist.**
- Consequence: WS7's security impact is **UNKNOWN / NOT SPECIFIED** until
  scoped.
- Any future WS7 that touches auth/ownership/IDOR/visibility/storage/sessions
  must (per the standing security contract) preserve the inherited P1/P3
  boundaries (uniform 404 ownership, upload/storage isolation, soft-delete,
  session isolation, RAG visibility). This is a standing constraint, not a WS7
  deliverable.
- **No security boundary was changed during this discovery phase.**

## 11. Database impact

- Current Alembic state (verified this audit): single head
  `0028_ws10_idempotency_key_index`.
- WS7 database classification: **UNKNOWN — no schema requirement specified.**
- Because WS7 is undefined, no migration is describable. Standby contract holds
  (PostgreSQL production, SQLite fast path, linear migrations, single head).
- **No migration was created during this audit.**

## 12. Frontend impact

- Verified current frontend: **vanilla multi-page SPA** under
  `backend/frontend/` (`index.html`, `signin.html`, `signup.html`,
  `upload.html`, `processing.html`, `player.html`), no framework, no build
  step. Browser E2E infra = pytest-playwright + system Chrome (`tests/e2e/`).
- WS7 frontend requirement: **NOT SPECIFIED**. If a future WS7 addresses the
  P0 Phase-2/Phase-3 roadmap it would change the frontend, but that is NOT an
  authoritative WS7 scope.
- **No frontend code changed during this audit.**

## 13. AI / RAG impact

- WS3 semantic vector retrieval is inherited and must be preserved by any
  future AI/RAG work (standing contract).
- WS7 AI/RAG requirement: **NOT SPECIFIED**.
- **No AI/RAG code changed during this audit.**

## 14. Worker / async impact

- Inherited: Celery `app.workers.celery_app`, DLQ, ack-late, bounded retries
  (P2/P3); WS4 bounded caches.
- WS7 worker/async requirement: **NOT SPECIFIED**.
- **No worker/async code changed during this audit.**

## 15. Performance / resource impact

- WS7 performance/resource requirement: **NOT SPECIFIED**.
- Standing constraints (WS4 bounded caches, no unbounded state, no N+1) apply
  to any future work but are inherited, not WS7 deliverables.
- **No performance/resource code changed during this audit.**

## 16. Test strategy

No WS7 tests can be specified because WS7 behavior is undefined. A test matrix
for WS7 is therefore **NOT SPECIFIABLE**. Existing inherited suites
(fast/PG/e2e) remain the regression baseline. **No tests added or modified in
this audit.**

## 17. CI / Docker impact

- `.github/workflows/ci.yml` exists and covers lint/unit/integration/
  migration-head/live-PG/postgres/secret-scan/mypy/docker-build.
- WS7 CI/Docker requirement: **NOT SPECIFIED**.
- **No CI or Docker configuration changed during this audit.**
- (Note: Docker build and prod image import were independently verified during
  WS6; that state is INHERITED and unchanged.)

## 18. Proposed checkpoints

Because WS7 is undefined, an implementation checkpoint plan **cannot be
responsibly proposed yet**. The provisional skeleton (only to be used after a
formal WS7 scope is agreed) would follow the established pattern, but is
explicitly **PENDING WS7 DEFINITION**:

```
WS7-C0  baseline + formal scope confirmation
WS7-C1  first required implementation
WS7-C2  second required implementation
WS7-C3  integration verification
WS7-C4  final hardening + documentation
```

A concrete plan (objective/files/tests/gate/rollback/exit) is **NOT provided**
until WS7 scope exists — providing one would require guessing.

## 19. WS7 implementation boundary

- **WS7 MUST implement:** nothing — no authoritative scope exists. Any
  implementation must wait for the program owner to formally define WS7 from
  the P0 roadmap and/or product direction.
- **WS7 MAY implement:** to be determined ONLY once formally scoped (candidate
  context from P0: frontend production build, 2D editor engine, animation
  persistence, CI/scale hardening — all NOT authoritative).
- **WS7 MUST NOT implement:** nothing can be hard-bounded because WS7 is
  undefined; however, per the governing rules it MUST NOT (a) reopen WS1–WS6,
  (b) violate the PostgreSQL/fast-path/vanilla-SPA/ownership contracts, or
  (c) introduce speculative features outside a formally agreed scope.
- **What belongs to WS8:** **UNKNOWN** — cannot be bounded until WS7 is
  formally defined. (If WS7 = P0 Phase 2, then WS8 might be P0 Phase 3, etc.,
  but this is speculation and is recorded as UNKNOWN, not asserted.)

## 20. WS7 release gate design

Planned gate ONLY (to be applied to whatever WS7 eventually defines) — mirror
the WS6 gate:

- Fast suite (`pytest tests -m "not postgres"`)
- PostgreSQL suite (`pytest tests/postgres -m postgres`, real PG)
- Browser E2E (`pytest tests/e2e/test_smoke.py -m e2e --browser chromium`)
- Ruff (`ruff check app tests scripts --no-fix`)
- mypy Δ=0 (`mypy app`)
- Alembic single head (`alembic heads`)
- Secret scan
- `git diff --check` + clean tree
- Docker verification if WS7 requires it
- CI verification if WS7 requires it

This is a **plan for an undefined scope**; it is not claimed as executed
verification. This audit itself executed only the read-only `alembic heads`
check (single head `0028`).

## 21. Known unknowns

| # | Unknown | Why unresolved |
|---|---------|----------------|
| U1 | What is WS7? | No authoritative definition exists in the repo. |
| U2 | WS7 objective/deliverables | Undefined. |
| U3 | WS7 dependencies | Undefined. |
| U4 | WS7 DB/frontend/AI/worker/CI/Docker/testing requirements | Undefined. |
| U5 | WS7 vs WS8 boundary | Undefined. |
| U6 | Whether WS7 = a P0 roadmap phase (2/3/7/14, etc.) | Program-owner decision; NOT authoritative. |

## 22. Deferred items

- Formal WS7 scoping — deferred pending program-owner definition.
- Any P0 roadmap phase work (frontend framework, 2D editor, animation
  persistence, scale/CI) — deferred / NOT part of P4.
- `P4_IMPLEMENTATION_AUDIT.md` and `P4_IMPLEMENTATION_FOUNDATION_REPORT.md`
  (referenced in the task prompt but absent) — recorded NOT FOUND; their
  creation, if desired, is a documentation decision for the program owner.

## 23. Explicit non-goals (this WS7 discovery phase)

- NO WS7 application code.
- NO migrations / schema changes (Alembic head unchanged at `0028`).
- NO test changes.
- NO CI changes.
- NO Docker changes.
- NO frontend changes.
- NO reopening of WS1–WS6.
- NO implementation of any P0 roadmap phase without a formal scope.
- NO fabrication of a WS7 definition.

## 24. Recommendation for WS7 implementation

**Do not implement WS7 from this repository alone.** The repository contains
no authoritative WS7 definition. Recommended sequence before any WS7
implementation:

1. Program owner formally defines **WS7 name, objective, deliverables, and
   scope** (selecting from documented context — e.g. the `P0` roadmap — or a
   new product decision).
2. Optionally confirm which (if any) P0 roadmap phase(s) WS7 corresponds to.
3. Produce a scope-update document (e.g. a new `P4_SCOPE_AND_FOUNDATION.md`
   supplement or a `P4_WS7_SCOPE...` doc) that records the formal WS7
   definition, requirements, dependency graph, and exit criteria.
4. Only then run the WS7 implementation against that formal scope with the
   standing release gate.

Until then the honest status is **BLOCKED pending clarification / scope
definition** — not because of a conflict, but because **WS7 has no
authoritative definition** in this repository.

---

*End of WS7 scope & discovery audit. No WS7 implementation performed. WS8 not
started. Working tree and P4-state preserved.*
