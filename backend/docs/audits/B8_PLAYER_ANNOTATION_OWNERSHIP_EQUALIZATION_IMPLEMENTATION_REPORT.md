# B8 — Player/Annotations Ownership-Response Equalization: Implementation Report

## 1. Milestone Scope

| | |
|---|---|
| **ID** | B8 |
| **Issue type** | Cross-user resource oracle + availability bug — foreign lessons answered `403 Access denied` while missing lessons answered `404` (existence/ownership leak); `POST /lessons/{id}/player/advance` and `.../set-topic` let an uncaught `ValueError` escape as a 500 |
| **Affected routes** | `backend/app/api/v1/player.py` (all 7 routes) + `backend/app/api/v1/annotations.py` (`_owned_lesson` helper) |
| **Branch** | `feature/individual-user-foundation` |
| **Baseline commit** | `8270a49 fix(security): reassert export ownership in worker` (documented pre-fix behavior from code + failing tests) |
| **Fix commit** | (see final commit) |

## 2. Evidence and Finding

`LessonPlayerService._load_accessible_lesson`
(`backend/app/services/lesson_player_service.py` lines 59-74) distinguishes the two cases by
exception type:

- lesson row missing → `ValueError("Lesson {id} not found")`
- lesson exists but presentation owned by someone else → `PermissionError("You do not have access to
  this lesson")`

The player router (`player.py`) and the annotation helper (`annotations.py::_owned_lesson`) mapped
`PermissionError → 403 Access denied` and `ValueError → 404`, so probing a lesson id answered the
question "does this lesson exist, and is it someone else's?" — a **cross-user existence/ownership
oracle** for every read (state/start/checkpoint/mastery/annotations). Additionally:

- `advance_topic` and `set_topic` handlers contained a dead `if state is None: raise ValueError` branch
  while the service itself raises `ValueError("Session {id} not found")` for both missing AND foreign
  sessions — that uncaught `ValueError` bubbled out of the route → **500** (an availability error,
  inconsistent with the repo's "never 500, no resource-existence leak" convention).
- `set_position` already returned 404 for both missing and foreign sessions (service returns `None`);
  only its uncaught sibling routes were wrong.

Test suite mirrored the flaw: `test_e2e_pipeline::test_player_ownership_enforced` (assert 403 on GET
lessons/{id}/player), `test_p15_resume_api` (assert 403), `test_two_user_isolation` (assert 403),
`test_annotation_layers_api.py` (assert 403 and documented it), and
`tests/unit/test_annotation_routes.py` (`test_ownership_403`, `test_unauthorized_owner_403`).

**Pre-fix discriminator results** (inferred from HEAD code at `8270a49`, the pre-fix tests asserting
403/500 passing there): foreign lesson read → `403 error.forbidden` with `message "Access denied"`;
missing lesson → `404`; `POST /player/advance` + `/set-topic` with a bogus session_id → `500
INTERNAL_ERROR`. The new security suite written against these behaviors failed at HEAD (translated to
the fixed contract, all now pass).

## 3. Fix

### 3.1 Change

`backend/app/api/v1/player.py` — every route that loads a lesson now maps both access failures to the
single repo-wide not-found response:

```python
except (PermissionError, ValueError):
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Lesson {lesson_id} not found",
    )
```

Applied to `get_player_state`, `start_player_session`, `get_checkpoint`, `get_mastery_and_next_action`.
`advance_topic` and `set_topic` now wrap their service call:

```python
try:
    state = await service.advance_topic(request.session_id, owner_id=str(user.id))
except ValueError as e:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
```

(the dead `if state is None: raise ValueError` line removed; the service raises for missing and foreign
sessions alike, so the response stays equalized). `set_position` was already 404-on-None and is
unchanged.

`backend/app/api/v1/annotations.py::_owned_lesson` — same two-clause → single equalized 404 with the
standard `Lesson {id} not found` phrasing; module docstring updated.

### 3.2 Why the fix is complete and minimal

- **No existence/ownership oracle.** Foreign lessons are byte-identical in phrase to missing lessons
  (same status `404`, same `error.code == "NOT_FOUND"`, same `message` template) — the two branches now
  share one code path.
- **No more 500s.** The two session-mutation routes validate into a 404 instead of an unhandled server
  error, matching `set_position`.
- **Legit callers unaffected.** Owner reads/writes still succeed (200); session mutations still resolve
  the session as before.
- **Interface-shape preserved.** Response schema, error envelope, and status `404`
  (`code_map.get(404)` → `NOT_FOUND`) come from the existing exception middleware; no new framework.
- Frontend grep confirmed no client depends on 403 or "Access denied" for these endpoints, so changing
  the code cannot break the shipped UI.

## 4. Regression Tests

New file `backend/tests/integration/test_player_annotation_ownership_security.py` (8 tests, two-user JWT
harness mirroring `test_effectiveness_security.py`):

- unauthenticated `/player` → 401 (harness sanity)
- owner reads own player state → 200 (feature preserved)
- **non-owner `/player` state == missing-lesson response** (discriminator)
- **non-owner `/player/start` == missing-lesson response** (discriminator)
- **non-owner `/checkpoint` + `/mastery` == missing-lesson responses** (discriminator)
- **non-owner `/annotations` == missing-lesson response** (discriminator)
- **`POST /advance` with bogus session → 404, never 500** (discriminator)
- **`POST /set-topic` with bogus session → 404, never 500** (discriminator)

Updated existing tests that encoded the 403/500 behavior:

- `tests/unit/test_annotation_routes.py` — 403 cases → 404
- `tests/integration/test_annotation_layers_api.py` — non-owner test now also asserts the missing-lesson
  equality contract
- `tests/integration/test_e2e_pipeline.py::test_player_ownership_enforced` → 404
- `tests/integration/test_p15_resume_api.py` → 404 (+ comment)
- `tests/integration/test_two_user_isolation.py` → 404 (+ comments)

## 5. Verification

| Check | Result |
|---|---|
| Discriminator suite pre-fix (`8270a49`, inferred from HEAD code + tests asserting 403/500) | foreign=403 / bogus-session=500 |
| Discriminator suite post-fix | **12 passed** (8 new + 4 reworked annotation tests) |
| `uv run --project . pytest tests/unit -q` | **1624 passed** |
| `uv run --project . pytest tests/integration -q` | **269 passed** (261 prior + 8 new) |
| `uv run --project . ruff check app tests` | **All checks passed** |
| Secret scan of diff (sk-…, api-key, secret, password, private keys) | **Clean** |
| `git diff --check` | **Clean** before commit |

## 6. Related-Path Sweep

| Surface | Status |
|---|---|
| `GET /lessons/{id}/player` | **fixed (B8)** — equalized 404 |
| `POST /lessons/{id}/player/start` | **fixed (B8)** — equalized 404 |
| `GET /lessons/{id}/player/checkpoint`, `.../mastery` | **fixed (B8)** — equalized 404 |
| `POST /lessons/{id}/player/advance`, `.../set-topic` | **fixed (B8)** — caught ValueError → 404; session foreign/missing identical |
| `POST /lessons/{id}/player/position` | Already 404-on-None (unchanged) |
| `GET/PUT /lessons/{id}/annotations` via `_owned_lesson` | **fixed (B8)** — equalized 404 |
| `LessonPlayerService` exception vocabulary | Unchanged — ValueError (missing) vs PermissionError (foreign) still distinct at the service layer; equalization happens at the HTTP boundary |

No other player/annotation path showed a reachable ownership gap; no unrelated refactor was performed.

## 7. No Inventions / Scope Discipline

This milestone changes exactly the error mapping in `player.py` + `annotations.py::_owned_lesson`, adds
the eight security tests, reworks the affected ownership-assertion tests, and commits this report. No
P0/P1 ops/LLM gap items from `REMAINING_GAPS.md` were touched. The pre-existing untracked release
reports and `B5_SECURITY_OWNERSHIP_AUDIT_REPORT.md` were preserved untouched. All tests/checks pass;
exactly one atomic commit follows.

Final repository state: post-commit tracked tree clean; the untracked
`B8_PLAYER_ANNOTATION_OWNERSHIP_EQUALIZATION_RELEASE_REPORT.md` (plus the pre-existing reports) remains
uncommitted. Push: **NO**. PR: **NO**.