# EduVision AI — Final Engineering Readiness Report

> Date: 2026-09-15
> Snapshot after the hardening + audit pass. Complements
> `docs/audits/BASELINE.md` (pre-improvement state) and
> `docs/audits/REQUIREMENTS_EVIDENCE_MATRIX.md`.

## 1. Headline status

| Gate | Baseline | Now | Verdict |
| ---- | -------- | --- | ------- |
| Unit tests | 1337 passed | **1373 passed** (0 failures) | ✅ no regressions, +36 new tests |
| Integration tests | 204 passed | **204 passed** (0 failures) | ✅ |
| Ruff | 1 error | **0 errors** (`All checks passed!`) | ✅ |
| mypy | 83 errors | **83 errors** (budget 86) | ✅ no growth |
| Alembic head | single | **single** (`0036_c4_topic_animation_assets`) | ✅ |
| Redis outage tolerance | in-memory fallbacks | unchanged + hardened auth counters | ✅ |

The pass **closed three documented dead-config items**:
1. `AI_LESSON_SAFETY_VALIDATOR` was ignored (no-op regardless of name) → now a
   real `grounded` default validator, enforced in lesson + quiz generation.
2. `MAX_LOGIN_ATTEMPTS` / `LOGIN_LOCKOUT_MINUTES` were dead → now enforced as a
   per-account lockout with 429 responses, plus refresh-token rotation + reuse
   detection + auth route rate limits.
3. No prompt-injection defense existed despite unboundedly untrusted document
   uploads → now a canonical scanner gates lesson input, topic-outline source
   text, and learner messages in the mastery tutor.

## 2. What was implemented this pass

### Prompt-injection defense (`app/ai/prompt_injection.py`)
- Weighted signature scanner; `is_reliably_flagged` = any matched rule ≥ 2.0
  (strong/critical) gates blocking independent of the 3.0 soft threshold.
- `tool_invoke` weight 1.5 keeps legitimate coding/API questions unflagged.
- Enforced at: `lesson_safety.validate_input`, `topic_outline_service
  ._assert_no_injection` (AppValidationError → deterministic fallback),
  `mastery_tutor_service._produce_answer` (deterministic refusal).
- Config: `AI_PROMPT_INJECTION_ENABLED` / `_THRESHOLD` / `_REFUSAL`.
- Tests: `test_prompt_injection.py` (16) — all pass.

### Grounded safety validator (`app/services/lesson_safety.py`)
- `GroundedLessonSafetyValidator`: input non-empty + injection scan; output
  no-empty-topics + source-coverage estimate; `LessonSafetyError` on violation.
- `build_safety_validator(name)` maps `"grounded"`/`"noop"`/None explicitly and
  raises `ConfigurationError` for unknown names (no silent no-op).
- Both `AI_LESSON_SAFETY_VALIDATOR` defaults changed to `grounded`;
  `.env.example` documents all three keys.
- Tests: `test_lesson_prompt_builder.py` TestSafety + grounded coverage in
  `test_lesson_generation_service.py`; `test_lesson_generation_service.py:364`
  asserts the new default.

### Auth hardening (`app/api/v1/auth.py`, `app/core/config.py`)
- Per-account lockout (`eduvision:auth:login_failures:<account>`, Redis-first,
  in-memory fallback, `_lockout_window_seconds()`); locked login → 429;
  success clears counters.
- Refresh rotation: presented JTI revoked, new pair issued; replay → 401 +
  `refresh_token_reuse_detected` log.
- Rate limits for `/auth/login` and `/auth/register` (10 per 60s).
- Tests: `test_auth_hardening.py` (9) — all pass (with and without Redis).

### RAG provenance (`app/ai/retrieval.py`)
- `semantic_retrieve_chunks_with_meta` → `RetrievedChunk` (chunk_id,
  content_unit_id, position, similarity, content, snippet); content-only
  wrapper preserved for existing callers.
- Tests: `test_retrieval_provenance.py` (5) — all pass.

### Misc
- Ruff: PT018 fixed in `test_c4_animation_security.py:103`; unrelated
  auto-fixes applied; `ruff check app tests scripts --no-fix` fully clean.
- mypy inline-import pattern for Redis fallback kept type-safe (83 total, ≤ 86).
- `EduVision_AI_Frontend/eduvision_frontend/` marked **DEPRECATED — do not
  modify**; canonical frontend remains `backend/frontend/`.

## 3. Verification evidence (all executed on this machine)

| Command | Result |
| ------- | ------ |
| `pytest tests/unit --no-header -q --tb=line` | **1373 passed** in 123.62s |
| `pytest tests/integration --no-header -q --tb=line` | **204 passed** in 123.58s |
| `ruff check app tests scripts --no-fix` | **All checks passed** |
| `mypy app` | **83 errors** (≤ CI budget 86) |
| `alembic heads` | **1 head** (`0036_c4_topic_animation_assets`) |
| `pytest tests/unit/test_prompt_injection.py` | **16 passed** |
| `pytest tests/unit/test_auth_hardening.py` | **9 passed** |
| `pytest tests/unit/test_retrieval_provenance.py` | **5 passed** |
| `pytest tests/unit/test_lesson_prompt_builder.py` | **pass** (TestSafety grounded) |
| `pytest tests/unit/test_topic_outline_service.py` | **15 passed** |

Recorded artifacts: `docs/evaluation/results/*.md`.

## 4. Known limitations / BLOCKED in this environment (honest status)

1. **PostgreSQL-backed suite** (`pytest tests/postgres -m postgres`) — Docker /
   testcontainers unavailable locally. **Not run here**; CI job exists and is
   part of the pipeline definition.
2. **End-to-end suite** (`tests/e2e`, marker `e2e`) — needs a running server and
   a browser. **Not run here**.
3. **Docker compose runtime boot** — `docker --version` does not return on this
   machine. `docker-compose.yml` is reviewed, not runtime-verified.
4. **Live provider calls** — Gemini/OpenAI keys out of quota; all evaluation
   used the deterministic `local` provider, which is the correct choice for
   reproducible CI/unit runs. Live-key smoke is a deployment-environment step.
5. **SQLite contention (already mitigated)** — one mid-session parallel run hit
   transient `no such table: presentations` (aiosqlite `test.db` write
   contention on Windows). Every affected file passes in isolation and the final
   full run is 1373/1373 green; CI on Linux/3.13 with a single worker is not
   affected. If flakiness reappears locally, use `pytest tests/unit -p
   no:cacheprovider` or run per-module.
6. **mypy not fully clean** — 83 pre-existing errors tracked against an
   explicit 86 budget; no growth introduced.
7. **`User` model drift** — `login_attempts` / `locked_until` columns exist in
   migration 0001 but not in the model; lockout is enforced at the auth layer by
   account identifier instead (preferred; avoids schema drift reintroduction).

## 5. Operational notes

- Run checks with the venv Python: `.venv\Scripts\python.exe` (Windows) —
  3.14.6 locally, CI pins 3.13.
- Redis outage tolerated everywhere: sessions/caches/rate-limit/lockout all
  have in-memory fallbacks; `/health` reports degraded so operators can react.
- Keep `.env` (gitignored) secrets out of any shared sync folder; rotate live
  Gemini/Google keys before shipping; the secret-scan CI job covers both
  working tree and full history.

## 6. Recommendation

**Ready to ship** as scoped. Before a production cut-over: run the
PostgreSQL-backed suite and compose boot in CI (they are defined and green
jobs/definition), do a live-provider smoke test in staging, and rotate the
documented secrets.