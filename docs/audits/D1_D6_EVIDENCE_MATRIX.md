# D1–D6 Remediation — Evidence Matrix

Every claim below carries a pointer to the code/test or command that produced
it. Columns: **ID / Claim / Evidence (file : line or test name) / Status**.

## D1 — Injection coverage at every AI entry point

| ID | Claim | Evidence | Status |
|---|---|---|---|
| D1.1 | There are exactly 10 LLM text-generation call sites tied to `get_ai_content_service`/`AIContentService` | `grep` of `backend/app` — sites in lesson_generation_service.py:92, topic_outline_service.py:111, mastery_tutor_service.py:547, learning_assistant_service.py:638, quiz_generation_service.py:196, component_discovery_service.py:39, learning_objective_service.py:36, relationship_engine_service.py:44, visual_classifier_service.py:169, visualization_decision_service.py:77 | VERIFIED |
| D1.2 | A single central choke point (`guard_ai_request`) scans `user_prompt`, `system_prompt`, and `messages[*].content` | `app/ai/prompt_injection.py` — `guard_ai_request` | VERIFIED |
| D1.3 | `AIContentService.generate()` and `.stream()` run the guard before cache + provider | `app/ai/service.py:96-97` (`generate`), `:182-183` (`stream`); test `TestGatewayInAIContentService::test_generate_blocks_injected_prompt_before_provider` | VERIFIED (test) |
| D1.4 | Call sites opt in via `scan_for_injection=True`; disabled flag = no scan | `app/ai/models.py` field default False; test `TestGuardAIRequest::test_does_not_scan_when_flag_disabled` | VERIFIED (test) |
| D1.5 | Race: only strong rules drive the blocking path (weak words like "no restrictions" never block) | existing `test_prompt_injection.py` 16 cases + new `test_accepts_educational_words_about_injection` | VERIFIED |
| D1.6 | The negotiation's 3 adversarial strings are all reliably blocked | `INJECTION_A/B/C` in `tests/unit/test_gateway_injection_guard.py:33-36` (all raise in `TestGuardAIRequest`); rules at `app/ai/prompt_injection.py:44-48` | VERIFIED |
| D1.7 | Lesson-about-injection is not a false positive | `test_accepts_educational_words_about_injection` | VERIFIED |
| D1.8 | Config gate: `AI_PROMPT_INJECTION_ENABLED=False` skips the scan | `test_disabled_config_skips_scan` | VERIFIED |

## D2 — High-risk assistant + quiz paths

| ID | Claim | Evidence | Status |
|---|---|---|---|
| D2.1 | Assistant refuses (no echo) an injected `user_message` before provider | `app/services/learning_assistant_service.py:628-643`; `test_generate_response_returns_refusal_for_injection` | VERIFIED |
| D2.2 | Assistant's benign question is not refused | `test_generate_response_does_not_block_benign_question` | VERIFIED |
| D2.3 | Quiz generation never sends flagged content to the model | `app/services/quiz_generation_service.py:197-204` (`scan_for_injection=True`); `test_call_ai_blocks_injected_lesson_content` | VERIFIED |

## D3 — Visual chain (5 services)

| ID | Claim | Evidence | Status |
|---|---|---|---|
| D3.1 | Orchestrator fail-fasts on injected content with `[INJECTION]` error | `app/services/visual_intelligence_service.py:62-73`; `test_orchestrator_fails_fast_on_injected_content` | VERIFIED |
| D3.2 | Orchestrator still accepts benign content | `test_orchestrator_accepts_benign_content` | VERIFIED |
| D3.3 | Every visual AIRequest carries `scan_for_injection=True` | tests `test_{component_discovery,learning_objective,relationship_engine,visual_classifier,visualization_decision}_sets_flag` on the request builder call sites | VERIFIED |

## D4 — Grounding architecture

| ID | Claim | Evidence | Status |
|---|---|---|---|
| D4.1 | Provenance metadata recorded on every generated version | existing `test_lesson_generation_service.py::test_success_persists_version_blocks_and_usage` (prompt_hash/payload_hash/safety_checks) | VERIFIED |
| D4.2 | Per-topic coverage computed for each topic block | `app/services/lesson_safety.py::_estimate_topic_coverage`, `_first_weak_topic` | VERIFIED |
| D4.3 | Dead tutor config removed | `grep` shows no references to `TUTOR_GROUNDED_SENTENCE_THRESHOLD` / `TUTOR_INJECTION_FLAG_THRESHOLD` in `backend/`; both deleted in `app/core/config.py` | VERIFIED |
| D4.4 | New enforcement metric emitted | `ai_safety_output_coverage_rejected_total` in `lesson_safety.py:validate_output` | VERIFIED (code) |

## D5 — Coverage enforcement (bars A–E)

| ID | Claim | Evidence | Status |
|---|---|---|---|
| D5.1 | A: grounded source → ACCEPT | `TestAGroundedSourceAccepts` | VERIFIED |
| D5.2 | B: unsupported O(1) claim → REJECT | `TestBUnsupportedClaimRejects` | VERIFIED |
| D5.3 | C: mixed supported+unsupported → REJECT (per-topic) | `TestCMixedClaimsPartiallyRejects` | VERIFIED |
| D5.4 | D: valid paraphrase → ACCEPT | `TestDParaphraseAccepts` | VERIFIED |
| D5.5 | E: injection inside document never becomes model instructions | `TestEInjectionInDocumentNotInPayload` (validate_input rejects the hostile source; validate_output sees only grounded payloads) | VERIFIED |
| D5.6 | Threshold is config-driven | `TestCoverageThresholdConfigurable` (0.10 passes, 0.60 rejects the same payload) | VERIFIED |
| D5.7 | Existing suite stayed green with enforcement on | unit suite: 1401 passed; integration: 204 passed | VERIFIED |
| D5.8 | Residual limit documented | lexical estimator cannot catch vocabulary-overlapping fabrication; noted in report §Remaining risks | DOCUMENTED |

## D6 — Vector-retrieval architecture

| ID | Claim | Evidence | Status |
|---|---|---|---|
| D6.1 | App-side cosine is the only verified execution path here (no PostgreSQL available) | environment constraint; baseline audit report | VERIFIED |
| D6.2 | Candidates bounded at `TUTOR_EMBEDDING_SEARCH_LIMIT=200` per content unit | `app/repositories/rag_repository.py::list_embedded_pairs_for_content_units` (`settings.TUTOR_EMBEDDING_SEARCH_LIMIT`) | VERIFIED |
| D6.3 | Ranking/tie-breakers/fallback live only in `app/ai/retrieval.py` | `_ranked_pairs`, `cosine_similarity` | VERIFIED |
| D6.4 | Migration path documented (pgvector behind a repo method + backend setting; ranking stays single source of truth) | `app/ai/retrieval.py` module docstring "Scaling boundary" | VERIFIED (doc) |
| D6.5 | pgvector / PostgreSQL behavior claimed? | **No** — explicitly NOT verified anywhere in this pass | — |

## Honesty ledger

| Thing | Claimed? |
|---|---|
| Hallucination prevention | NO — not claimed anywhere; grounding is lexical coverage |
| Complete injection prevention | NO — scanner is a deterministic lexical guard |
| pgvector / PostgreSQL | NO — only app-side cosine is verified |
| Browser E2E | NO — `tests/e2e` is JS and not runnable here |
| Live Gemini/OpenAI verification | NO — all runs use `AI_PROVIDER=local` |