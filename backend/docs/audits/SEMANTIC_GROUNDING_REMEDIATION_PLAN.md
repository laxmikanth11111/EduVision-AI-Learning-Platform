# Semantic Grounding Remediation Plan (Phase 1)

Status: **PROPOSED** — investigation complete; produced before any production-code change.

## 1. Current architecture (traced)

Lesson generation flow (`app/services/lesson_generation_service.py`):

```
create_lesson()            → GeneratedLesson(status=QUEUED) persisted
run_generation()           → atomic claim (PROCESSING)
  _attempt_generation():
    build_source_context()  → SourceContext (units/slides, capped 50 units / 40000 chars)
    safety.validate_input() → empty-source + prompt-injection scan (reject)      [app/services/lesson_safety.py:158]
    ai.generate(request)    → AIContentService → provider (retry/timeout/cache/usage)
      |  AIError → heuristic payload (verbatim source sentences)  [NO validate_output]
    model_validate_json()   → LessonPayload (else _record_failed_version(FAILED))
    safety.validate_output()→ per-topic lexical coverage footer                    [lesson_safety.py:209]
    version_repo.create(SUCCEEDED)  + GeneratedBlocks persisted → lesson READY
  LessonSafetyError → _record_failed_version(lesson, FAILED) → lesson FAILED
```

Persistence semantics (`generated_lesson_version.py`, `shared/constants`):
- Version statuses: `SUCCEEDED` / `FAILED` only. Lesson statuses include `QUEUED/PROCESSING/READY/FAILED/...`.
- A `SUCCEEDED` version (blocks persisted) is created **only after** `validate_output` returns. A rejection raises `LessonSafetyError` → a `FAILED` version is recorded; lesson becomes FAILED; no blocks persisted. Structurally, rejected output cannot become a successful version — this will be locked with regression tests (§20).

Validator (`app/services/lesson_safety.py:GroundedLessonSafetyValidator`):
- `validate_input`: empty-source check + deterministic prompt-injection scan (`app/ai/prompt_injection.py`, `AI_PROMPT_INJECTION_THRESHOLD=3.0`).
- `validate_output`: rejects payloads with no topics; computes per-topic **lexical** source coverage (`_estimate_topic_coverage`, content-word overlap, floor `AI_LESSON_SOURCE_COVERAGE_THRESHOLD=0.10`); raises when a topic is below the floor. Records `ai_safety_*` metrics and coverage.

Evidence-retrieval infra (`app/ai/retrieval.py`):
- DB-backed app-side cosine over persisted `ChunkEmbedding` rows (`semantic_retrieve_chunks_with_meta`, floor `TUTOR_RETRIEVAL_SIMILARITY_THRESHOLD`, cap `TUTOR_EMBEDDING_SEARCH_LIMIT`), with numeric-safe `cosine_similarity()` (returns `None` on malformed/zero-norm/mismatched vectors) and deterministic tie-breakers. Used by tutor/assistant services.
- Embedding provider abstraction (`app/ai/embeddings/base.py` + factory): `local` deterministic provider (sha256-derived 384-dim vectors, no API key), plus gemini/openai. Available in the test environment.
- `SourceContext` (in-memory, `app/services/lesson_prompt_builder.py`) is the actual input to validation — **not** DB chunk rows. Therefore lesson grounding evidence retrieval must operate in memory over `SourceContext.units`, not via `DocumentChunkRepository`.

AI provider abstraction (`app/ai/service.py`): `AIContentService.generate(AIRequest) -> AIResponse` applies retries, overall timeout, rate limit, cache, injection gate (`guard_ai_request`), usage accounting (`AIUsageRepository`) and structured telemetry. `AIResponseFormat.JSON` + payload is model-returned `text`. Local provider returns a canned JSON doc (`{ok, provider, model, digest, prompt_length}`) — it never produces lesson payloads or verdicts.

## 2. Exact weakness (reproduced)

The lexical per-topic coverage check cannot distinguish a claim that restates the source from a claim that shares the source vocabulary but asserts something the source does not state or contradicts.

Reproduction (ad-hoc script, real run, `AI_PROVIDER=local`, current `GroundedLessonSafetyValidator.validate_output`):

| Case | Claim | Current verdict | Correct outcome |
|---|---|---|---|
| Exact grounded (Earth/Sun) | exact restatement | ACCEPTED | ACCEPT |
| **C**: Photosynthesis → *nuclear* energy | chem→nuclear swap | **ACCEPTED** | REJECT (CONTRADICTED) |
| **D**: TCP + "guarantees zero packet loss" | added clause | **ACCEPTED** | REJECT (UNSUPPORTED) |
| **E**: "Binary search always completes in exactly 7 operations" | numeric | **ACCEPTED** | REJECT (UNSUPPORTED) |
| **F**: "Exercise permanently prevents every cardiovascular disease" | causal | **ACCEPTED** | REJECT (UNSUPPORTED) |
| **G**: HTTP "maintains permanent server-side session state" | contradiction | **ACCEPTED** | REJECT (CONTRADICTED) |
| **L**: "three-way handshake to destroy the connection" | relation swap | **ACCEPTED** | REJECT (CONTRADICTED) |

Result: **6 of 7 fabrication cases currently pass.** The root cause is structural: word-overlap is tolerant of swapped attributes, added absolute clauses, and contradicting predicates. (Raising the threshold does not fix D/G/L, which have high overlap, and would break legitimate paraphrases.)

Important analytic finding: no deterministic, vocabulary-only mechanism can separate a valid paraphrase (Test B) from a vocabulary-overlap fabrication (Test C) — they are feature-identical at the token level. Real paraphrase-vs-fabrication separation requires a semantic entailment decision, which in this repo means the existing AI provider abstraction (LLM verifier). The deterministic layer is therefore designed for fail-safe *rejection* (restatement acceptance + conservative high-risk rejection + uncertainty), and the LLM verifier is the entailment authority.

## 3. Proposed architecture

Layered, matching §15 of the master prompt. Validation pipeline in `validate_output` and new `app/services/claim_grounding.py`:

```
SOURCE (SourceContext)
  ├─ Layer 1  empty source                        (validate_input, unchanged)
  ├─ Layer 2  prompt-injection scan               (validate_input, unchanged)
  ├─ Layer 3  lexical per-topic coverage pre-check (KEEP, now preliminary only)
  └─ Layer 4+ claim-level semantic grounding (new):
       source text
         └─ sentence evidence units (per unit/slide; provenance: position, unit title, slide)
       generated topic description
         └─ claim segmentation (deterministic sentence split + light discourse merge)
              └─ claim classification (factual/definition/numeric/causal/comparative/
                  procedural/analogy/pedagogical + risk: high/low)
                   └─ evidence retrieval (per claim, in-memory):
                        ⴰ lexically preselect candidate evidence units (cheap, bounded)
                        ⴰ embed claim + preselects via EmbeddingProvider (batched)
                        ⴰ rank with app.ai.retrieval.cosine_similarity (top-k = MAX_EVIDENCE)
                        ⴰ provenance retained (SourceEvidence: unit index, title, text, similarity)
                        ⴰ fallback to lexical ranking when embedding unavailable/fails
                   └─ claim-level verifier:
                        LLMGroundingVerifier (Option A, existing AI provider abstraction)
                          → strict JSON {verdict, confidence, evidence_spans, reason}
                          → Pydantic-validated; malformed/timeout/error → UNCERTAIN
                          → claim + evidence wrapped as DATA (injection-fenced)
                        DeterministicGroundingVerifier (conservative local fallback;
                          used when AI_PROVIDER == "local" or no provider configured)
                          → restatement acceptance (near-verbatim)
                          → absolute/negation-marker rejection (always/never/only/every/
                            exactly/guarantees/permanently/must/...)
                          → causal-change verb high-risk (increases/reduces/causes/prevents/
                            destroys/converts/produces/stores/...)
                          → contradiction table (antonym predicate pairs, e.g.
                            establish↔destroy, improves↔prevents)
                          → everything else: UNCERTAIN
                   └─ deterministic policy (layer 6):
                        UNSUPPORTED/CONTRADICTED             → claim REJECT (topic fails)
                        SUPPORTED + confidence ≥ MIN_CONFIDENCE → claim PASS
                        SUPPORTED + low confidence           → treat as UNCERTAIN
                        UNCERTAIN                            → high-risk claim: REJECT
                                                               low-risk claim: PASS + flag
                        verifier error / no evidence         → UNCERTAIN → high-risk REJECT
                   └─ topic result: REJECT if any claim fails; else PASS (flags recorded)
                        lesson decision: REJECT if any topic fails
```

Structured grounding report (provenance, §12/§13) stored in version `generation_metadata["grounding"]` (PortableJSONB; evidence text capped to snippets so nothing raw/large is persisted): per-topic claim verdicts, evidence ids/text/similarity, verifier method + provider/model/latency, policy decisions, flags.

Naming/terminology (§16): `ai_safety_grounding_*` metrics; config `AI_LESSON_GROUNDING_*`; docstrings explicitly say lexical coverage ≠ entailment.

## 4. Files to change

- **NEW `app/services/claim_grounding.py`** — Pydantic result types (`SourceEvidence`, `ClaimGroundingResult`, `GroundingVerdictResult`); sentence segmentation; claim classification (with high-risk markers); claim/predicate helpers (choice table for contradiction ::: antonym); evidence-unit construction + retrieval (embedded + lexical fallback); `GroundingVerifier` protocol; `LLMGroundingVerifier`; `DeterministicGroundingVerifier`; `run_claim_grounding()` orchestrator (bounded claim batches, fail-safe enumeration of failure modes).
- **MODIFY `app/services/lesson_safety.py`** — keep `LessonSafetyError`, `NoopLessonSafetyValidator`, Protocol; extend `GroundedLessonSafetyValidator` with the layered pipeline (layers 3→6) and grounding report; add `build_safety_validator(name, *, ai_service=None, embedding_provider=None)`.
- **MODIFY `app/services/lesson_generation_service.py`** — pass `ai_service=self._ai` into validator construction so the LLM verifier reuses retries/timeout/cache/usage telemetry.
- **MODIFY `app/core/config.py`** — replace/supplement `AI_LESSON_SOURCE_COVERAGE_THRESHOLD` with `AI_LESSON_GROUNDING_ENABLED`, `AI_LESSON_GROUNDING_MIN_CONFIDENCE`, `AI_LESSON_GROUNDING_MAX_EVIDENCE`, `AI_LESSON_GROUNDING_MAX_CLAIMS_PER_TOPIC`, `AI_LESSON_GROUNDING_VERIFIER` (`auto|llm|deterministic`), keep `AI_LESSON_SOURCE_COVERAGE_THRESHOLD` as the layer-3 pre-check. Production guard: raise when `APP_ENV=="production"` and grounding is disabled / min-confidence ≤ 0 / max-evidence < 1 (no silent disable in production).
- **MODIFY `app/services/lesson_prompt_builder.py`** — (only if needed) expose per-unit slide intervals for evidence provenance; otherwise unchanged.
- **NEW tests** (see §5).
- **NEW `docs/audits/SEMANTIC_GROUNDING_REMEDIATION_REPORT.md` / `EVIDENCE_MATRIX.md` / `COMMAND_LOG.md`** (Phase 2 output).

Constraint-check: FastAPI/SQLAlchemy/Celery/provider/retrieval D6 (app-side cosine) all preserved. No new runtimes, no pgvector claims, no live-provider claims.

## 5. Tests to add

- `tests/unit/test_claim_grounding.py` — segmentation, classification (risk), evidence retrieval (provenance, deterministic order), verifier failure modes: timeout, malformed JSON, missing verdict, bad confidence, provider error, no/empty evidence, embedding failure, zero-norm embedding, claim-segmentation failure — **none may resolve to SUPPORTED**.
- `tests/unit/test_semantic_grounding_adversarial.py` — master-prompt Test A–L; plus injection in source / in evidence / in generated claims / educational prompt-injection discussion (no false positive on Test I); plus mixed claims (Test H) fail at topic level.
- `tests/unit/test_llm_grounding_verifier.py` — LLM verifier against a stubbed `AIContentService`: scripted verifiable JSON → verdict accepted; injection-looking evidence does not change verdict (containment); malformed/error → UNCERTAIN.
- `tests/unit/test_grounding_benchmark.py` + `tests/fixtures/grounding/benchmark_cases.py` — dataset (20+ supported, 10+ paraphrases, 20+ unsupported, 10+ contradictions, 10+ vocab-overlap, 10+ numeric/causal, 10+ adversarial) with expected binary accept/reject; reports real TP/FP/FN/TN + precision/recall per category for the deterministic verifier (and documents that the LLM verifier is the production entailment authority, exercised via mock contract tests).
- `tests/integration/test_lesson_grounding_persistence.py` — real lesson flow with a fake `ai_service`:
  - grounded output → version SUCCEEDED, lesson READY, blocks persisted;
  - vocab-overlap fabricated output → `LessonSafetyError`, version FAILED (`error_code="safety_rejected"`), lesson FAILED, **no** SUCCEEDED version, **no** blocks;
  - mixed topics (one fabricated) → whole lesson rejected.
- Existing `test_grounding_enforcement.py`, `test_lesson_generation_service.py`, `test_lesson_prompt_builder.py` remain green (no deletion/weakening; D4/D5 tests keep passing).

## 6. Dependency implications

None new. Uses stdlib `re`, existing `app.ai.embeddings`, `app.ai.retrieval.cosine_similarity`, existing `AIContentService`/provider abstraction, existing `metrics`, existing `PortableJSONB` metadata. Local embedding provider keeps everything deterministic in CI (`EMBEDDING_PROVIDER` falls back to `AI_PROVIDER=local`).

## 7. Failure modes (and safe result)

| Failure | Result |
|---|---|
| Verifier timeout / provider error / malformed / missing verdict / invalid confidence | `UNCERTAIN` (never `SUPPORTED`) |
| No evidence retrieved / empty evidence | `UNCERTAIN` → high-risk REJECT |
| Embedding failure / zero-norm / dimension mismatch | lexical fallback ranking; verifier still runs |
| Source extraction / claim segmentation failure | topic REJECT with recorded reason |
| Injection text in source/evidence/claim | treated as data (fenced prompt); injection signature in a claim → pre-emptive high-risk rejection; `validate_input` still blocks source-level injections |
| A threshold set to 0 / grounding disabled | prohibited in production (config guard), dev/test-only otherwise |

## 8. Expected evidence (master prompt §35)

G1 lexical no longer sole decision · G2 per-claim evaluation · G3 semantic retrieval (embeddings + cosine, in-memory) · G4 similarity ≠ entailment (LLM verdict is primary; deterministic never calls cosine a verdict) · G5 vocab-overlap fabrication rejected (C/L via policy; LLM path) · G6 contradiction rejected (G/L) · G7 unsupported numeric/causal rejected (D/E/F) · G8 paraphrase accepted (LLM verifier path demonstrated; deterministic honest UNCERTAIN/REJECT documented) · G9 mixed content cannot pass (topic fail-fast) · G10 verifier failures fail safe (failure-mode suite) · G11 injection cannot control verifier (fencing + tests) · G12 rejected output cannot become successful version (persistence test) · G13 provenance preserved (SourceEvidence + metadata) · G14 D1–D3 injection protection intact · G15 existing tests green · G16 no pgvector/live-provider/E2E claims.

Anticipated classification: **PARTIALLY VERIFIED** for the deterministic-only environment (paraphrase acceptance requires the LLM verifier), **VERIFIED** for the claim-level pipeline + policy + fail-safety, pending Phase 2 results.