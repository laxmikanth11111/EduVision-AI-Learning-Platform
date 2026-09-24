# B7 — Effectiveness Comparison Owner-Scoping: Implementation Report

## 1. Milestone Scope

| | |
|---|---|
| **ID** | B7 |
| **Issue type** | Reachable cross-user aggregate disclosure (broken-scoped read) — any authenticated user could read all users' effectiveness aggregates via a guessed/free-form `experiment_group` label |
| **Affected service** | `backend/app/services/effectiveness_service.py` (`compare_groups`) + `backend/app/api/v1/effectiveness.py` (`GET /api/v1/effectiveness/comparison`) |
| **Branch** | `feature/individual-user-foundation` |
| **Baseline commit** | `8270a49 fix(security): reassert export ownership in worker` |
| **Fix commit** | (see final commit) |

## 2. Evidence and Finding

`compare_groups` (pre-fix, lines 361-423) filtered the `EffectivenessAssessment` table **only** on the
`experiment_group` label:

```python
stmt_a = select(EffectivenessAssessment).where(
    EffectivenessAssessment.experiment_group == group_a,
)
stmt_b = select(EffectivenessAssessment).where(
    EffectivenessAssessment.experiment_group == group_b,
)
```

No `user_id` predicate and no caller identity were involved. The route (`effectiveness.py`, decorator at
line 331, handler at 336) injected `get_current_user` but did **not** pass the user into the service —
only `group_a`/`group_b` query parameters. Because `experiment_group` is a free-form string a user sets
themselves (`app/schemas/effectiveness.py` lines 54/77/95) with no enumerable set, any authenticated user
could probe a group label and read cross-user aggregate counts, completion counts, and averages
(baseline/post/absolute/normalized gain, retention fields, learning time).

Evidence of cross-user intent in the pre-fix test suite:

- `tests/unit/test_p2_effectiveness.py::TestGroupComparison::test_compare_groups_service` deliberately
  built `other_user`'s assessment in group `eduvision` and asserted it appeared in the caller's aggregate
  (`group_b_count == 1`, `group_b_avg_absolute_gain == 50.0`).
- `tests/integration/test_p2_effectiveness_e2e.py` Step 11 asserted a single comparison aggregated both
  User A's and User B's per-user group data (`group_a_count == 1` **and** `group_b_count == 1`).
- The same service's `export_study_data` was already user-scoped (filters `user_id` at lines 482-484) —
  an internal inconsistency left by B3, which never covered the comparison endpoint (report scope was the
  assessment start/submission flow and `user_summary`).

Frontend audit: the comparison endpoint has no frontend caller
(`grep /effectiveness/comparison backend/frontend` → none), so the fix alters no UI contract.

**Discriminating pre-fix run** (new API-level suite, see §4) — 3 failed / 2 passed at `8270a49`:

```
tests/integration/test_effectiveness_comparison_security.py
  test_cross_user_comparison_never_includes_victim_group     FAILED
      B querying A's group 'secretgrp' returned group_a_count == 3 (victim aggregate leaked)
  test_foreign_group_indistinguishable_from_nonexistent      FAILED
      victim group response differed from nonexistent-group response
  test_service_level_call_is_user_scoped                     FAILED
      TypeError: compare_groups() got an unexpected keyword argument 'user_id'
```

## 3. Fix

### 3.1 Change

Two minimal edits:

1. `EffectivenessService.compare_groups` now takes a required keyword-only `user_id: uuid.UUID` and both
   selects gain the ownership predicate:
   ```python
   stmt_a = select(EffectivenessAssessment).where(
       EffectivenessAssessment.experiment_group == group_a,
       EffectivenessAssessment.user_id == user_id,
   )
   ```
   (same added to `stmt_b`). This matches the repo convention used by `get_owned_presentation`
   (lines 24-46) and `export_study_data`.

2. The route threads the authenticated caller into the service:
   ```python
   result = await service.compare_groups(
       user_id=user.id,
       group_a=group_a,
       group_b=group_b,
   )
   ```

### 3.2 Why the fix is complete and minimal

- **Owner still sees own data.** A caller's own assessments remain aggregated by `experiment_group`
  (self-study comparison across their own presentations), so the owner-facing feature is preserved.
- **No existence/ownership oracle.** A foreign group and a never-existing group both produce
  `count == 0` with `None` averages — identical responses (verified by
  `test_foreign_group_indistinguishable_from_nonexistent`), reusing the 404-equality convention from
  B1-B5. The endpoint still returns 200 with empty aggregates on purpose (aggregation is by definition
  empty-safe); it no longer reveals anyone else's data.
- **Single call site.** A grep over `app/` confirms the route is the only `compare_groups` caller.
- **No schema, model, migration, or response-shape change.** `Assessment.user_id` is non-nullable, so the
  predicate is always well-defined; `GroupComparisonResponse` is unchanged.
- **Defense-in-depth preserved for future callers**: the parameter is required keyword-only, so any future
  caller must consciously supply a user identity.

## 4. Regression Tests

New file `backend/tests/integration/test_effectiveness_comparison_security.py` (5 tests, built on the
shared two-user JWT harness mirroring `test_effectiveness_security.py`):

- **Unauthenticated comparison rejected** — 401 without a token.
- **Owner sees own group data** — A resolves their own `experiment_group` (count/average correct); other
  group empty.
- **Cross-user comparison never includes victim group (discriminator)** — B queries A's group → `count ==
  0`, all averages `None`, `completed == 0`.
- **Foreign group indistinguishable from nonexistent** — B's response for A's real group is byte-identical
  (metrics-wise) to a nonexistent group's response; no oracle.
- **Service-level call is user-scoped** — same guarantee at the service boundary with `user_id` threaded
  explicitly.

Pre-fix: 3 failed / 2 passed (see §2). Post-fix: **5 passed**. The pre-fix "leak-encoding" tests in
`test_p2_effectiveness.py`, `test_p2_validation.py`, and `test_p2_effectiveness_e2e.py` were converted
into owner-scoped aggregation tests rather than deleted (the math tests remain meaningful when the caller
owns all seeded assessments).

## 5. Verification

| Check | Result |
|---|---|
| Pre-fix run of new security suite (vulnerable HEAD) | **3 failed, 2 passed** — victim aggregate leaked |
| Post-fix run of new security suite | **5 passed** |
| `uv run --project . pytest tests/unit -q` | **1624 passed** (unchanged total; tests updated in place) |
| `uv run --project . pytest tests/integration -q` | **261 passed** (256 prior + 5 new) |
| `uv run --project . ruff check app tests` | **All checks passed** |
| Secret scan of diff + new test file (sk-…, api-key, secret, password, private keys) | **Clean** |
| `git diff --check` | **Clean** before commit |

## 6. Related-Path Sweep

| Surface | Status |
|---|---|
| `GET /effectiveness/comparison` | **fixed (B7)** — caller-scoped aggregation |
| `EffectivenessService.compare_groups` | **fixed (B7)** — required `user_id` + ownership predicate |
| `user_summary`, `export_study_data`, assessment start/submit/score/retention flows | Already user-scoped (B3 era); unchanged |
| `EffectivenessAssessment.experiment_group` population | No change — groups remain a per-user self-label |
| Other `compare_groups` callers | None in `app/`; route is the only caller |

No other effectiveness surface showed a reachable ownership gap; no unrelated refactor was performed.

## 7. No Inventions / Scope Discipline

This milestone changes exactly one service method signature + one route call site, adds the five
security tests, converts the leak-encoding tests to owner-scoped equivalents, and commits this report. No
P0/P1 ops/LLM gap items from `REMAINING_GAPS.md` were touched. The pre-existing untracked release reports
(B1-B6, F1, `NEXT_MILESTONE_RELEASE_REPORT.md`) and the untracked `B5_SECURITY_OWNERSHIP_AUDIT_REPORT.md`
were preserved untouched. All tests/checks pass; exactly one atomic commit follows.

Final repository state: post-commit tracked tree clean; the untracked
`B7_EFFECTIVENESS_COMPARISON_SCOPING_RELEASE_REPORT.md` (plus the pre-existing reports) remains
uncommitted. Push: **NO**. PR: **NO**.