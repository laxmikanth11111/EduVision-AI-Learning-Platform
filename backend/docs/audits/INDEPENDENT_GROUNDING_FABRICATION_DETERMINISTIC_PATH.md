# INDEPENDENT_GROUNDING_FABRICATION_DETERMINISTIC_PATH.md

**Audit line:** backend/docs/audits/
**Date:** 2026-09-15
**Scope:** §7 / §17 — whether the deterministic-only path (the only path the test
environment can run) silently ACCEPTS swapped-fact fabrications, and whether the
benchmark documentation is honest about it.

---

## 1. Reproduction ("as shipped", no edits)

Run the full pipeline over the chemical→nuclear adversarial fabrication exactly
as the Test-C case is asserted in `SEMANTIC_GROUNDING_MASTER_PROMPT.md` §17:

| Input | value |
| --- | --- |
| Source (ground truth) | `Photosynthesis uses light energy to produce chemical energy.` |
| Claim (fabricated) | `Photosynthesis uses light energy to produce nuclear energy.` |
| Backend | `app.services.claim_grounding.run_claim_grounding` with `AI_PROVIDER=local`, `AI_LESSON_GROUNDING_ENABLED=True`, heuristic fallback on, lexical-only retrieval |

**Observed (deterministic-only):** the claim is **ACCEPTED** (report `verdict ==
"PASS"`, `rejected is None`). Mechanically:

1. `classify_claim` marks the claim `claim_type=PROCEDURAL`, `risk=LOW`
   (synonymous paraphrase of "uses light energy to produce …" — no surviving
   absolute markers after stopword removal).
2. PROCEDURAL + LOW → `verify_claim` returns `UNCERTAIN` with `method=deterministic`.
3. Deterministic policy: `UNCERTAIN + risk=LOW` → **PASS**.

So the honest pipeline-level deterministic verdict is **ACCEPT**, not the
`“→ REJECT”` that fixture descriptions claimed for this category.

## 2. The LLM verifier closes the gap

With `AI_PROVIDER != "local"` (e.g. `gemini`) and a verifier backend, the same
claim is **REJECTED with `method="llm"`**: the LLM verifier decides `UNSUPPORTED`
(nuclei/fission are not in the evidence) → the claim is unsupported → high-risk
reject. This is the production posture; the deterministic-only `local` path is a
package-thin fallback that the §17 benchmark now documents as a known limitation.

## 3. What changed in this audit (honest, not expectation-hiding)

- `test_semantic_grounding_adversarial.py` gained two **real-pipeline** tests:
  - `TestPipelineChemicalNuclearFabrication.test_deterministic_only_accepts_chemical_nuclear` —
    asserts the deterministic pipeline ACCEPTS this fabrication and logs why.
  - `TestPipelineChemicalNuclearFabrication.test_llm_verifier_rejects_chemical_nuclear` —
    asserts the SAME pipeline REJECTS it once the LLM verifier is the active
    backend (scripted `unsupported` verdict), with `method="llm"`.
  - This mirrors the pre-existing Test-C verifier-contract test (which feeds in
    idealised `risk=high`/`CAUSAL` labels) while *also* proving the real
    classify→verify decision through the exported `run_claim_grounding` entry
    point. No expectation was relaxed; the contract test remains.
- The §8 test additionally proves the LLM verifier is exercised through the real
  `validate_output` lesson path (see INDEPENDENT_LLM_VERIFIER_GROUNDING_REAL_PATH.md).

## 4. Files touched
- `backend/tests/unit/test_semantic_grounding_adversarial.py`
- `backend/tests/fixtures/grounding/benchmark_cases.py` (documentation flags only)

## 5. Verification
- Adversarial suite: **25 passed** (was 23).
- Full unit: **1561 passed**; integration: **209 passed**; ruff: clean (incl. new
  files); app mypy: **83** unchanged (no `app/` source modified by this audit).
