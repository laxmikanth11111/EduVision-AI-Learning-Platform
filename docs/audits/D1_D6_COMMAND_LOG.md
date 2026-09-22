# D1–D6 Remediation — Command Log

All commands run from `backend/` (repo root `C:\Users\Admin\OneDrive\Desktop\EduVision AI — AI-Powered Interactive Learning Platform`), Windows PowerShell 5.1, Python 3.14.6 venv. Suites always run **serially** (shared SQLite under `%TEMP%\eduvision_testdb`).

## 1. Pre-remediation baseline (same state as the audit)

```
.\.venv\Scripts\python.exe -m pytest tests/unit --collect-only -q
→ 1373 tests collected in 8.93s

.\.venv\Scripts\python.exe -m pytest tests/unit --no-header -q --tb=short
→ 1373 passed, 1 warning in 186.51s (0:03:06)

.\.venv\Scripts\python.exe -m pytest tests/integration --no-header -q --tb=short
→ 204 passed in 151.82s (0:02:31)

.\.venv\Scripts\ruff.exe check app/
→ All checks passed!

.\.venv\Scripts\python.exe -m mypy app/ --ignore-missing-imports
→ Found 83 errors in 24 files (checked 333 source files)
```

## 2. Targeted new-test run (first attempt — before fixing 6 test-data issues)

```
.\.venv\Scripts\python.exe -m pytest tests/unit/test_grounding_enforcement.py tests/unit/test_gateway_injection_guard.py tests/unit/test_lesson_generation_service.py tests/unit/test_lesson_prompt_builder.py tests/unit/test_prompt_injection.py --no-header -q --tb=short
→ 6 failed, 101 passed in 33.47s
fails: TestC mixed payload (word "primarily" overlapped source); INJECTION_B/C not covered by scanner rules;
DiscoveredComponent missing fields; classifier/decision rule paths returned before the fake AI
→ fixes: re-crafted TestC claim; +4 scanner rules; full component fixtures; monkeypatched rule tables to force LLM path
```

## 3. Post-fix targeted runs + lint during the pass

```
.\.venv\Scripts\python.exe -m pytest tests/unit/test_grounding_enforcement.py tests/unit/test_gateway_injection_guard.py tests/unit/test_prompt_injection.py --no-header -q --tb=short
→ 44 passed in 18.47s

.\.venv\Scripts\ruff.exe check # app + the two new test files (+ all changed services)
→ Found 4 errors (4 fixed, 0 remaining)   (unused imports introduced mid-edit; auto-fixed)

.\.venv\Scripts\python.exe -m mypy app/ # after gateway work
→ Found 84 errors  (1 NEW error: `dict` missing type arg in AIInputSecurityError)
→ fixed to `dict[str, Any]`
```

## 4. Post-remediation full verification (serial)

```
.\.venv\Scripts\python.exe -m pytest tests/unit --no-header -q --tb=short
→ 1401 passed, 1 warning in 195.34s (0:03:15)      (baseline 1373 → +28 new tests)

.\.venv\Scripts\python.exe -m pytest tests/integration --no-header -q --tb=short
→ 204 passed in 127.59s (0:02:07)                  (identical pass set)

.\.venv\Scripts\ruff.exe check app/ tests/unit/test_grounding_enforcement.py tests/unit/test_gateway_injection_guard.py
→ All checks passed!

.\.venv\Scripts\python.exe -m mypy app/ --ignore-missing-imports
→ Found 83 errors in 24 files (checked 333 source files)   (exactly the baseline count; CI budget 86)

.\.venv\Scripts\python.exe -m pytest tests/unit/test_prompt_injection.py tests/unit/test_gateway_injection_guard.py tests/unit/test_grounding_enforcement.py --no-header -q --tb=short
→ 44 passed in 16.73s
```

## 5. Delta vs baseline

| Check | Baseline | Post-remediation | Delta |
|---|---|---|---|
| unit | 1373 passed | 1401 passed | +28 (19 gateway + 9 grounding) |
| integration | 204 passed | 204 passed | 0 |
| ruff | clean | clean | 0 |
| mypy (CI budget 86) | 83 | 83 | 0 |

## 6. Honesty checks performed

* No `tests/postgres`, `tests/e2e`, Docker, Redis, or live-provider command was
  run or claimed.
* No test was deleted or disabled; the two lesson-generation fixture edits
  changed test DATA (Intro/Body/Details/More → source-grounded topics) to comply
  with the now-enforced policy.
* `git status`/`git diff` reviewed before and during the pass; only the intended
  production/tests/docs files were modified by this remediation (the working
  tree also contains pre-existing uncommitted changes from earlier phases).