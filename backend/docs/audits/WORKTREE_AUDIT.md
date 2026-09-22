# EduVision AI — Working Tree Audit & Safe Cleanup Report

- **Date:** 2026-09-22
- **Auditor:** opencode (read-only audit session)
- **Branch:** `feature/individual-user-foundation`
- **HEAD:** `d873d99855de1116f8aa70ecdf3e39dcad7ef49a`
  ("feat(eduvision): close C3 visual intelligence pipeline", 2026-09-07)
- **Baseline:** 40 modified + 87 untracked + 0 deleted + 0 renamed = **127 changed files**
- **Staged:** 0 (nothing in the index)
- **Scope mode:** audit / classificatory only. **No files were committed, staged, pushed, or deleted.**

---

## A. Inventory & Classification Summary

| Class | Count | Meaning |
|---|---|---|
| KEEP (active feature work — commit as group) | 126 | Legitimate in-progress engineering |
| KEEP (docs/evidence/tests) | — | Included in the 126 above |
| REVIEW | 0 | Nothing requires spot review |
| GENERATED / transient | 0 | No build or cache artifacts in the tree |
| OBSOLETE / removable | 0 | Nothing proven safe to delete |
| DANGEROUS / secret | 0 | No live credentials in changed files |
| CANDIDATE FOR REMOVAL — NOT REMOVED | 1 dir | `EduVision_AI_Frontend/` (see E) |

**Overall verdict:** the working tree is a coherent, in-progress feature branch. All
changes belong to three interdependent work streams plus test/docs updates, and they
**must be committed together** (several tracked files import/register untracked modules).
Nothing provisional was found that would justify `git clean` / `git reset`. The work is
additionally verified: 1,777 unit+integration tests pass and the full changed `.py` set
compiles cleanly.

---

## B. Per-Modified-File Classification (40 files)

Legend: **S** = semantic-grounding / prompt-injection remediation, **C2** = C2 topic
intelligence, **C4** = C4 animation feature (depends on untracked C4 modules),
**P** = frontend/parser/product, **T** = tests, **A** = auth/middleware hardening.

| # | File | Class | Notes |
|---|---|---|---|
| 1 | `EduVision_AI_Frontend/eduvision_frontend/README.md` | P | Adds DEPRECATED banner (prototype) — already committed via prior session; working copy clean |
| 2 | `backend/.env.example` | S | Documents `AI_LESSON_SAFETY_VALIDATOR=grounded`, `AI_PROMPT_INJECTION_ENABLED/THRESHOLD` |
| 3 | `backend/app/ai/embeddings/config.py` | S | Embedding model no longer silently inherits `AI_MODEL`; uses `EMBEDDING_MODEL` or provider default |
| 4 | `backend/app/ai/embeddings/providers/gemini.py` | S | Provider-side embedding wiring |
| 5 | `backend/app/ai/models.py` | S | Prompt-injection scan model plumbing |
| 6 | `backend/app/ai/retrieval.py` | S | D6 scaling boundary + pgvector future note documented |
| 7 | `backend/app/ai/service.py` | S | Prompt-injection scan executed at AI call gateway |
| 8 | `backend/app/api/v1/auth.py` | A | Auth hardening (OAuth/redirect handling); prior-review confirmed benign |
| 9 | `backend/app/core/config.py` | A/S | Added prompt-injection + grounded-validator settings |
| 10 | `backend/app/main.py` | C4 | Registers `c4_animation_router` → **depends on untracked** `app/api/v1/c4_animation_router.py` |
| 11 | `backend/app/middleware/exception_handler.py` | A | Passes headers through (e.g. `WWW-Authenticate`) |
| 12 | `backend/app/models/__init__.py` | C4 | Registers `TopicAnimationAsset` → **depends on untracked** model |
| 13 | `backend/app/parsers/document_parser.py` | P | PPTX bullet-level + table extraction improvements |
| 14 | `backend/app/schemas/topic_outline.py` | C2 | Adds `SourceReference`, `Concept`, `EducationalExample`, `Misconception`, `Prerequisite` |
| 15 | `backend/app/services/component_discovery_service.py` | C2 | Component discovery tuned to new outline schema |
| 16 | `backend/app/services/learning_assistant_service.py` | S | LLM call site wired to grounded validator |
| 17 | `backend/app/services/learning_objective_service.py` | S | LLM call site wired to grounded validator |
| 18 | `backend/app/services/lesson_generation_service.py` | S | LLM call site wired to grounded validator |
| 19 | `backend/app/services/lesson_player_service.py` | S | LLM call site wired to grounded validator |
| 20 | `backend/app/services/lesson_safety.py` | S | **+330 lines — grounded validator** (prompt-injection scan, empty-payload rejection, source-coverage telemetry) |
| 21 | `backend/app/services/mastery_tutor_service.py` | S | LLM call site wired to grounded validator |
| 22 | `backend/app/services/quiz_generation_service.py` | S | LLM call site wired to grounded validator |
| 23 | `backend/app/services/relationship_engine_service.py` | S | LLM call site wired to grounded validator |
| 24 | `backend/app/services/topic_outline_service.py` | C2 | **+739 lines — C2 topic intelligence** (deterministic fallback, sections/topics/subtopics/concepts/objectives) |
| 25 | `backend/app/services/visual_classifier_service.py` | C2 | Classifier adapts to new outline |
| 26 | `backend/app/services/visual_intelligence_service.py` | C2 | Grounding adapts to new outline |
| 27 | `backend/app/services/visualization_decision_service.py` | C2 | Decision service adapts to new outline |
| 28 | `backend/app/workers/c3_visual_tasks.py` | C4 | C4 generation auto-dispatch after C3 render |
| 29 | `backend/app/workers/celery_app.py` | C4 | Includes `c4_animation_tasks` → **depends on untracked** module |
| 30 | `backend/frontend/player.html` | C4 | **+226 lines — C4 animation mode UI** (c4-anim-stage, sandboxed iframe, HUD) |
| 31 | `backend/tests/postgres/test_migrations.py` | T | `EXPECTED_HEAD` → `0036_c4_topic_animation_assets` |
| 32 | `backend/tests/postgres/test_p12_adaptive_persistence.py` | T | Head update |
| 33 | `backend/tests/postgres/test_p13_analytics_pg.py` | T | Head update |
| 34 | `backend/tests/postgres/test_p14_retention_pg.py` | T | Head update |
| 35 | `backend/tests/postgres/test_p15_resume_pg.py` | T | Head update |
| 36 | `backend/tests/postgres/test_p16_video_projects_pg.py` | T | Head update |
| 37 | `backend/tests/unit/test_document_parser.py` | T | Parser additions |
| 38 | `backend/tests/unit/test_embedding_config.py` | T | Embedding config change |
| 39 | `backend/tests/unit/test_lesson_generation_service.py` | T | Grounded validator coverage |
| 40 | `backend/tests/unit/test_lesson_prompt_builder.py` | T | Grounded validator coverage |

No modified file contains credentials, hardcoded secrets, or destructive changes.

---

## C. Untracked-File Classification (87 files)

### C1. New application code — C4 animation engine (13 files) — KEEP, feature-critical
| File | Role |
|---|---|
| `backend/app/api/v1/c4_animation_router.py` | `/c4/animations` CRUD + generate; ownership asserts; legacy `/animations` untouched |
| `backend/app/models/topic_animation_asset.py` | `topic_animation_assets` table, `c4a_` public ids, JSONB spec, fingerprint, version, provenance |
| `backend/app/repositories/topic_animation_asset_repository.py` | Owner-scoped `SELECT … FOR UPDATE lock_generation`, `next_version` |
| `backend/app/schemas/c4_animation_intelligence.py` | Bounded deterministic animation spec language (511 lines) |
| `backend/app/services/c4_animation_need_analyzer.py` | Lesson → animation need analysis |
| `backend/app/services/c4_animation_planning_pipeline.py` | Spec planning pipeline |
| `backend/app/services/c4_animation_renderer.py` | Deterministic self-contained HTML/SVG package renderer (no randomness, no external deps, HTML-escaped) |
| `backend/app/services/c4_animation_spec_generator.py` | Spec generation |
| `backend/app/workers/c4_animation_tasks.py` | `eduvision.c4.generate_animations`, `TaskWithDLQ`, acks_late, engine.dispose in finally |
| `backend/app/database/migrations/versions/0036_c4_topic_animation_assets.py` | Migration revises `0035_c3_topic_visual_assets` |

### C2. New application code — semantic grounding + prompt-injection (2 files) — KEEP, security-critical
| File | Role |
|---|---|
| `backend/app/ai/prompt_injection.py` | Deterministic lexical prompt-injection detector, scored vs `AI_PROMPT_INJECTION_THRESHOLD`, raises `AIInputSecurityError` → 422 |
| `backend/app/services/claim_grounding.py` | Layered grounding: claim segmentation/classification, evidence retrieval, `LLMGroundingVerifier` + `DeterministicGroundingVerifier`, fail-safe policy |

### C3. New tests (24 files) — KEEP
- C4: `test_c4_animation_api`, `test_c4_animation_contract`, `test_c4_animation_intelligence`,
  `test_c4_animation_need_analyzer`, `test_c4_animation_planning_pipeline`, `test_c4_animation_player`,
  `test_c4_animation_renderer`, `test_c4_animation_security`, `test_c4_animation_spec_generator`,
  `test_c4_animation_tasks` (in `backend/tests/unit/`)
- Grounding / security: `test_claim_grounding`, `test_gateway_injection_guard`, `test_grounding_benchmark`,
  `test_grounding_enforcement`, `test_llm_grounding_verifier`, `test_prompt_injection`,
  `test_retrieval_provenance`, `test_semantic_grounding_adversarial`, `test_auth_hardening` (unit);
  `test_c1_source_integration`, `test_lesson_grounding_persistence` (integration);
  `backend/tests/fixtures/grounding/__init__.py`, `backend/tests/fixtures/grounding/benchmark_cases.py`
- C2: `test_c2_topic_intelligence.py`

### C4. Dev/verification scripts (5 files) — KEEP
`backend/scripts/generate_sample_educational_pptx.py`, `verify_c1_browser.py`, `verify_c2_browser.py`,
`verify_c4_browser.py`, `verify_c4_quality.py` — local browser/quality verification harnesses.
Only secret-pattern matches are the dummy test password `StudentPassword123!` (benign, fixtures only).

### C5. Documentation / evidence / audits (41 files) — KEEP
- Root `README.md` (repo layout, canonical frontend note, quick start).
- `backend/docs/EDUVISION_2_0_*.md` (7), `backend/docs/C4_EXECUTION_EVIDENCE_2026_09_08.md`,
  screenshots `backend/docs/screenshots/{c1_source_mode_verified,c2_topic_hierarchy_verified}.png`
  (valid PNG headers, 79.8 KB and 133.0 KB).
- `backend/docs/audits/*` (15 files): production/security/semantic-grounding audit trail.
- `docs/architecture/ARCHITECTURE.md`, `docs/audits/*` (11 files), `docs/evaluation/README.md` + `results/*` (7 files).

### C6. Working-tree nuance — `docs/evaluation/data/`
Present on disk as an **empty directory** (not tracked; git ignores empty dirs). No action needed.

---

## D. Data & Credentials Risk Check

- **Secret scan over all 127 changed files** (regex: AWS keys, private-key headers, `sk-`, `AIza`,
  `ghp_`, slack/webhook tokens, `secret_key=/client_secret=` assignments, `password=`):
  **5 matches, all identical** dummy test password `StudentPassword123!` in
  `backend/scripts/verify_c{1,2,3,4}_browser.py` and `verify_c3_autotrigger.py` — **benign fixtures**.
  **No live credentials found in any changed file.**
- `backend/.env` (real credentials) is **gitignored and untracked** — untouched; values never logged as-is; report redacts.
- No binaries/private keys/keystores added. The two screenshots are confirmed PNGs.

---

## E. Safety / Cleanup Assessment

- **Nothing is proven safe to delete.** Per task rules, no file was removed or staged.
- **`EduVision_AI_Frontend/` — CANDIDATE FOR REMOVAL, NOT REMOVED.**
  - Canonical frontend is `backend/frontend/` (served by `app.main._resolve_frontend_dir()` —
    checks `backend/frontend` first — and mounted as `/frontend` via `StaticFiles(html=True)`).
    It contains `dashboard.html`, `tutor.html`, `videos.html` (absent from prototype) and performs
    real `/api/v1/...` fetches.
  - `EduVision_AI_Frontend/eduvision_frontend/` is a static/mock prototype (its own `player.html`
    has no API calls), not mounted, not referenced by any code — only by audit docs.
    Its README now carries the DEPRECATED marker. **Kept** because it is git-tracked, sensitive to
    prior sessions, and removal requires explicit approval.
- **Danger commands NOT run** (and should not be run without explicit human approval):
  `git clean -fd`, `git reset --hard`, `git checkout -- .`, and `rm -rf EduVision_AI_Frontend`.

---

## F. Dependencies / Import Touching

- **Commit-coupling confirmed:** tracked files import or register untracked modules, so any
  commit that omits the C4 files will break the build:
  - `backend/app/main.py` → `app.api.v1.c4_animation_router`
  - `backend/app/models/__init__.py` → `TopicAnimationAsset`
  - `backend/app/workers/celery_app.py` → `c4_animation_tasks`
  - `backend/app/workers/c3_visual_tasks.py` → C4 auto-dispatch
  - `backend/tests/postgres/*` → expects migration `0036_c4_topic_animation_assets`
- Cross-checks passed: 1,777 tests exercise the coupled modules end-to-end.
- Runtime dependencies (PostgreSQL, Redis, MinIO, Celery) unchanged; no new third-party deps in
  changed files (C4 package renderer is deliberately dependency-free).

---

## G. Structural / Git Health

- No renames/deletes detected; no staged changes; no merge in progress; single upstream,
  single author history (91 commits) — clean shape.
- OneDrive-backed worktree causes slow full `git status` scans; use
  `git status --porcelain=v1 --untracked-files=no` + `git ls-files --others --exclude-standard`.
- Working-copy deps created during this audit live **outside the repo**
  (`C:\Users\Admin\.venvs\eduvision-ai-backend`), so no venv cleanup inside the tree is needed.

---

## H. Verification (exact commands + results)

| Check | Command | Result | Status |
|---|---|---|---|
| Syntax (all 78 changed `.py`) | `python -m py_compile <file>` (Python 3.11) | 0 errors | **VERIFIED** |
| Lint (full app) | `uv tool run --from ruff ruff check backend/app` | All checks passed (exit 0) | **VERIFIED** |
| Unit + integration (full suite) | `uv run --project . pytest tests/unit tests/integration -q` | **1777 passed** in 152.61 s | **VERIFIED** |
| Focused changed-area tests | `pytest` on prompt-injection/claim-grounding/C2/embedding/prompt-builder | 90 passed in 10.23 s | **VERIFIED** |
| Secret scan | regex scan over all 127 changed files | only 5 benign dummy passwords | **VERIFIED** |
| Migration head | `test_migrations.py` `EXPECTED_HEAD` | `0036_c4_topic_animation_assets` | **VERIFIED** (static) |

**Not verified (recorded as BLOCKED, not converted to PASS):**
- `pytest -m postgres` — requires a live PostgreSQL instance; **BLOCKED (no PG service available/started)**.
- `pytest -m e2e` / browser verification scripts — require running server + S3/MinIO + Redis; **BLOCKED**.
- `mypy` — not run in this session (would need full type-check pass + config review to interpret);
  CI workflow `backend/.github/workflows/ci.yml` already runs it; recommended as follow-up before commit.

**No test was marked PASS without being executed.**

---

## I. Recommended Path Forward

### I.1 Suggested commit groups (do NOT split the C4 group)
1. **C4 animation feature (atomic):** all `backend/app/**/c4_*` + `0036` migration + `main.py`,
   `models/__init__.py`, `celery_app.py`, `c3_visual_tasks.py`, `backend/frontend/player.html`,
   all 10 `test_c4_animation_*`, `test_c2_topic_intelligence` (C4-adjacent), C4 docs + `verify_c4_*` scripts,
   `test_migrations.py` + 5 postgres head files (last in group).
2. **Semantic grounding + prompt-injection remediation:** `prompt_injection.py`, `claim_grounding.py`,
   `lesson_safety.py`, `ai/{service,models,retrieval}.py`, `ai/embeddings/*`, all grounded call sites,
   `exception_handler.py`, `config.py`, `.env.example`, all grounding/prompt-injection/security tests +
   fixtures, `SEMANTIC_GROUNDING_*`/`SECURITY_*`/`PRODUCTION_*`/`INDEPENDENT_*`/`REMAINING_GAPS` docs,
   `docs/evaluation/results/*`.
3. **C2 topic intelligence:** `topic_outline_service.py`, `topic_outline.py`,
   `visual_*_service.py`, `component_discovery_service.py`, `test_c2_topic_intelligence.py`,
   C2 docs + `verify_c1/2` scripts + screenshots.
4. **Docs/evidence housekeeping:** root `README.md`, `backend/docs/EDUVISION_2_0_*.md`,
   `docs/architecture`, `docs/audits`, `docs/evaluation/README.md`.

### I.2 Cleanup
- No deletions proposed. Leave `EduVision_AI_Frontend/` in place unless the team explicitly
  approves removal (then remove in its own commit, verifying no references remain).
- Do not add `backend/.env` to any commit; keep it gitignored.

### I.3 Hard constraints (re-stated)
- Never run `git clean -fd`, `git reset --hard`, or `git checkout -- .` on this tree.
- Do not commit the two dummy-password verification scripts unknowingly being mistaken for secrets;
  they are fixtures.
- If committing the C4 group, stage the untracked C4 modules and the four tracked wiring files in
  the **same** commit — they are inseparable.

---

*Audit closes the working-tree baseline. Prior forensic security audit is a separate document
(`SECURITY_FORENSIC_AUDIT.md`). This session performed no commit, push, or delete.*