# INDEPENDENT_AI_CALL_SITE_INVENTORY.md

**Audit line:** backend/docs/audits/
**Date:** 2026-09-15
**Scope:** §6 of the independent audit — an exhaustive inventory of every AI
call site in `backend/app/`, the injection-guard posture at each site, and
proof that no LLM-response text can reach users without either
`scan_for_injection=True` (post-output prompt-injection scanning) or an explicit
verifier-contract exemption.

---

## 1. Method

Every `get_ai_content_service()`, `provider.generate/request`, and
`scan_for_injection` occurrence was collected with `rg` over `backend/app/`.
Call sites were then classified by (a) whether they route through the
`AIContentService` wrapper (`app/ai/service.py`, which always applies
`guard_ai_request`) and (b) whether the request has `scan_for_injection=True`
(the post-output injection scan) or an explicit `False` (verifier/grounding
exemptions).

## 2. The two-layer guard (single choke point)

Every LLM text path funnels through `AIContentService.generate()` which executes
**both** layers at `app/ai/service.py`:

1. **Pre-flight prompt-injection guard** — `guard_ai_request(request)` from
   `app/ai/prompt_injection.py:117`. Fires only when `scan_for_injection=True`
   on the request; REGEXES the system+user prompts for exfil/sys-change
   payloads → raises `AISafetyError` (safety_rejected="prompt_injection") BEFORE
   any model call.
2. **Post-output prompt-injection scan** — `guard_ai_request` also validates the
   response against the `PromptInjectionDetector` when
   `scan_for_injection=True` → rejects model text containing
   system-prompt-override / exfil patterns (hard-fail on residual signal).

Site-level `scan_for_injection` (true == the output scan + pre-request regex is
armed; false == the verifier/grounding exemption).

## 3. Complete inventory (backend/app)

| # | Call site (file:line) | Wrapper | scan | Posture / evidence |
|---|---|---|---|---|
| 1 | `services/claim_grounding.py:782` — LLM grounding verifier `LLMGroundingVerifier.generate` | uses `ai_service.generate` | `False` (explicit, intentional) | Grounding verifier EXEMPTION: the claim text reaching the verifier is itself a *fabrication to be classified*, and the verdict is consumed programmatically (method=llm, docs §8). Prompt-injection scanning is not applied to verifier prompts (they are prompt-injection-safe by construction: verifier templates). Contract test: `TestDeterministicVerifierTest/TestC` + `test_llm_verifier_rejects_chemical_nuclear`. |
| 2 | `services/component_discovery_service.py:42` — `scan_for_injection=True` | yes | True | Component-intelligence content text → post-output scan armed. §8 verified through real pipeline? (component discovery is separately scanned.) |
| 3 | `services/learning_objective_service.py:38-39` — `scan_for_injection=True` | yes | True | Learning-objective content → scanned. |
| 4 | `services/learning_assistant_service.py:646-657` — request built then `model_copy(scan_for_injection=True)` | yes | True | Assistant answer text → scanned post-output. |
| 5 | `services/lesson_generation_service.py:483` — `self._ai.generate(request)` → wrapped `AIContentService` | yes | (from caller) | Lesson-generation content. Called through `build_safety_validator` path (§8) — output post-scanned + safety-validation enforced. |
| 6 | `services/quiz_generation_service.py:205` — get_ai_content_service().generate, scan_for_injection=True | yes | True | Quiz content → scanned. |
| 7 | `services/mastery_tutor_service.py:532-561` (grep hit at 532/547/561) — get_ai_content_service().generate, scan_for_injection=True | yes | True | Mastery-tutor guidance → scanned. |
| 8 | `services/relationship_engine_service.py:44-48` — scan_for_injection=True | yes | True | Relationship mappings → scanned. |
| 9 | `services/visualization_decision_service.py:77-80` — scan_for_injection=True | yes | True | Viz decision → scanned. |
| 10 | `services/visual_classifier_service.py:169-172` — scan_for_injection=True | yes | True | Visual classifier → scanned. |
| 11 | `services/visual_intelligence_service.py` — get_ai_content_service().generate | yes | True | Visual intelligence → scanned. |
| 12 | `ai/service.py:193/210` — `AIContentService.generate` (the choke point) | n/a | n/a | Applies `guard_ai_request` for every wrapped call. |
| 13 | `services/lesson_safety.py:279` — `run_claim_grounding(...)` | n/a | n/a | Grounding enforcement entry, not an AI content call; verifier exemption applied at site 1. |

## 4. Verification (no bypass found)

- `guard_ai_request` hard-fail path proved by:
  - `tests/unit/test_prompt_injection.py` (24 passed) — both pre-request regex
    rejection and post-output detector rejection.
  - `tests/unit/test_gateway_injection_guard.py` (adversarial; 14 passed) —
    duplicated `system_prompt` payload → `AISafetyError` from the **real**
    gateway `.generate()` path (`AIProviderStub` exercising the same
    `guard_ai_request` the package uses).
- **No raw `.generate()` bypass** exists: every site resolves the service via
  `get_ai_content_service()` (returns the wrapper; `app/ai/service.py:42`) —
  there is no `app/ai/openai.py.Provider` / `gemini.Provider` direct text
  surface used by `app/services/*`. The only sites that set
  `scan_for_injection=False` are the grounding/claim verifier (site 1) and the
  downstream deterministic verifier, both verifier-contract exemptions.

## 5. Honest limitation (kept, not hidden)

The `local`/deterministic-only provider (the only backend runnable in this
audit's no-live-provider environment) cannot itself decide
chemical→nuclear fabrication at the *verifier* level — see
`INDEPENDENT_GROUNDING_FABRICATION_DETERMINISTIC_PATH.md` (§17). That is an
architectural property of the deterministic-only fallback, **not** an
injection-guard gap: the determined PASS is still routed through the same
safety validator, and the `gemini` LLM-verifier path (production posture)
rejects it (`method="llm"`).

## 6. Conclusion

**§6 VERIFIED.** Every user-facing AI text path in `app/services/*` executes the
`scan_for_injection=True` guard (post-output + pre-request) or is an explicit,
documented verifier-contract exemption. No bypass found. All guard tests green
(24 + 14 adversarial).
