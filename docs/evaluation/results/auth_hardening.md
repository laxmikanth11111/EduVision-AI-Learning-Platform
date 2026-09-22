# Auth hardening — recorded result

Module: `app/api/v1/auth.py`
Config: `MAX_LOGIN_ATTEMPTS` (5), `LOGIN_LOCKOUT_MINUTES` (15),
`RATE_LIMIT_ROUTES` (`^/api/v1/auth/login$` and `^/api/v1/auth/register$` = 10/60).
Tests: `tests/unit/test_auth_hardening.py` (9 tests)

Command:

```
.venv\Scripts\python.exe -m pytest tests/unit/test_auth_hardening.py -q --no-header --tb=short
```

- Date: 2026-09-15
- **Result: 9 passed**

## Checks exercised

- Login failure counting keys `eduvision:auth:login_failures:<account>` (Redis
  first, in-memory fallback) with window `_lockout_window_seconds()`.
- After `MAX_LOGIN_ATTEMPTS` failures within the window, login returns **429**
  (locked) with `account_locked=true`, and the counter persists.
- Successful login clears the failure counter.
- `/auth/refresh` rotates the refresh token: the presented JTI is revoked in
  Redis (JTI-set) and a new access+refresh pair is issued.
- Replay of a revoked refresh token → **401**, logs
  `refresh_token_reuse_detected`, and the rotated pair stays valid.
- Works without Redis (in-memory fallback) so CI/local SQLite runs are green.

## Verified against the baseline debt item

- Baseline: "Login brute-force lockout config is dead — no enforcement anywhere."
- Now: enforced end-to-end and unit-tested. (Known doc note: `User` model still
  has no `login_attempts`/`locked_until` columns; enforcement is keyed at the
  auth layer on the account identifier, which is preferable to schema drift.)