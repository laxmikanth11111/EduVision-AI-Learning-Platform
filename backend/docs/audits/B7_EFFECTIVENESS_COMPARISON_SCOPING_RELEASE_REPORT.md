# B7 — Effectiveness Comparison Owner-Scoping: Release Report

## 1. Summary

**Classification: A. Provable, reachable cross-user data disclosure — FIXED by owner-scoping.**

`GET /api/v1/effectiveness/comparison` aggregated `EffectivenessAssessment` rows across **all** users
filtering only on the free-form `experiment_group` label (a string any user sets themselves). Any
authenticated user could probe group labels and read other learners' aggregate counts, completion counts,
and averages (baseline/post/absolute/normalized gain, retention fields). The only parameters were
`group_a`/`group_b`; the route resolved the authenticated user but never passed them into the service.

Discriminating pre-fix run (new API-level suite at vulnerable HEAD `8270a49`): User B querying User A's
experiment group received the victim's aggregates (`group_a_count == 3`, non-`None` averages) — 3 of the
5 new tests failed on the leak. Post-fix, B's query returns `count == 0` / `None` averages, byte-identical
to a never-existing group (no existence/ownership oracle).

## 2. Baseline

- Branch: `feature/individual-user-foundation`
- Baseline commit: `8270a49 fix(security): reassert export ownership in worker`
- Fix commit: `cf18846 fix(security): scope effectiveness comparison to the calling user`

## 3. Fix

1. `EffectivenessService.compare_groups` now requires a keyword-only `user_id` and both group selects gain
   `EffectivenessAssessment.user_id == user_id`. The predicate is always well-defined (`user_id`
   non-nullable), matches the repo convention (`get_owned_presentation`, `export_study_data`, and
   `presentation_repository`), and makes future callers consciously supply an identity.
2. The route threads `user.id` into the service.

The owner's own self-study comparison is preserved: a caller still aggregates their **own** assessments
tagged with different `experiment_group` labels, so a single user's reference-vs-eduvision evaluation keeps
working. Frontend has no caller for this endpoint, so no UI contract changed.

## 4. Security Negotiation

The leak-encoding tests were converted to owner-scoped tests rather than deleted, so aggregation-math
coverage survives:

- `tests/unit/test_p2_effectiveness.py::TestGroupComparison`
- `tests/unit/test_p2_validation.py` (`TestNoStatisticalClaims`, `TestComparisonFramework`,
  `TestBoundaryBetweenSoftwareAndLearning`)
- `tests/integration/test_p2_effectiveness_e2e.py` Step 11 (now documents caller scoping)

## 5. Verification

| Check | Result |
|---|---|
| Pre-fix security suite (HEAD) | **3 failed, 2 passed** — victim aggregate leaked |
| Post-fix security suite | **5 passed** |
| `tests/unit -q` | **1624 passed** |
| `tests/integration -q` | **261 passed** |
| `ruff check app tests` | **All checks passed** |
| Secret scan of diff | **Clean** |
| `git diff --check` | **Clean** |

## 6. Residual Risk

- If a future product feature requires a genuine researcher/administrator multi-user A/B comparison, it
  must be re-designed with an explicit role gate and aggregated-only response; the current endpoint is
  per-caller by contract.
- `experiment_group` remains a per-user free-form label; two users may coincidentally share a label, but
  each sees only their own aggregates.

## 7. Post-Release Cleanup

- Implementation report: `backend/docs/audits/B7_EFFECTIVENESS_COMPARISON_SCOPING_IMPLEMENTATION_REPORT.md` (committed).
- This release report is intentionally uncommitted, matching the B1-B6/F1 convention.
- Push: **NO**. PR: **NO**.