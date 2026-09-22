# INDEPENDENT VERIFICATION BASELINE

Date: 2026-09-15
Auditor: OpenCode (independent forensic pass)
Status: Baseline established

## Repository State

- **Branch**: `feature/individual-user-foundation`
- **HEAD commit**: `d873d99855de1116f8aa70ecdf3e39dcad7ef49a`
- **Commit message**: "feat(eduvision): close C3 visual intelligence pipeline"
- **Commit date**: 2026-09-07 17:51:37 +0530
- **Working tree**: Contains prior-pass modifications (M: retrieval.py, auth.py, config.py, main.py, lesson_safety.py, mastery_tutor_service.py, etc.; ?? untracked: prompt_injection.py, C4 animation set, root README.md). These are uncommitted changes from the prior engineering pass.
- **test.db files**: Present at repo root and `backend/` (SQLite, not committed to git)

## Environment

- **OS**: Windows 10/11 (win32)
- **Shell**: PowerShell 5.1
- **Python**: 3.14.6 (in `backend/.venv`; CI pins 3.13)
- **Invocation pattern**: `cmd /c "cd /d backend && .venv\Scripts\python.exe -m pytest ..."` (from repo root); do NOT combine `workdir=backend` with `cd /d backend` inside the command.
- **Ruff**: available (`app/tests/scripts --no-fix`)
- **MyPy**: available; CI gate counts `error:` lines against budget 86

## Previous Claims Under Review

1. "1,373 unit tests pass" (prior engineering-pass final verification)
2. "204 integration tests pass" (same)
3. "Ruff: all checks passed" (same)
4. "MyPy: 83 errors (budget 86)" (same)
5. "Semantic vector retrieval with cosine similarity" (final readiness report, prompt-injection evaluation)
6. "Grounded validator performs source grounding" (final readiness report, grounded validator evaluation)
7. "Prompt-injection scanner covers all relevant AI entry points" (prompt-injection evaluation doc, lines 42-49)
8. "Frontend is the canonical backend/frontend/ with real API calls" (frontend evaluation)
9. "Auth hardening: lockout, refresh rotation, rate limiting all wired into production routes" (auth hardening evaluation)

## Commands Executed

| Command | Result |
|---------|--------|
| `git log -1 --format="%H %ci %s"` | d873d99... 2026-09-07 17:51:37 |
| `git status --porcelain` | M: 19 files, ?? 23+ entries |
| `python --version` (venv) | Python 3.14.6 |
| `pytest tests/unit --collect-only -q` | 1373 collected |
| `pytest tests/unit --no-header -q --tb=short` | 1373 passed (185.95s) |
| `pytest tests/integration --no-header -q --tb=short` | 204 passed (157.07s) |
| `ruff check app tests scripts --no-fix` | All checks passed |
| `mypy app 2>&1 \| Select-String 'error:'` | 83 errors |
| `alembic heads --verbose` | Single head: 0036_c4_topic_animation_assets |
| RAG runtime test (3 docs, production `semantic_retrieve_chunks_with_meta`) | All 3 queries correct ranking |
| `prompt_injection.py` entry-point audit | 3/10 LLM call sites covered |

## Environmental Limitations

- Docker/PostgreSQL unavailable locally (tests/postgres blocked; integration tests run on SQLite)
- Playwright/e2e tests not runnable (no browser)
- Live AI keys not configured (AI_PROVIDER=local in conftest, LOCAL_EMBEDDING_MODE=deterministic)
- `ripgrep` (rg) not installed locally (CI-only on ubuntu runner)
- PowerShell `python -c` with nested quotes via `cmd /c` unreliable — use temp scripts for standalone audits

## Key Files Examined

- `backend/app/ai/retrieval.py` — cosine_similarity, semantic_retrieve_chunks_with_meta, _ranked_pairs
- `backend/app/repositories/rag_repository.py:231` — list_embedded_pairs_for_content_units
- `backend/app/models/chunk_embedding.py` — vector JSON/JSONB nullable
- `backend/app/services/lesson_safety.py` — GroundedLessonSafetyValidator
- `backend/app/services/mastery_tutor_service.py:490-530` — injection scan
- `backend/app/services/learning_assistant_service.py:628-660` — _generate_response (no scan)
- `backend/app/services/quiz_generation_service.py:191-209` — _call_ai (no scan)
- `backend/app/services/visual_classifier_service.py:167-195` — LLM fallback (no scan)
- `backend/app/ai/prompt_injection.py` — scanner, is_reliably_flagged
- `backend/app/core/config.py:146,163-167,250-253` — defaults, dead config
- `backend/tests/conftest.py` — session SQLite, autouse auth override
- `backend/tests/unit/test_prompt_injection.py` — 16 tests
- `backend/tests/unit/test_mastery_tutor_semantic_rag.py` — semantic ranking tests
- `backend/tests/unit/test_rag_semantic_retrieval.py` — cosine ranking tests
- `backend/tests/unit/test_auth_hardening.py` — lockout + refresh rotation tests
- `backend/app/services/lesson_prompt_builder.py` — prompt structure
- `backend/app/services/quiz_generation_service.py` — uncovered injection path
- `.github/workflows/ci.yml` — mypy gate (budget 86), ruff, alembic checks
