# PRODUCTION_COMMAND_LOG.md

**Date:** 2026-09-21 — exhaustive command log for the production-verification pass.
**Shell:** Windows PowerShell 5.1 · **Python:** `py -3` (CPython 3.11.9) · **Workdir:** `backend/` unless stated (repo root contains an em-dash).
**Env baseline for one-liner probes:** `AI_PROVIDER=gemini`, `EMBEDDING_PROVIDER=gemini`, `EMBEDDING_MODEL=gemini-embedding-001` in `backend/.env` (key not reproduced here).

## 1. Baseline & this-pass code state

```
git status --short                  # change surface review — this pass touched only:
                                    #   app/services/claim_grounding.py
                                    #   app/ai/embeddings/config.py
                                    #   app/ai/embeddings/providers/gemini.py
                                    #   tests/unit/test_llm_grounding_verifier.py
                                    #   tests/unit/test_embedding_config.py
                                    #   backend/.env (operator config: embedding model)
```

## 2. Static gates

```
py -3 -m ruff check app tests scripts            → All checks passed!
py -3 -m mypy app                                → 83 errors in 24 files (checked 334)
                                                  (CI gate ≤86; unchanged from baseline)
py -3 -m mypy app/services/claim_grounding.py app/ai/embeddings/config.py
      app/ai/embeddings/providers/gemini.py      → no errors in these files
```

## 3. Full suites

```
py -3 -m pytest tests/unit -q -p no:cacheprovider
    → 1568 passed, 1 warning in 212.03s         (baseline this morning: 1561)
py -3 -m pytest tests/integration -q -p no:cacheprovider
    → 209 passed in 130.98s
py -3 -m pytest tests/unit/test_claim_grounding.py \
      tests/unit/test_semantic_grounding_adversarial.py \
      tests/unit/test_llm_grounding_verifier.py \
      tests/unit/test_grounding_benchmark.py \
      tests/unit/test_embedding_config.py tests/unit/test_rag_embeddings.py -q
    → 220 passed in 26.26s
```

## 4. Grounding benchmark reports (95 cases)

```
py -3 -m pytest tests/unit/test_grounding_benchmark.py::test_safety_decision_accuracy \
      tests/unit/test_grounding_benchmark.py::test_pipeline_level_safety_fidelity \
      -q -p no:cacheprovider -s
→ 2 passed in 14.66s
→ deterministic: safety_accuracy 0.9789 | verdict 1.0 | precision 0.9828 | recall 0.9828
                 | f1 0.9828 | TP 57 | FN 1 | FP 1 | documented_known_limitations 16
→ pipeline:      safety_accuracy 0.8316 | precision 0.9375 | recall 0.7759
                 | TP 45 | FN 13 | FP 3
```

## 5. Live LLM-verifier verification (real Gemini calls)

```
py -3 live_verifier_probe.py            # backend/.env → gemini
→ provider: gemini | model: gemini-3.5-flash; 3x ai_generation_success
  retry_count=0; latency 1.8/2.3/11.8s; estimated_cost ≈USD 0.00006 each
→ FABRICATION  (DNS IPv6 vs IPv4 evidence): verdict uncertain 1.0 high,
                topic REJECT, method "llm"
→ RESTATEMENT  (TCP 3-way handshake):       verdict supported, PASS, method "llm"
→ PARAPHRASE   (OSI seven layers):          verdict supported, PASS, method "llm"
```

Raw provider reply captured before the fix (diagnosis step):
```
{"verdict": "UNCERTAIN", "confidence": 1.0, "evidence_spans": [], "reason": "..."}
→ ValidationError: Input should be 'supported', 'unsupported', 'contradicted' or 'uncertain'
   input_value='UNCERTAIN'   ← uppercase-vs-lowercase schema mismatch (fixed)
```

## 6. Live embedding verification (real Gemini REST)

```
py -3 embed_probe2.py
→ GET /v1beta/models (200): embedContent-capable →
     models/gemini-embedding-001, models/gemini-embedding-2-preview, models/gemini-embedding-2
→ gemini-embedding-001: embed OK (3072 dims)          (probe forcing 768 → dimension guard)
→ text-embedding-004:  404 "not ... supported for embedContent"
→ embedding-001:       404 "not found for API version v1beta"
py -3 embed_probe.py                                    # after config fix
→ model gemini-embedding-001 | dims 3072 | embed OK
```

## 7. Deployment checks

```
docker version --format "{{.Server.Version}}"           → 29.6.2
Copy-Item .env.example .env                             # README-recommended operator step
docker compose -f docker-compose.yml config -q          → exit 0
  warning: "attribute `version` is obsolete, it will be ignored" (cosmetic)
Remove-Item .env                                        # temp file removed; not left behind
```

## 8. Environment facts recorded

- Local CPython: 3.11.9; declared: `requires-python = ">=3.13"` + Dockerfile `python:3.13-slim`
- `backend/.env`: `AI_PROVIDER=gemini`, `AI_MODEL=gemini-3.5-flash`, `EMBEDDING_PROVIDER=gemini`, `EMBEDDING_MODEL=gemini-embedding-001`, `RAG_INDEXING_ENABLED=false`
- Repo root: no `.env` (compose requires the documented copy step)