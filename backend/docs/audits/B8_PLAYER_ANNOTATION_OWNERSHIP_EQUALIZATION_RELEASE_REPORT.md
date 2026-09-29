# B8 — Player/Annotations Ownership-Response Equalization: Release Report

## 1. Summary

**Classification: A. Reachable cross-user information disclosure (existence/ownership oracle) + availability bug — FIXED.**

`GET/POST /api/v1/lessons/{id}/player`, `/checkpoint`, `/mastery`, and `GET/PUT .../annotations`
answered a **foreign** lesson with `403 "Access denied"` while a **missing** lesson answered
`404 "Lesson {id} not found"`. Any authenticated user could therefore enumerate lesson ids and learn
(1) whether a lesson exists and (2) that someone else owns it. `POST /player/advance` and
`POST /player/set-topic` additionally raised an uncaught `ValueError` → `500 INTERNAL_ERROR` for a
missing/foreign session.

Both cases now collapse to the single repo-wide not-found contract: **one code path** emitting
`404` / `error.code == "NOT_FOUND"` / `message == "Lesson {id} not found"`, identical for foreign and
missing lessons. Session mutations return the same 404 the `set_position` route already produced.

## 2. Baseline

- Branch: `feature/individual-user-foundation`
- Baseline commit: `8270a49 fix(security): reassert export ownership in worker`
- Fix commit: `2b3ebb0 fix(security): equalize player/annotations ownership responses to 404`

## 3. Fix

- `app/api/v1/player.py` — `get_player_state`, `start_player_session`, `get_checkpoint`,
  `get_mastery_and_next_action` now catch `(PermissionError, ValueError)` → single 404
  `f"Lesson {lesson_id} not found"`. `advance_topic`/`set_topic` catch `ValueError` → 404 (dead
  None-check removed).
- `app/api/v1/annotations.py::_owned_lesson` — same two-clause → equalized 404; docstring updated.
- The service layer still distinguishes `ValueError` (missing) from `PermissionError` (foreign); only
  the HTTP boundary equalizes them, preserving diagnostic signal internally.

## 4. Security Negotiation

- Foreign and missing responses are now phrase-identical, so probing a lesson id returns no information
  about existence or ownership.
- The 500s are gone — consistent with the "never 500, no resource-existence leak" convention used across
  B1-B7.
- Eight discriminators added in `tests/integration/test_player_annotation_ownership_security.py`; the
  previous 403-/500-encoding tests were converted to the equalized contract.

## 5. Verification

| Check | Result |
|---|---|
| Pre-fix (HEAD `8270a49`) | foreign lesson → 403; bogus-session advance/set-topic → 500 (code-verified) |
| Post-fix discriminator suite | **12 passed** (8 new + 4 reworked) |
| `tests/unit -q` | **1624 passed** |
| `tests/integration -q` | **269 passed** |
| `ruff check app tests` | **All checks passed** |
| Secret scan of diff | **Clean** |
| `git diff --check` | **Clean** |

## 6. Residual Risk

- Frontend already treats these endpoints generically (no 403 handling anywhere); verified by grep.
- Session id is server-generated; foreign sessions were already indistinguishable from missing via the
  `ValueError`/`None` arms and remain so.

## 7. Post-Release Cleanup

- Implementation report: `backend/docs/audits/B8_PLAYER_ANNOTATION_OWNERSHIP_EQUALIZATION_IMPLEMENTATION_REPORT.md` (committed).
- This release report is intentionally uncommitted, matching the B1-B7/F1 convention.
- Push: **NO**. PR: **NO**.