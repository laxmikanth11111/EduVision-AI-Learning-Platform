# INDEPENDENT_LLM_VERIFIER_REAL_PATH.md

**Audit line:** backend/docs/audits/
**Date:** 2026-09-15
**Scope:** §8 — prove, through the REAL `validate_output` lesson path, that the
**LLM** verifier is (a) wired, (b) actually exercised (not dead code), and (c)
the decision that flips the chemical→nuclear fabrication from ACCEPT to REJECT.

---

## 1. Facts verified

The LLM verifier is not a hypothetical. Three independently-established facts:

1. **Resolution** — `resolve_verifier(settings, ai_service)` (claim_grounding.py:837)
   returns `LLMGroundingVerifier` when `AI_PROVIDER != "local"` (product posture,
   `AI_PROVIDER=gemini`) **or** when a provider is forced non-local; returns the
   deterministic verifier for `local` or when `ai_service is None`. Run through
   `run_claim_grounding` (claim_grounding.py:896), which is exported for the
   lesson pipeline.
2. **Wiring through validate_output** — `lesson_safety.py validate_output`
   (l.233+) → `run_claim_grounding` → `resolve_verifier` → the LLM verifier's
   `verify` → verdict `UNSUPPORTED` → claim rejected → `LessonSafetyError`.
3. **Real-path proof test** — `tests/integration/test_lesson_grounding_persistence.py`
   `test_llm_verifier_exercised_through_validate_output` drove the **real
   `LessonValidationResult` path** with a `_VerifierAwareFakeAI` (counts
   verifier calls) and `AI_PROVIDER` monkeypatched to `gemini` for the call,
   asserting `verifier_calls >= 1` and the fabricated claim is REJECTED
   (`method="llm"`).

## 2. The pipeline-level proof (chemical→nuclear)

- **Deterministic-only** (`AI_PROVIDER=local`, request `scan_for_injection=False`
  verifier exemption): `Photosynthesis uses light energy to produce nuclear
  energy.` → procedure claim, low risk → verifier `UNCERTAIN` → policy
  `UNCERTAIN+LOW` → **ACCEPT** (PASS). Real pipeline verdict = ACCEPT; this is
  the documented §17 limitation (fixture flag §14, `deterministic_known_limitation`).
- **With LLM verifier active** (`AI_PROVIDER=gemini`): verifier `verify` →
  `UNSUPPORTED` (nuclear energy is never asserted) → claim **REJECTED** with
  `method="llm"`. So the SAME fabrication is rejected in the production posture.

## 3. Suite + reproduction evidence

- Adversarial file (tests/unit/test_semantic_grounding_adversarial.py):
  **25 passed in 19.32s** — includes `TestPipelineChemicalNuclearFabrication`
  (deterministic-only ACCEPTS vs LLM-verifier REJECTS, same claim).
- Persistence integration file (tests/integration/test_lesson_grounding_persistence.py):
  **5 passed in 21.51s** — includes the LLM-through-validate_output test.
- Full integration: **209 passed in 141.57s**.

(Full command + env in INDEPENDENT_COMMAND_LOG.md; exact benchmark split in
INDEPENDENT_GROUNDING_BENCHMARK_INDEPENDENCE.md.)
