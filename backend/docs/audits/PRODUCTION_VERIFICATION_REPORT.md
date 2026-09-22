# PRODUCTION_VERIFICATION_REPORT.md

**Date:** 2026-09-21
**Location:** backend/docs/audits/
**Scope:** Independent production verification of the EduVision AI learning platform, with focus on the lesson-grounding (claim verification) path, AI provider wiring, embeddings/RAG configuration, and CI/test gates. This report supersedes earlier per-feature audit notes for anything it directly contradicts.

---

## 1. Verdict

`DEVELOPMENT READY — marks a clear step towards a trial deployment (DEPLOYMENT CANDIDATE).`

- Code-level and AI-provider-path verification **passed**; the two most serious production-path defects — the LLM grounding verifier never parsing real provider output, and embeddings never working under the shipped configuration — were **found, fixed, and proven live** during this pass.
- **DEPLOYMENT READY is not yet claimed** because the full Docker stack has not been brought up and smoke-tested in this pass, the project declares Python >=3.13 while the verification runs on 3.11.9 (CI images use 3.13, so that risk is contained to unexercised-3.13 code paths), and RAG indexing is explicitly disabled (`RAG_INDEXING_ENABLED=false`).

## 2. What was independently verified (summary)

| Area | Result |
|---|---|
| Full unit suite (`tests/unit`) | **1568 passed** in 212.03s (baseline before this pass: 1561; +7 justified changes/tests) |
| Full integration suite (`tests/integration`) | **209 passed** in 130.98s (unchanged) |
| `ruff check app tests scripts` | **Clean** |
| `mypy app` (CI gate: ≤86 errors) | **83 errors** — unchanged from today's baseline, no growth from this pass |
| Grounding benchmark (95 cases) | deterministic verdict **accuracy 1.0** (95/95), safety accuracy 0.9789, precision/recall/F1 **0.9828** (TP 57, FN 1, FP 1 — both flagged/documented) |
| Real pipeline benchmark (95 cases) | safety accuracy 0.8316, precision 0.9375, recall 0.7759 (FN 13, FP 3 — all documented flags) |
| LLM verifier, live (Gemini `gemini-3.5-flash`) | **Works end-to-end after fix**: fabrication→REJECT, restatement→PASS, paraphrase→PASS (`method="llm"`) |
| Embeddings, live (Gemini `gemini-embedding-001`) | **Works after fix**: 3072-dim vectors; `batchEmbedContents` returns 200 |
| `docker-compose.yml` | `docker compose config` **valid** (exit 0; daemon 29.6.2); only warning is the obsolete `version:` attribute |

## 3. Critical defects found and remediated (this pass)

### 3a. The LLM grounding verifier had NEVER parsed a real provider reply
- **Symptom:** every real Gemini call logged `lesson_grounding_verifier_error error='verifier call/parse failed'` and every claim fell back to `method="llm_error"` / `verdict=uncertain`.
- **Root cause:** `LLMGroundingVerifier.VERIFIER_SYSTEM_PROMPT` asks the provider for uppercase enums (`"SUPPORTED" | "UNSUPPORTED" | ...`); the provider complies; but `GroundingVerdictResult.verdict` is a pydantic enum accepting only lowercase. `_extract_verdict_json()` returned the raw dict, so `model_validate()` raised `ValidationError` on every real reply.
- **Why earlier audits missed it:** prior evidence (`INDEPENDENT_LLM_VERIFIER_REAL_PATH.md`, 2026-09-15) exercised the real `validate_output` path with a **scripted fake AI** that returned lowercase JSON — it proved wiring, not parsing of real provider output.
- **Fix:** `_extract_verdict_json()` in `app/services/claim_grounding.py` now normalizes the `verdict` value to lowercase before validation. Regression test added in `tests/unit/test_llm_grounding_verifier.py` covering `SUPPORTED/UNSUPPORTED/CONTRADICTED/UNCERTAIN`.
- **Live proof after fix:** a real `gemini-3.5-flash` call classified `DNS resolves domain names to IPv6 addresses.` (evidence: IPv4) as UNCERTAIN/high → **REJECT** `method="llm"`; `TCP uses a three-way handshake...` and the OSI-paraphrase as **SUPPORTED → PASS** `method="llm"`.

### 3b. Embeddings could not work under the shipped configuration
- **Symptom:** `claim_grounding_embedding_fallback error='embedding retrieval failed'` in every live run; semantic evidence ranking silently degraded to deterministic (source-order) ranking.
- **Root cause 1:** `EmbeddingProviderConfig.from_settings()` inherited the **chat model** (`EMBEDDING_MODEL or AI_MODEL`). `.env` sets `AI_MODEL=gemini-3.5-flash`, which is not `embedContent`-capable → HTTP 404.
- **Root cause 2:** the provider's default embedding model `text-embedding-004` is also unavailable to this API key (404), which only exposes `gemini-embedding-001` (3072-dim), `gemini-embedding-2`, `gemini-embedding-2-preview`.
- **Fix:** `app/ai/embeddings/config.py` no longer inherits `AI_MODEL` (falls back to the provider's own embedding default when `EMBEDDING_MODEL` is unset); `GeminiEmbeddingProvider.default_model` becomes `gemini-embedding-001`; `backend/.env` now sets `EMBEDDING_PROVIDER=gemini` and `EMBEDDING_MODEL=gemini-embedding-001`. Regression test added in `tests/unit/test_embedding_config.py`.
- **Live proof after fix:** `embed OK dims: 3072 vec_len: 3072`; the live grounding pipeline no longer logs the embed fallback.

## 4. Benchmark numbers (95 cases, authoritative)

Deterministic verifier (label-based):
```
total_cases 95  categories: restatement 21, paraphrase 13, unsupported 21,
contradiction 11, vocab_overlap 14, numeric_causal 12, educational_injection 3
safety_accuracy 0.9789 | verdict_value_accuracy 1.0 | precision 0.9828 |
recall 0.9828 | f1 0.9828 | TP 57 | FN 1 | FP 1 | documented_known_limitations 16
```
Real pipeline (`classify_claim` → verifier → safety policy), risk/claim_type produced by the pipeline itself:
```
safety_accuracy 0.8316 | precision 0.9375 | recall 0.7759 | TP 45 | FN 13 | FP 3
```
The pipeline recall ceiling is dominated by **documented** low-risk factual fabrications (UNCERTAIN+LOW is a deliberate PASS; each carries a `deterministic_known_limitation` flag). The LLM verifier is the authority expected to close them.

Remediation added to the deterministic verifier in this pass (verdict-level):
- Raw-token marker detection for absolutes (`only/solely/exclusively/entirely/nowhere/every/must/all`) — fixes multiple undocumented FPs.
- Restatement branch now requires **order-preserving subsequence** vs evidence, rejects phase reversals (`before`↔`after`) and directional reversals, and refuses claims that **introduce new negation**.
- Negation window constrained to tokens **after** the negator (±3 → +3) to stop sweeping unrelated preceding nouns into `contradicted`.
- Numeric/unit substitutions (3 vs 4 cycles; GHz vs MHz) left as UNCERTAIN+high → REJECT.

## 5. Gate status (as CI would run them)

| Gate | Command | Result | CI requirement |
|---|---|---|---|
| Ruff | `ruff check app tests scripts` | pass | pass |
| Mypy budget | `mypy app` | 83 errors | ≤86 (no growth) |
| Unit | `pytest tests/unit` | 1568 passed | pass |
| Integration | `pytest tests/integration` | 209 passed | pass |
| Docker compose | `docker compose config -q` | exit 0 (with root `.env` per README) | pass |

## 6. Security / secrecy notes

- Provider keys are stored in `backend/.env` (gitignored) and are **not reproduced** in any artifact of this pass.
- The grounding prompts wrap all evidence/claim text in explicit `[EVIDENCE_START]/[EVIDENCE_END]` + `[CLAIM_START]/[CLAIM_END]` DATA fences; injection-style claims are pre-emptively rejected at the pipeline level (verified by unit contract + adversarial tests).

## 7. Cost / runtime of the live verification

- 3 verifier+evidence `ai_generation_success` calls: estimated cost ≈ USD 0.00006 each, latency 1.8–11.8s, `retry_count=0`, model `gemini-3.5-flash`.
- 2 embedding probes (success + error paths) + 1 model-list call.
- Total billed ≈ USD 0.0005.

## 8. Traceability

- Evidence: `PRODUCTION_EVIDENCE_MATRIX.md`
- Commands: `PRODUCTION_COMMAND_LOG.md`
- Outstanding items: `REMAINING_GAPS.md`