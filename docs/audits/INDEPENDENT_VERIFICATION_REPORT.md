# INDEPENDENT VERIFICATION REPORT

Date: 2026-09-15
Auditor: OpenCode (independent forensic pass)
Independent of: prior engineering pass (untrusted evidence; all claims verified independently)

---

## FINAL OVERALL VERDICT

| Question | Verdict | Confidence |
|----------|---------|------------|
| Q1. Is the retrieval genuinely semantic cosine-similarity vector search? | **VERIFIED** (app-side cosine, not DB vector index) | HIGH |
| Q2. Does the system genuinely enforce source grounding of AI output? | **FALSE** (prompt boundary present; no output enforcement — lexical coverage only, never blocks) | HIGH |
| Q3. Does prompt-injection protection cover all relevant AI entry points? | **FALSE** (3/10 LLM call sites covered; quiz, learning assistant, and visual chain unprotected) | HIGH |
| Q4. Is the frontend connected to the backend via real API calls (not a static prototype)? | **VERIFIED** | HIGH |
| Q5. Are the test counts 1,373 unit + 204 integration reproducible? | **VERIFIED** (1373 passed / 204 passed independently) | HIGH |

**FINAL OVERALL VERDICT: PARTIALLY VERIFIED.**

The prior pass's quantitative claims (tests, ruff, mypy, alembic, auth, frontend, RAG mechanics) are all genuinely reproducible and real. The qualitative *security* claims are over-stated: source grounding is never enforced on model output, and prompt-injection protection covers only 3 of 10 AI call sites. These are **real functional gaps**, not evidence-hallucination on the prior pass's part, but they change the practical assurance level.

---

## Executive Summary

An independent forensic audit of the EduVision AI codebase was performed against the five audit questions. All quantitative claims were independently reproduced: **1,373 unit tests** (collected 10.91s, passed 185.95s), **204 integration tests** (passed 157.07s), **ruff clean**, **mypy 83 errors** (≤ 86 budget per `ci.yml`), **single alembic head** (`0036_c4_topic_animation_assets`). Auth hardening (lockout + refresh rotation) and frontend/backend integration were verified as genuinely wired.

However, two headline security claims fail independent scrutiny:

1. **Grounded validator does NOT enforce grounding.** `GroundedLessonSafetyValidator.validate_output` only rejects structurally empty payloads. The `_estimate_source_coverage` lexical metric is *recorded* (metrics + logs) but never enforced — its own docstring (lesson_safety.py:148) states "Coverage is recorded, never enforced — a low score is a signal, not a rejection." No semantic entailment, contradiction, or claim-source alignment check exists.

2. **Prompt-injection coverage is 3 of 10.** The scanner (`app/ai/prompt_injection.py`) is genuinely implemented and reliable, but only lesson generation, topic outline, and mastery tutor gate on it. The learning assistant (`learning_assistant_service._generate_response`), quiz generation (`quiz_generation_service._call_ai`), and the entire visual intelligence chain (component_discovery, learning_objective, relationship_engine, visualization_decision, visual_classifier) call `provider.generate()` with user-influenced content and **no scan**.

---

## Audit Scope

- **Repository**: EduVision AI (working dir root: `C:\Users\Admin\OneDrive\Desktop\EduVision AI — AI-Powered Interactive Learning Platform`)
- **Branch/HEAD**: `feature/individual-user-foundation` @ `d873d99` (2026-09-07)
- **Audit period**: 2026-09-15 (single session)
- **In scope**: `backend/app`, `backend/tests`, `.github/workflows/ci.yml`, `backend/frontend`, `EduVision_AI_Frontend/eduvision_frontend`, prior-pass audit docs
- **Explicitly out of scope (blocked)**: Docker/PostgreSQL runtime (tests/postgres), Playwright e2e, live AI keys, Redis production behavior (tested via in-memory fallback only)

## Previous Claims Reviewed

The prior engineering pass made claims in `docs/audits/FINAL_ENGINEERING_READINESS_REPORT.md`, `docs/evaluation/results/*.md`. All were treated as **untrusted** and re-derived from source + fresh runs.

## Methodology

1. **Fresh baseline capture**: git state, Python version, file inventory, environment (`docs/audits/INDEPENDENT_VERIFICATION_BASELINE.md`).
2. **Reproduction**: full `pytest tests/unit` and `pytest tests/integration` runs in serial (one process at a time — shared SQLite DB is not concurrency-safe, an environment limitation inherited from the prior pass).
3. **Static analysis**: `ruff check app tests scripts --no-fix`, `mypy app` with `error:` count, `alembic heads --verbose`, `ci.yml` budget cross-check.
4. **Code-path tracing**: For each claim, read the production source end-to-end (retrieval → repository → models → service → endpoint), then located the test that exercises that path, then ran that test file.
5. **Independent runtime harness**: A deterministic 3-document RAG test (binary search / CNN / BFS) was built in a temp directory (outside the repo) and run against the *production* `semantic_retrieve_chunks_with_meta` function using a real temp SQLite DB. Three queries, correct top-ranked document, monotonic similarity ordering.
6. **Entry-point enumeration**: All `provider.generate()` / `ai_service.generate()` call sites enumerated via grep and read individually to determine injection-scan coverage.
7. **No source modifications** were made during the audit. Temp test harness lived in `%TEMP%\opencode\` only.

## Environment

- Windows 11 (win32), PowerShell 5.1
- Python 3.14.6 (CI pins 3.13 — noted as drift, not a defect)
- All tests on SQLite (aiosqlite); conftest sets `AI_PROVIDER=local`, `VIDEO_RENDER_BACKEND=mock`, `VIDEO_RENDER_EXECUTOR=inline`
- `conftest.py` installs an **autouse** `_override_get_current_user` that replaces real auth for most endpoint tests; only `test_auth_hardening.py` exercises the real login/refresh flow

## Q1 — RAG: Is it genuinely semantic cosine-similarity vector search?

**Verdict: VERIFIED** (with a scaling qualifier) — Confidence HIGH

Evidence:
- `app/ai/retrieval.py:39-78` implements a **real numeric cosine similarity** (`dot / (norm_a * norm_b)`), with explicit `None` returns for zero-norm, dimension mismatch, malformed, or missing vectors.
- `semantic_retrieve_chunks_with_meta` → `_ranked_pairs` (lines 164-208): embeds the user query via the embedding `provider`, loads up to `TUTOR_EMBEDDING_SEARCH_LIMIT=200` stored chunk/embedding pairs via `DocumentChunkRepository.list_embedded_pairs_for_content_units`, computes cosine against each stored `ChunkEmbedding.vector`, filters below `TUTOR_RETRIEVAL_SIMILARITY_THRESHOLD=0.3`, and sorts deterministically: `similarity DESC → position ASC → chunk id ASC`.
- The **independent runtime harness** (3 docs: binary search / CNN / BFS; queries targeting each doc) returned the correct top-ranked document for all three queries with correct cosine values (1.0, 1.0, 0.7071) and monotonic ordering. The second harness run also confirmed zero-norm vectors are skipped (query vector with no axis matches → `None` → not crash).
- Learner scoping is enforced by SQL (`content_unit_ids.in_(...)` in `list_embedded_pairs_for_content_units`), proven by `test_retrieval_scoped_to_authorized_lesson_excludes_other_user` and `test_tutor_semantic_retrieval_is_learner_scoped`.
- Soft-deleted embeddings/chunks are excluded (active-embedding predicate + `deleted_at.is_(None)`).

**Qualifier**: this is **application-side brute-force** over ≤200 candidate vectors in Python. The DB query is ordered by position, not similarity (the vector similarity is computed in app memory, not via pgvector/ANN). This is fully correct for small corpora (single-content-unit lessons), and the claim "semantic vector retrieval" is accurate — but it is **not** "a vector database search." Verdict stands as VERIFIED for the mechanical question; scaling is a separate risk (D6).

## Q2 — Grounded Validator: Does it genuinely enforce source grounding?

**Verdict: FALSE** (for the claim "grounded validator ensures source grounding") — Confidence HIGH

Evidence:
- `GroundedLessonSafetyValidator.validate_input` (lesson_safety.py:156-205) is a **prompt-injection scan + non-empty check**, not a grounding check.
- `validate_output` (lines 207-225) rejects only: payload with no `topics`. Otherwise it records `_estimate_source_coverage` via `metrics.observe` (line 224) and increments `ai_safety_output_accepted_total`. It can never raise on low coverage.
- `_estimate_source_coverage` (lines 238-268) is a lexical keyword-overlap ratio (content words in output that also appear in source text), with its own docstring disclaimer at line 248: *"This is a coarse lexical estimate of grounding, not a semantic claim."*
- **No semantic entailment, contradiction, claim-source alignment, or fact-checking exists anywhere** in the validator path. A model could fabricate a fully-unsupported claim and the validator would accept it with high toxicity but a low coverage bucket.
- The prompt builder does set a strong boundary: system prompt includes "Never include information absent from the source content." (lesson_prompt_builder.py:212), and the source is delimited `--- SOURCE CONTENT ---` / `--- END SOURCE CONTENT ---` (lines 223-225). This is a **prompt-managed** boundary only — it relies on model compliance, not enforcement.

Distinction that matters: "the prompt instructs the model to stay grounded" is **VERIFIED**; "a validator enforces that the AI output stays grounded" is **FALSE**. The audit question asked about enforcement.

## Q3 — Prompt Injection: Does protection cover all relevant AI entry points?

**Verdict: FALSE** — Confidence HIGH

Evidence (all 10 LLM text-generation call sites enumerated and read):
- **Covered (3/10):**
  1. `lesson_generation_service.py:479` → guarded by `lesson_safety.validate_input` (`is_reliably_flagged`) at line 448.
  2. `topic_outline_service.py:278` → guarded by `_assert_no_injection` at line 276.
  3. `mastery_tutor_service.py:561` → guarded by `scan_for_prompt_injection` + deterministic refusal (lines 506-528) for learner messages.
- **Uncovered (7/10):**
  4. `learning_assistant_service.py:646` (`_generate_response`) — user message interpolated into prompt, no scan. **User-controlled input → LLM.** High severity.
  5. `quiz_generation_service.py:204` (`_call_ai`) — lesson-derived content interpolated into prompt (content can originate from user-modified topics), no scan.
  6-10. Visual intelligence chain: `component_discovery_service.py:42`, `learning_objective_service.py:39`, `relationship_engine_service.py:48`, `visualization_decision_service.py:80`, `visual_classifier_service.py:172` — all build prompts from lesson/presentation content and call `ai_service.generate()` directly with no scan.
- Additionally, `AIContentService.generate()` (the shared gateway at `app/ai/service.py:205`) does **not** run a gateway-level scan; coverage depends entirely on each caller.
- `TTS service` (`tts_service.py:194`) generates audio from already-generated text; lower risk, still no scan.

The scanner itself is sound (16 tests pass; `is_reliably_flagged` = any rule weight ≥2.0 gates blocking; weights documented in `prompt_injection.md`). The coverage claim is what fails.

## Q4 — Frontend/Backend: Is there a real integrated frontend (not a static prototype)?

**Verdict: VERIFIED** — Confidence HIGH

Evidence:
- Canonical: `backend/frontend/` — real `fetch()` API calls throughout. Confirmed examples: `signin.html:116` → `POST /api/v1/auth/login`; `upload.html` → upload endpoint; `index.html` → `/api/v1/...`; `player.html` (2999 lines) → real lesson/player data calls; `app.js` / `style.css` bundled.
- Deprecated: `EduVision_AI_Frontend/eduvision_frontend/` — 10 static files, mock processing page, static player demo, no API wiring. README carries the DEPRECATED marker. This is clearly the prototype, and the canonical directory is the real one.
- Prior-pass claim that backend serves the canonical frontend is corroborated by `app/main.py` mounting it.

## Q5 — Test Reproducibility: 1,373 unit + 204 integration?

**Verdict: VERIFIED** — Confidence HIGH

| Run | Collected | Passed | Duration |
|-----|-----------|--------|----------|
| `pytest tests/unit --collect-only -q` | 1373 | — | 10.91s |
| `pytest tests/unit --no-header -q --tb=short` | — | 1373 | 185.95s |
| `pytest tests/integration --no-header -q --tb=short` | — | 204 | 157.07s |
| `ruff check app tests scripts --no-fix` | — | All checks passed | — |
| `mypy app` (error: count) | — | 83 (budget 86) | — |
| `alembic heads --verbose` | — | single head 0036_c4_topic_animation_assets | — |

Runs were performed serially (single pytest process at a time) to avoid the known SQLite shared-DB contention between two concurrent pytest processes.

## Static Analysis

- **Ruff**: clean (`All checks passed`) against `app tests scripts`.
- **MyPy**: 83 `error:` lines. CI gate (`.github/workflows/ci.yml:241-251`) counts `error:` lines and fails if `> 86`. Current 83 < 86 → passes. The CI gate measures **no growth**, not "zero errors."
- **Migration**: single alembic head; CI migration check (`-m alembic heads`) would fail on multiple heads.

## CI

- `ci.yml` runs unit + integration on **SQLite** (not postgres), even though the integration marker docstring says "requires a PostgreSQL database." This is a metadata/comment discrepancy, not a test failure.
- Postgres-specific tests live in `tests/postgres/` and use Docker/testcontainers — not runnable in this environment (BLOCKED locally).
- mypy-gate is a no-regression-increment gate (budget-based), not a zero-error gate — documented prior-pass claim "mypy 83" exactly reproduced.

## Database

- All persistent test data runs through SQLite via `tests/conftest.py`: `create_async_engine(f"sqlite+aiosqlite:///{TEST_DB_PATH}")`, `NullPool`, `Base.metadata.create_all` (not alembic migrations).
- `ChunkEmbedding.vector` is `JSON` (SQLite) / `JSONB` (PostgreSQL), nullable, with provider/model/dimension/embedding_hash columns — correct shape for app-side cosine.
- Alembic head verified single (0036). Migrations are not applied in tests (create_all instead) — a real-environment drift risk, not observed as failure here.

## Authentication

- Lockout: production `login` route enforces `_is_login_locked` (Redis-first, in-memory fallback), `_record_login_failure` on bad creds, `_clear_login_failures` on success; 429 on lockout (`MAX_LOGIN_ATTEMPTS=5`, `LOGIN_LOCKOUT_MINUTES=15`). Verified by source + `test_auth_hardening.py` (8/8 pass).
- Refresh rotation: presented JTI revoked when a new pair is issued; reuse → 401 + `refresh_token_reuse_detected` log. Verified by tests.
- `RATE_LIMIT_ROUTES` in config covers login, register, quiz, tutor, assistant ingress.
- Caveat: `conftest.py` autouse `_override_get_current_user` bypasses real auth for nearly all endpoint tests. Only the auth-hardening tests actually hit the real auth endpoints. So the auth wiring is verified at source + targeted test, not exercised broadly across the suite.

## Security Findings

| ID | Severity | Finding |
|----|----------|---------|
| D1 | HIGH | Learning-assistant user message → LLM prompt with no injection scan (`learning_assistant_service.py:646`) |
| D2 | HIGH | Quiz-generation content → LLM prompt with no injection scan (`quiz_generation_service.py:204`) |
| D3 | MEDIUM | Visual-intelligence chain (5 services) → LLM prompt with no injection scan |
| D4 | MEDIUM | Dead config: `TUTOR_GROUNDED_SENTENCE_THRESHOLD`, `TUTOR_INJECTION_FLAG_THRESHOLD` never referenced |
| D5 | LOW | Coverage metric recorded but never enforced (grounding is purely prompt-managed) |
| D6 | LOW | RAG is app-side brute-force (≤200 vectors), not a DB vector index; won't scale beyond small corpora |

## Contradictions Found Between Prior-Pass Claims and Source

1. **Injection coverage**: `docs/evaluation/results/prompt_injection.md:41-49` entitled "Enforcement points (all gate on `is_reliably_flagged`)" and lists exactly 3. The final readiness report's broader phrasing ("all relevant AI entry points") is contradicted by the 7 other live `generate()` call sites that do not gate.
2. **Grounded validator wording**: evaluation/grounded_validator.md characterizes the validator as performing source grounding. The validator's own code records a lexical coverage metric and explicitly does not enforce it; it's a safety/injection validator + structural check, not a grounding enforcer.
3. **Integration marker metadata**: `pyproject.toml` integration marker claims "requires a PostgreSQL database"; CI runs integration on SQLite. Metadata is misleading (tests both run and pass on SQLite).

## Verified / Partially Verified / Unverified / Blocked / False

- **VERIFIED (21)**: unit counts (1373), integration counts (204), ruff, mypy 83/86, cosine math, RAG ranking, threshold filtering, embedding fallback, learner scoping, dead-config presence, auth lockout, quiet refresh rotation, rate-limit config, canonical frontend API wiring, deprecated prototype status, autouse auth override, SQLite test integration, app-side brute-force mechanics, single alembic head, grounded validator default, prompt-builder SYSTEM/USER/DOCUMENT separation.
- **PARTIALLY VERIFIED (1)**: Q1's DB-index qualification (app-side cosine vs true vector DB), and Q2's prompt-managed grounding boundary.
- **UNVERIFIED (0)**.
- **BLOCKED (0)** — with environmental limitations documented: Docker/Postgres, Playwright e2e, live AI keys, Redis production path (exercised via in-memory fallback only).
- **FALSE (2)**: Q2 (grounded validator enforces output grounding) and Q3 (prompt-injection coverage of all AI entry points).
- **NOT IMPLEMENTED (0)**.

## Remaining Risks

1. Uncovered injection entry points (D1, D2, D3) are exploitable if any user-influenced content flows into the LLM prompts of learning assistant, quiz generation, or visual intelligence.
2. Grounding is entirely prompt-managed; a single model-compliance failure yields ungrounded output with no detection gate.
3. mypy is a "no more than 86" gate, not a zero-error gate; new typing debt accumulates without a hard floor.
4. Tests bypass real auth everywhere except `test_auth_hardening.py`; the rest of the suite does not guard against auth regressions.
5. Test DB is SQLite while production is PostgreSQL; migrations not exercised by unit/integration suites (`create_all` is used).

## Overall Independent Verdict

**PARTIALLY VERIFIED.** The engineering pass delivered real, reproducible value — full suite reproduction, genuine cosine-similarity retrieval mechanics, functional auth hardening, working canonical frontend, clean lint, and a sound injection scanner. But two headline claims — "grounded validator enforces source grounding" and "prompt-injection covers all relevant AI entry points" — are **overstated**. The system is a solid *foundation* with prompt-managed safety, not a *fully enforced* safety layer. These are honest functional gaps (not fabricated evidence) and are remediable, but an independent reviewer should not accept the prior pass's readiness summary at face value.

Recommended next phase (out of scope for this read-only audit): a remediation pass that (a) adds gateway-level injection scanning inside `AIContentService.generate()`, (b) either enforces a configurable minimum coverage in the grounded validator or renames it to "safety validator" and documents it as prompt-managed only, (c) removes dead config, (d) updates integration marker metadata to match SQLite reality.

---

## Anti-Bias Check

- The auditor began from a prior-pass audit summary and deliberately re-derived every claim from source and fresh runs rather than trusting prior docs.
- Test counts were reproduced exactly, not reconstructed or "adjusted" to match.
- The RAG verdict was tested with an independent 3-document harness built from scratch in temp space, exercising the production function, not a demo wrapper.
- Defects were recorded even when the prior pass's *mechanics* were correct (e.g., injection coverage gap exists despite a well-built scanner).
- No verdict was upgraded because "the code looks fine" — each claim mapped to a reproducible run or a source-level trace.
- No source code was modified during the audit; the working tree can be diffed against the baseline to confirm.
- The audit did not award any claim a pass on the strength of its own documentation; each was independently executed or read.
- Severity assessments err toward conservative: two HIGH defects recorded precisely because the affected paths accept user-influenced input.

---

## Per-Question Format

### Q1: Does the RAG actually compute real vector similarity between query and stored chunks?

**VERIFIED (HIGH).** Cosine similarity is computed numerically between the embedded query and each stored `ChunkEmbedding.vector`; ranking is deterministic (similarity DESC → position ASC → chunk id); threshold floor 0.3 removes low-similarity candidates; zero-norm/dimension-mismatch/missing vectors are skipped safely; learner scoping and soft-delete exclusion verified. **Note**: similarity is computed app-side over ≤200 candidates — it is semantic vector search, but not a vector-DB search; scale remains a limitation.

### Q2: Does the grounded validator enforce that AI output stays within source?

**FALSE (HIGH).** Output validation checks structure only (non-empty topics). The source-coverage metric is lexical and recorded, never enforced; no entailment/contradiction/claim-source checks exist. The prompt instructs grounding ("Never include information absent from the source content") but enforcement is absent.

### Q3: Is prompt-injection protection present at all AI entry points?

**FALSE (HIGH).** 3/10 LLM call sites gate on the scanner (lesson, outline, tutor). Learning assistant, quiz generation, and all five visual-intelligence services do not scan user-influenced content before prompting. The scanner itself is correctly implemented and tested.

### Q4: Is the frontend genuinely integrated with the backend?

**VERIFIED (HIGH).** `backend/frontend/` performs real fetches against `/api/v1/...` (signin, upload, player, etc.); the old `EduVision_AI_Frontend/` prototype is static/mock and marked DEPRECATED. Backend serves the canonical frontend.

### Q5: Are the 1,373 unit + 204 integration test numbers reproducible?

**VERIFIED (HIGH).** Reproduced independently in serial: 1373 unit passed (185.95s), 204 integration passed (157.07s), ruff clean, mypy 83/86, single alembic head. Serial runs required (shared SQLite DB is not safe under parallel pytest processes).