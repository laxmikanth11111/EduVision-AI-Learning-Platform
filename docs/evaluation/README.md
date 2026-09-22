# Evaluation

How EduVision AI is evaluated beyond unit/integration tests: correctness of the
hardened trust boundaries (prompt-injection defense, grounded safety, RAG
provenance, auth hardening) and reproducibility of the demo for the key
surfaces.

## Contents

- `results/` — recorded outcomes of each evaluation method that could be run in
  this environment. Each result file lists the exact command(s), the date, the
  outcome, and any deviation from CI.
- `data/` — small fixture artifacts used by evaluations (sample documents /
  generated traces), kept small and free of secrets.

## Result summary (2026-09-15)

| Area | Method | Outcome | Artifact |
| ---- | ------ | ------- | -------- |
| Unit tests incl. new hardening | `pytest tests/unit` | **1373 passed** | `results/unit_suite.md` |
| Integration tests | `pytest tests/integration` | **204 passed** | `results/integration_suite.md` |
| Lint | `ruff check app tests scripts --no-fix` | all checks passed | `results/static_analysis.md` |
| Type gate | `mypy app` | 83 errors ≤ budget 86 | `results/static_analysis.md` |
| Prompt-injection scanner | 16 targeted tests | all pass | `results/prompt_injection.md` |
| Grounded safety validator | targeted tests in `test_lesson_prompt_builder/test_lesson_generation_service` | all pass | `results/grounded_validator.md` |
| Auth hardening (lockout + rotation) | `test_auth_hardening.py` | all pass | `results/auth_hardening.md` |
| RAG provenance trace | `test_retrieval_provenance.py` + generated trace | all pass | `results/rag_provenance.md` |

## Not evaluated locally (blocked environment)

- **PostgreSQL-backed suite** (`pytest tests/postgres -m postgres`) — requires
  Docker / testcontainers, unavailable on this machine. CI runs it.
- **End-to-end Playwright suite** (`pytest tests/e2e -m e2e`) — requires a
  running server and a browser. CI runs `docker-build`; e2e is a documented
  follow-up.
- **Docker compose boot** — `docker --version` does not return on this machine;
  `docker-compose.yml` is reviewed but not runtime-verified here.
- **Live provider keys** — Gemini/OpenAI keys are out of quota / not committed;
  all evaluation used the deterministic local mock provider.