# INDEPENDENT VERIFICATION MATRIX

Date: 2026-09-15
Auditor: OpenCode (independent forensic pass)

## Claim-by-Claim Audit

| # | Claim | Source | Evidence Path | Independent Result | Status | Confidence |
|---|-------|--------|---------------|-------------------|--------|------------|
| 1 | 1,373 unit tests pass | prior final verification | `pytest tests/unit` | **1373 collected, 1373 passed (185.95s)** | **VERIFIED** | HIGH |
| 2 | 204 integration tests pass | prior final verification | `pytest tests/integration` | **204 passed (157.07s)** | **VERIFIED** | HIGH |
| 3 | Ruff clean | prior final verification | `ruff check app tests scripts --no-fix` | **All checks passed** | **VERIFIED** | HIGH |
| 4 | MyPy 83 errors (budget 86) | prior final verification | `mypy app 2>&1 \| Select-String 'error:'` | **83 errors** (CI gate at `ci.yml:249`: `count > 86`) | **VERIFIED** | HIGH |
| 5 | Semantic cosine similarity retrieval | retrieval.py:39-78 | `test_mastery_tutor_semantic_rag.py` + 3-doc runtime audit | Real cosine similarity computed in Python; 3 queries return correct top-ranked doc. Monotonic ordering verified. | **VERIFIED** (with qualification: app-side brute force, not DB-level vector index) | HIGH |
| 6 | RAG ranking respects DB position ordering for equal similarity | retrieval.py:207 | `test_rag_semantic_retrieval.py:test_deterministic_ordering_for_equal_similarity` | Tie-break is `position ASC → chunk_id ASC`; `test_deterministic_ordering_for_equal_similarity` passes | **VERIFIED** | HIGH |
| 7 | RAG threshold filters low-similarity candidates | retrieval.py:199 (`TUTOR_RETRIEVAL_SIMILARITY_THRESHOLD=0.3`) | `test_rag_semantic_retrieval.py:test_zero_norm_vector_skipped_not_crash` | Zero-norm → `None` → skipped; below-threshold docs filtered out | **VERIFIED** | HIGH |
| 8 | Fallback to positional ordering when no embeddings available | mastery_tutor_service.py:713-744 | `test_mastery_tutor_semantic_rag.py:test_tutor_semantic_falls_back_to_positional_when_no_embeddings`; `test_rag_semantic_retrieval.py:test_no_valid_semantic_vectors_triggers_fallback` | Both tests pass; positional fallback returns position-0 first | **VERIFIED** | HIGH |
| 9 | Learner scoping in RAG retrieval | retrieval.py:231-261 (`content_unit_ids.in_`) | `test_mastery_tutor_semantic_rag.py:test_tutor_semantic_retrieval_is_learner_scoped`; `test_rag_semantic_retrieval.py:test_retrieval_scoped_to_authorized_lesson_excludes_other_user` | Both tests pass; User B never sees User A's chunks | **VERIFIED** | HIGH |
| 10 | Source grounding: prompt enforces "source only" rule | lesson_prompt_builder.py:212 | Source: `"Never include information absent from the source content."` in system prompt; `--- SOURCE CONTENT ---` / `--- END SOURCE CONTENT ---` delimiters in user prompt | Rule present. No semantic entailment check or claim-source alignment enforcement in output validation | **PARTIALLY VERIFIED** — prompt boundary present, no output enforcement | HIGH |
| 11 | Grounded validator rejects unsupported claims | lesson_safety.py:207-225 | `_estimate_source_coverage` is **recorded only** (line 224: `metrics.observe`), never enforced. Docstring at line 148: "Coverage is recorded, never enforced — a low score is a signal, not a rejection." | Output validation only rejects empty topics; lexical coverage metric is diagnostic only, never blocks | **FALSE** (for the claim that grounded validator enforces source grounding in output) | HIGH |
| 12 | Prompt-injection scanner covers all relevant AI entry points | prompt_injection.md:42-49 | Full source audit of all `generate()` call sites | **3 of 10 LLM call sites covered** (lesson_generation via lesson_safety, topic_outline via `_assert_no_injection`, mastery_tutor via deterministic refusal). **7+ uncovered**: quiz_generation `_call_ai` (line 191-209), learning_assistant `_generate_response` (line 628-660), visual_classifier (line 167-195), component_discovery, learning_objective, relationship_engine, visualization_decision. No gateway-level scan in `AIContentService.generate()` | **FALSE** | HIGH |
| 13 | `TUTOR_GROUNDED_SENTENCE_THRESHOLD` and `TUTOR_INJECTION_FLAG_THRESHOLD` are dead config | config.py:250,253 | Grep: only 2 matches, both in `config.py`. Never imported or referenced | Defined but unused; no code path references either value | **VERIFIED** (dead config exists as claimed) | HIGH |
| 14 | Auth lockout wired into production login route | auth.py:51-107,281-312 | `test_auth_hardening.py:test_login_endpoint_locks_after_repeated_failures` + source: `_is_login_locked` called at login, `_record_login_failure` on bad creds, `_clear_login_failures` on success | Test passes; source shows all three functions wired into login endpoint. `MAX_LOGIN_ATTEMPTS=5`, `LOGIN_LOCKOUT_MINUTES=15` | **VERIFIED** | HIGH |
| 15 | Refresh rotation with reuse detection | auth.py:470-503 | `test_auth_hardening.py:test_refresh_rotates_presented_token` + `test_reusing_rotated_token_is_rejected` | Both tests pass; token is revoked on rotation, replay returns 401 | **VERIFIED** | HIGH |
| 16 | `RATE_LIMIT_ROUTES` includes auth endpoints | config.py:413-425 | Source: `^/api/v1/auth/login$=10/60`, `^/api/v1/auth/register$=10/60` + quiz/tutor/assistant routes | Present in config; middleware wiring verified in prior pass (requires runtime Redis to fully exercise) | **VERIFIED** (config present; middleware wired) | HIGH |
| 17 | Canonical frontend has real API calls | `backend/frontend/` | `signin.html:116` → `/api/v1/auth/login`; `upload.html` → upload endpoint; `player.html` → lesson fetch | Real fetch calls with proper endpoint URLs | **VERIFIED** | HIGH |
| 18 | Deprecated `eduvision_frontend` is static/mock | `EduVision_AI_Frontend/eduvision_frontend/` | `processing.html` uses mock data; `player.html` has no fetch calls; README marked DEPRECATED | Static prototype, not connected to API | **VERIFIED** | HIGH |
| 19 | `conftest.py` autouse auth override hides real auth in tests | tests/conftest.py | `_override_get_current_user` is `autouse=True`; most endpoint tests bypass real auth | Tests use fake user; only `test_auth_hardening.py` exercises real auth flow | **VERIFIED** (real auth tested only in test_auth_hardening) | HIGH |
| 20 | Integration tests run on SQLite, not PostgreSQL | tests/conftest.py, ci.yml | `create_async_engine(f"sqlite+aiosqlite:///{TEST_DB_PATH}")`; ci.yml integration job uses same conftest | Integration marker docstring claims "requires a PostgreSQL database" but all tests run on SQLite | **VERIFIED** (SQLite-based, not PostgreSQL) | HIGH |
| 21 | Semantic retrieval uses app-side brute-force, not DB-level vector index | retrieval.py:164-208, rag_repository.py:245-261 | DB query is `ORDER BY position ASC` (not similarity); cosine ranking done in Python loop over ≤200 candidates | No pgvector, no ANN index, no DB-level vector operator | **VERIFIED** (app-side brute-force over ≤200 chunks) | HIGH |
| 22 | Single alembic head (0036) | ci.yml migration check | `alembic heads --verbose` → single head `0036_c4_topic_animation_assets` | Confirmed | **VERIFIED** | HIGH |
| 23 | `AI_LESSON_SAFETY_VALIDATOR` defaults to `"grounded"` | config.py:146 | `AI_LESSON_SAFETY_VALIDATOR: str = "grounded"` | Default present; `build_safety_validator("grounded")` returns `GroundedLessonSafetyValidator` | **VERIFIED** | HIGH |
| 24 | Lesson prompt builder separates SYSTEM / USER / DOCUMENT boundaries | lesson_prompt_builder.py:198-227 | System prompt (line 198-213): instructions + JSON contract + "Never include information absent from the source content."; User prompt (line 216-227): `--- SOURCE CONTENT ---` delimiters | Clean separation; source content isolated in user message with explicit delimiters | **VERIFIED** | HIGH |

## Summary by Status

| Status | Count | Items |
|--------|-------|-------|
| **VERIFIED** | 21 | #1, #2, #3, #4, #5, #6, #7, #8, #9, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22, #23, #24 |
| **PARTIALLY VERIFIED** | 1 | #10 (prompt boundary present, no output enforcement) |
| **FALSE** | 2 | #11 (grounded validator never enforces), #12 (injection coverage claimed full, actually 3/10) |
| **BLOCKED** | 0 | — |
| **UNVERIFIED** | 0 | — |
| **NOT IMPLEMENTED** | 0 | — |

## Defects Found

| ID | Severity | Description | Location |
|----|----------|-------------|----------|
| D1 | HIGH | Learning assistant (`learning_assistant_service._generate_response`) injects user message into LLM prompt with NO prompt-injection scan — unpatched injection surface | `learning_assistant_service.py:628-660` |
| D2 | HIGH | Quiz generation (`quiz_generation_service._call_ai`) injects lesson content (potentially user-modified) into LLM prompt with NO prompt-injection scan | `quiz_generation_service.py:119-126, 191-209` |
| D3 | MEDIUM | All 5 visual intelligence services call `ai_service.generate()` with content in prompt, NO injection scan: component_discovery:42, learning_objective:39, relationship_engine:48, visualization_decision:80, visual_classifier:172 | `component_discovery_service.py:42`, `learning_objective_service.py:39`, `relationship_engine_service.py:48`, `visualization_decision_service.py:80`, `visual_classifier_service.py:172` |
| D4 | MEDIUM | `TUTOR_GROUNDED_SENTENCE_THRESHOLD` and `TUTOR_INJECTION_FLAG_THRESHOLD` defined but never referenced anywhere — dead config | `config.py:250,253` |
| D5 | LOW | Grounded validator `_estimate_source_coverage` records a lexical coverage metric but never enforces it; grounding is diagnostic only, not enforced | `lesson_safety.py:207-225, 238-268` |
| D6 | LOW | Semantic ranking uses app-side brute-force over ≤200 chunks (not DB vector index); functionally correct but won't scale beyond small corpora | `retrieval.py:164-208` |
