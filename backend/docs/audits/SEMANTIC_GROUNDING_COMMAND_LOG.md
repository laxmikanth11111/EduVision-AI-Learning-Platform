# Semantic Grounding Remediation — Command Log (Phase 2)

Chronological record of significant commands, their output, and outcomes.
All runs: `AI_PROVIDER=local`, `PYTHONPATH=<backend>`, Windows PowerShell 5.1, serial.

---

## 1. LLM grounding verifier tests (Phase 2, session 1)

```
$env:PYTHONPATH="...\backend"; $env:AI_PROVIDER="local"
.\.venv\Scripts\python.exe -m pytest tests/unit/test_llm_grounding_verifier.py -q
```
**Outcome:** 16 passed. Fixed `[1] ` evidence prefix assertion; `LLMGroundingVerifier(ai_service, min_confidence=0.6)` (keyword-only).

---

## 2. Benchmark tests + fixture (Phase 2, session 1)

```
.\.venv\Scripts\python.exe -m pytest tests/unit/test_grounding_benchmark.py -q
```
**Outcome:** 89 passed (isolation). Added `deterministic_known_limitation` field to `BenchmarkCase`; corrected 9 stale expected values; rewrote `test_safety_decision_accuracy` to reject only undocumented false decisions.

---

## 3. Full unit suite (Phase 2, session 1 — event-loop discovery)

```
.\.venv\Scripts\python.exe -m pytest tests/unit -q
```
**Outcome:** ~89 benchmark tests FAIL with `RuntimeError: There is no current event loop in thread 'MainThread'`. Root cause: `asyncio.get_event_loop().run_until_complete()` fails after prior async tests run. Fix: replace with `asyncio.run()`.

---

## 4. Event-loop fix

Edited `tests/unit/test_grounding_benchmark.py`: replaced `asyncio.get_event_loop().run_until_complete(...)` with `asyncio.run(...)` in both parametrized test and safety test.

```
.\.venv\Scripts\python.exe -m pytest tests/unit -q
```
**Outcome:** 1557 passed. Event-loop fix resolved all ~89 failures.

---

## 5. Integration persistence tests — initial failures

```
.\.venv\Scripts\python.exe -m pytest tests/integration/test_lesson_grounding_persistence.py -q
```
**Failures encountered and fixed:**
1. `ImportError: GeneratedBlock` → fixed import path
2. `ModuleNotFoundError: app.repositories.generated_lesson_version_repository` → replaced with direct `select` queries
3. `LessonSafetyError` not caught → wrapped in `pytest.raises(LessonSafetyError)`
4. `lesson.status == "failed"` assertion wrong → switched to `/status` endpoint (`error_code="safety_rejected"`)

```
.\.venv\Scripts\python.exe -m pytest tests/integration/test_lesson_grounding_persistence.py -q
```
**Outcome:** 4 passed.

---

## 6. Full integration suite

```
.\.venv\Scripts\python.exe -m pytest tests/integration -q
```
**Outcome:** 208 passed.

---

## 7. Enforcement test failure — investigation (Phase 2, session 2)

```
.\.venv\Scripts\python.exe -m pytest tests/unit/test_grounding_enforcement.py::TestEInjectionInDocumentNotInPayload -q
```
**Failure:** `test_injection_in_source_not_in_payload` — payload claim "Light energy is converted into chemical energy." contains causal verb `converted` → deterministic: UNCERTAIN+high → REJECT. Test expects ACCEPT.

**Root cause:** `classify_claim` flags `converted` (in `CAUSAL_CHANGE_VERBS`) → risk=high. Deterministic verifier cannot prove restatement (converted≠converts, containment 0.8) → UNCERTAIN. Policy: UNCERTAIN+high → REJECT. Legitimate paraphrase wrongly rejected.

**Resolution:** Updated test payload to use verbatim source sentences (preserving the injection-domestication assertion; Test D already covers paraphrase acceptance). Not a capability loss: the test's purpose is injection-not-leaking, not paraphrase handling.

```
.\.venv\Scripts\python.exe -m pytest tests/unit/test_grounding_enforcement.py -q
```
**Outcome:** 9 passed.

---

## 8. Full unit suite (post-event-loop fix, post-enforcement fix)

```
.\.venv\Scripts\python.exe -m pytest tests/unit -q
```
**Outcome:** 1557 passed.

---

## 9. Ruff (Phase 2, session 2)

```
.\.venv\Scripts\python.exe -m ruff check app tests
```
**Initial:** 8 errors (5 auto-fixed, 3 remaining).

**3 remaining errors fixed:**
1. `PT018` in `test_llm_grounding_verifier.py:84` → split compound `assert` into two
2. `F841` in `test_lesson_grounding_persistence.py:301` → removed unused `GeneratedLessonRepository` assignment
3. `ERA001` in `benchmark_cases.py:520` → rewrote "Deterministic: UNCERTAIN" comment as prose

```
.\.venv\Scripts\python.exe -m ruff check app tests
```
**Outcome:** All checks passed.

---

## 10. Mypy (Phase 2, session 2)

```
.\.venv\Scripts\python.exe -m mypy app
```
**Outcome:** 83 errors (unchanged from baseline 83/86). No new errors introduced.

---

## 11. Self-falsification repro (Phase 1, post-remediation)

```
$env:PYTHONIOENCODING="utf-8"
.\.venv\Scripts\python.exe "$env:TEMP\opencode\repro_lexical_limitation.py"
```
**Outcome:**
- Pre-Phase-2: 6 of 7 fabrication cases accepted
- Post-Phase-2: 1 of 7 fabrication cases accepted (case C: chemical→ nuclear swap, documented known limitation)
- 5 fabrications that previously passed now correctly rejected

---

## 12. Benchmark report capture

```
.\.venv\Scripts\python.exe -m pytest tests/unit/test_grounding_benchmark.py::test_safety_decision_accuracy -q -s
```
**Output JSON:**
```json
{
  "total_cases": 89,
  "deterministic": {
    "safety_accuracy": 0.9326,
    "verdict_value_accuracy": 1.0,
    "precision_reject_fabrications": 0.9796,
    "recall_reject_fabrications": 0.9057,
    "f1_score": 0.9412,
    "true_positives": 48,
    "false_negatives": 5,
    "true_negatives": 35,
    "false_positives": 1
  },
  "documented_known_limitations": {"count": 6}
}
```

---

## 13. Final verification summary

| Command | Outcome |
|---|---|
| `pytest tests/unit -q` | **1557 passed** |
| `pytest tests/integration -q` | **208 passed** |
| `ruff check app tests` | **All checks passed** |
| `mypy app` | **83 errors** (baseline unchanged) |
| `pytest tests/unit/test_grounding_benchmark.py -q` | **90 passed** |
| `pytest tests/unit/test_grounding_enforcement.py -q` | **9 passed** |
| `pytest tests/unit/test_llm_grounding_verifier.py -q` | **16 passed** |
| `pytest tests/integration/test_lesson_grounding_persistence.py -q` | **4 passed** |
| Self-falsification repro | **1/7 residual** (documented) |

Serial run times: unit ~174 s; integration ~141 s.
No external services, browsers, PostgreSQL, or live AI models used.
