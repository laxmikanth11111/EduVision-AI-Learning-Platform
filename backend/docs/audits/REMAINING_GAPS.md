# REMAINING_GAPS.md

**Date:** 2026-09-21 — outstanding items after the production-verification pass, with impact and remediation. Complements PRODUCTION_VERIFICATION_REPORT.md.

## P0 — must address before a trial deployment

1. **Live full-stack smoke test**
   - Gap: `docker compose up` (postgres + redis + minio + backend + celery) was never booted in this pass; only `docker compose config` was validated (daemon 29.6.2 present).
   - Impact: wiring between services (migrations, S3/minio, celery task execution, `/frontend` serving) is unverified at runtime.
   - Remediation: provision root `.env` (`cp .env.example .env`, fill values), `docker compose up -d`, run the health endpoint + migrations + one lesson-generation flow, capture screenshots.

2. **Python 3.13 vs 3.11 divergence**
   - Gap: `pyproject.toml`/Dockerfile/CI declare `>=3.13`; evidence in this report was produced on CPython 3.11.9. Everything passes on 3.11; nothing here exercises 3.13-only behaviour.
   - Impact: a 3.13-only failure would only appear in CI/containers.
   - Remediation: CI already runs the pinned images (3.13) — confirm the green 3.13 job after the next push; optionally add a 3.12 job to widen coverage.

3. **LLM-verifier coverage of the 16 documented deterministic limitations**
   - Gap: pipeline safety accuracy is 0.8316 (FN 13, FP 3) with every case flagged `deterministic_known_limitation`; the LLM verifier is the intended authority that closes them.
   - Impact: low-risk factual fabrications still PASS in the deterministic-only posture (documented, deliberate); in the gemini posture they are REJECTED (live-verified).
   - Remediation: (a) run the 16 flagged cases through the real LLM verifier and record pass rates; (b) decide whether low-risk factual fabrications should become a hard reject even in deterministic-only mode; (c) publish expected_llm_safety_accuracy from a live run (the dataset currently reports it as "not executed here").

## P1 — should address

4. **LLM verifier checks `AI_LESSON_GROUNDING_MIN_CONFIDENCE` only, not numeric similarity evidence**
   - Gap: a confident-but-wrong SUPPORTED still passes; no budget on evidence spans returned.
   - Remediation: log `evidence_spans` coverage and add a span-coverage floor; add an LLM-verifier sidecar asserts metric so drift is observable.

5. **Embedding/provider config is per-environment**
   - The working embedding model (`gemini-embedding-001`, 3072 dims) was established empirically against this account; the provider default is now aligned, but `EMBEDDING_MODEL` remains an operator value.
   - Remediation: document the probe (GET /v1beta/models) in ops runbooks so a model change is a config-only change; add an embeddings health check to `/health`.

6. **RAG / pgvector production path is disabled**
   - Gap: `RAG_INDEXING_ENABLED=false`; embeddings are used only for app-side cosine evidence ranking. pgvector column/index claims in architecture docs are not exercised by default.
   - Impact: none for correctness today (deterministic ranking is safe); matters for vector-scale search quality claims.
   - Remediation: enable indexing in a staging environment and run the postgres/pgvector test suite (`tests/postgres/*`) against the Docker stack.

7. **Root `.env` absent in checkout**
   - Gap: compose refuses to start without it; README documents the copy step. Cosmetic `version:` attribute warning in compose.
   - Remediation: operator step; remove obsolete `version:` key on next edit.

8. **Observability of grounding decisions**
   - Verifier errors are log-warned but not metered; a silent continuous `llm_error` regression would not trip any dashboard.
   - Remediation: expose `lesson_grounding_*` counters (verdicts by method, llm_error rate, embedding fallback rate) in the existing metrics registry.

9. **No full browser E2E in this pass**
   - `backend/frontend/` is canonical and served at `/frontend`; UI-level flows (auth → lesson generation → player) were not driven in this pass.
   - Remediation: run the existing browser verification scripts (`backend/scripts/verify_*.py`) against a running stack.

## Tracked knowledge, not gaps

- Deterministic limitations (16) are intended behaviour with visible flags; closing them is the LLM verifier's job (P0 item 3).
- Python 3.11 local dev is a supported fallback; CI is authoritative for 3.13.
- Provider keys live in gitignored `backend/.env`; nothing in this report reproduces them.