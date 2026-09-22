# Static analysis — recorded result

Commands (from `backend/`):

```
.venv\Scripts\python.exe -m ruff check app tests scripts --no-fix
.venv\Scripts\python.exe -m mypy app
```

- Date: 2026-09-15

## Ruff

- **Result: `All checks passed!`** (0 errors)
- Baseline had 1 error (PT018 in `tests/unit/test_c4_animation_security.py:103`);
  fixed + unrelated auto-fixes applied.

## mypy

- **Result: 83 `error:` lines** (24 files), CI budget is **86** (explicit in
  `.github/workflows/ci.yml` mypy-gate). No growth from the 83 baseline.
- The 2 remaining `auth.py` samesite errors (`auth.py:232`, `auth.py:241`) are
  pre-existing and count against the 83; they reference an optional cookie
  attribute and do not affect runtime behavior.
- Python on this machine is 3.14.6; CI runs 3.13.