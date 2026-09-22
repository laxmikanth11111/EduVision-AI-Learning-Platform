# PRODUCTION_EVIDENCE_MATRIX.md

**Date:** 2026-09-21 — independent re-verification of production claims for the EduVision AI platform.

Legend: ✅ VERIFIED · ⚠️ PARTIAL / CONDITIONAL · 🔴 NOT VERIFIED / GAP FOUND-AND-FIXED · 📌 DOCUMENTED LIMITATION

## A. Test suites and static gates

| Claim | Evidence | Status |
|---|---|---|
| Unit suite passes | `pytest tests/unit` → 1568 passed, 1 warning, 212.03s | ✅ |
| Integration suite passes | `pytest tests/integration` → 209 passed, 130.98s | ✅ |
| Ruff clean | `ruff check app tests scripts` → All checks passed | ✅ |
| Mypy within CI budget | `mypy app` → 83 errors (CI gate ≤86), unchanged from baseline | ✅ |
| Grounding/adversarial suites | claim_grounding + semantic_grounding_adversarial + llm_grounding_verifier + benchmark + embedding_config + rag_embeddings → 220 passed, 26.26s | ✅ |

## B. Grounding behaviour

| Claim | Evidence | Status |
|---|---|---|
| Deterministic verifier exists and is the local/tests backend | `resolve_verifier` in app/services/claim_grounding.py returns deterministic verifier for `AI_PROVIDER=local` / no ai_service | ✅ |
| LLM verifier is the non-local backend | Live run with `AI_PROVIDER=gemini`: `verifier: llm`, claims `method="llm"` | ✅ |
| LLM verifier parses real provider output | Live: fabrication → UNCERTAIN(1.0, high) → REJECT `method="llm"`; restatement & paraphrase → SUPPORTED → PASS `method="llm"` | ✅ (fixed 3a) |
| Verifier never silently abandons to unsafe | Every failure mode returns UNCERTAIN with `verifier_error` flag; UNCERTAIN+LOW is a documented deliberate PASS | ✅ |
| Fabrication rejection holds at pipeline level before LLM | Adversarial contract: injection claims rejected pre-LLM; `svc.calls == 0` | ✅ |
| Deterministic benchmark verdict accuracy | 95/95 verdicts match dataset (1.0); safety 0.9789; P/R/F1 0.9828; FN 1, FP 1 flagged | ✅ |
| Undocumented FPs eliminated | Fixture diffs confirm ~15 earlier flags were removed where behaviour legitimately improved; remaining FN/FP are flagged known limitations | ✅ |
| Temporal/directional reversals rejected | New cases: before↔after → unsupported; sender↔recipient reversal → unsupported | ✅ |
| Number/unit substitution rejected | New cases: 3 vs 4 clock cycles → UNCERTAIN+high→REJECT; GHz vs MHz → UNCERTAIN+high→REJECT | ✅ |
| Absolute claims require full evidence | `only/solely/exclusively/entirely/nowhere/every/must/all` detected over raw token stream → unsupported, REJECT | ✅ |
| Phase markers do not falsify restatement | `shared_seq` subsequence + phase-marker order check; mirrored `before/after` → UNCERTAIN (conservative) | ✅ |
| New negation in claim = fabrication | `claim_negated - ev_negated` non-empty → contradicted/unsupported; reverse-polarity loop uses `(claim_base - claim_negated) & ev_negated` | ✅ |
| 16 documented deterministic limitations reachable by LLM authority | Pipeline safety 0.8316; FN 13, FP 3 — every one carries a `deterministic_known_limitation` flag | 📌 |
| Prior claim "LLM verifier exercised (not dead code)" | Re-verified: wiring true, but **real-provider parsing was broken until this pass** (uppercase-enum bug); now live-proven | ⚠️→✅ |

## C. AI provider / embeddings

| Claim | Evidence | Status |
|---|---|---|
| Gemini chat provider works with shipped `.env` | 3 real calls: `ai_generation_success`, model `gemini-3.5-flash`, retry 0, latency 1.8–11.8s, cost ≈USD 0.00006 each | ✅ |
| Embeddings work with shipped configuration | **Was 🔴**: 404 twice (`gemini-3.5-flash` inherited; `text-embedding-004` unavailable). **Now ✅**: `EMBEDDING_MODEL=gemini-embedding-001` → 3072-dim vectors, HTTP 200 | ✅ (fixed 3b) |
| Embedding model match for this account | `GET /v1beta/models` → embedContent-capable: `gemini-embedding-001`, `gemini-embedding-2`, `gemini-embedding-2-preview` | ✅ |
| Embedding provider enforces dimension contract | Probe forcing 768 vs returned 3072 → `AIInvalidResponseError` with expected/actual dims | ✅ |
| Embeddings never fall back to chat model silently | `EmbeddingProviderConfig.from_settings()` no longer inherits `AI_MODEL` (regression test added) | ✅ (fixed) |
| Semantic evidence retrieval degrades gracefully | Downstream path falls back to deterministic ranking (source order) with a warning log | ✅ |

## D. Pipeline / deployment

| Claim | Evidence | Status |
|---|---|---|
| Docker compose file is valid | `docker compose config -q` → exit 0 after `cp .env.example .env` (README-recommended operator step); only obsolete `version:` warning | ✅ |
| Docker daemon available | `docker version --format ...` → server 29.6.2 | ✅ (not used to run stack) |
| Full stack boots and serves /frontend | Not executed in this pass (services are not running locally) | 🔴 |
| Canonical frontend is `backend/frontend/` | Repo README: `frontend/ # CANONICAL (served at /frontend)`; `EduVision_AI_Frontend/ # DEPRECATED prototype — do not modify` | ✅ |
| Declared Python version | `pyproject.toml requires-python = ">=3.13"`, Dockerfile `FROM python:3.13-slim` (all stages); local verification runtime = CPython 3.11.9 | ⚠️ docs/os-pair gap |
| CI mypy/ruff gates enforced | `.github/workflows/ci.yml:223-253` — mypy no-regression gate with explicit baseline 86 | ✅ |
| pgvector production RAG active | `backend/.env RAG_INDEXING_ENABLED=false`; `app/ai/retrieval.py` documents app-side cosine (D6) | 🔴 (functional gap, by config) |
| Root `.env` present for compose | README instructs `cp .env.example .env`; root `.env` absent in this checkout (operator step) | ⚠️ documented |

## E. Secrets hygiene

| Claim | Evidence | Status |
|---|---|---|
| Provider keys gitignored and outside tracked audit artifacts | Keys live in `backend/.env` (gitignored); this pass reproduces **no** secret; logs show key-present only | ✅ |
| `.env.example` present with embedding settings documented | `test_env_example_documents_embedding_settings` + file inspection | ✅ |