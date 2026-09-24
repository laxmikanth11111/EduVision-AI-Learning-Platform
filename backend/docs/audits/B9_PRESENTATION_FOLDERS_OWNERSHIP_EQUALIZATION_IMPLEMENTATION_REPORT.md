# B9 — Presentation Folder Ownership-Response Equalization: Implementation Report

## 1. Milestone Scope

| | |
|---|---|
| **ID** | B9 |
| **Issue type** | Cross-user resource oracle + availability bugs — foreign folders answered `403 Forbidden "You do not have access to this folder"` while missing folders answered `404 "Folder not found"` (an existence/ownership oracle on update/delete/breadcrumbs); the create/update parent path leaked a *different* message for foreign parent (`Folder not found`) vs missing parent (`Parent folder not found`); and every folder mutation attempted to write an audit row into the presentation-scoped `presentation_audit_logs` table (`presentation_id=folder.id`, FK → `presentations.id`) → guaranteed `IntegrityError` → **500** in any FK-enforcing database; `PATCH /folders/{id}` additionally 500'd with `MissingGreenlet` serializing post-flush expired ORM columns |
| **Affected services** | `backend/app/services/presentation_folder_service.py` |
| **Branch** | `feature/individual-user-foundation` |
| **Baseline commit** | `2b3ebb0 fix(security): equalize player/annotations ownership responses to 404` (documented pre-fix behavior from code + failing tests) |
| **Fix commit** | (see final commit) |

## 2. Evidence and Finding

`PresentationFolderService._assert_folder_owner`
(`backend/app/services/presentation_folder_service.py`) raised
`PermissionDeniedError("You do not have access to this folder")` for a folder owned by someone else,
while the missing-folder branches raised `NotFoundError(message="Folder not found")`. The API
(`backend/app/api/v1/presentation_folders.py`) therefore answered the question "does this folder
exist, and is it owned by someone else?" — a **cross-user existence/ownership oracle** on:

- `GET /folders/{id}/breadcrumbs` (missing → `404 "Folder not found"`, foreign → `403`)
- `PATCH /folders/{id}` (same split)
- `DELETE /folders/{id}` (same split)
- `POST /folders` and `PATCH /folders/{id}` **parent** checks — foreign parent → `404 "Folder not found"`,
  missing parent → `404 "Parent folder not found"`: the two 404s were distinguishable, so the oracle
  also survived in the create/move path.

Standing up the API-level probe for the above immediately exposed two further genuine availability
bugs in the same code path (previously unreachable by tests because the folder feature had no API
tests — unit tests mock the audit service):

1. **Guaranteed 500 on every folder mutation.** `create_folder`/`update_folder`/`delete_folder`
   called `PresentationAuditService.log(folder.id, …)` with
   `presentation_id=folder.id`, but `presentation_audit_logs.presentation_id` is `NOT NULL`
   and FK-references `presentations.id` (`backend/app/models/presentation_audit_log.py`, confirmed in
   migration `0001_initial.py:164-172`). A folder id is not a presentation row → `sqlite3.IntegrityError:
   FOREIGN KEY constraint failed` in the FK-enforcing test DB, and an equivalent PostgreSQL
   `FK violation` in production → **every create/patch/delete on a folder 500'd**.
2. **`PATCH /folders/{id}` 500 via `MissingGreenlet`.** `update_folder` flushed the loaded ORM
   instance and returned it; the route then serialized `created_at`/`updated_at`, which SQLAlchemy had
   expired on flush, and the expired-attribute reload escaped the greenlet context → 500.

Pre-fix discriminator results: foreign folder update/delete/breadcrumbs → `403
error.forbidden`; create under foreign parent → `404 "Folder not found"` (+ `403` for the
foreign-folder variant at HEAD, which the parent check hit first for create); missing → `404 "Folder
not found"` / `404 "Parent folder not found"`; root folder create → `500 INTERNAL_ERROR` (FK), update
→ `500` (FK or MissingGreenlet). The new security suite written against these behaviors failed at
HEAD (translated to the fixed contract, all now pass).

## 3. Fix

### 3.1 Change

`backend/app/services/presentation_folder_service.py`:

- `_assert_folder_owner` (update/delete/breadcrumbs) now raises
  `NotFoundError(message="Folder not found")` — foreign folder byte-identical to missing folder.
- The **parent** checks in `create_folder` and `update_folder` became a single equalized branch:
  `parent is None or parent.owner_id != owner_id → NotFoundError(message="Parent folder not found")`,
  so a foreign parent is indistinguishable from a missing parent in that context.
- **Removed the presentation-scoped audit writes** (FOLDER_CREATED / FOLDER_UPDATED / FOLDER_DELETED
  into `presentation_audit_logs`) and replaced them with `logger.info` records. The audit table is
  presentation-scoped (FK to `presentations.id`, NOT NULL); folder events cannot be represented there,
  and the attempt 500'd every mutation. No migration was introduced: this milestone restores folder
  operations without schema churn; the `PresentationAuditService` dependency and the now-unused
  `<self>._audit_service` attribute were dropped (`shared/constants.PresentationAction` no longer
  imported by this service). Presentation mutations still audit as before.
- `update_folder` now re-fetches the folder after `flush` and returns the fresh instance, eliminating
  the expired-attribute reload that raised `MissingGreenlet` at route serialization.

### 3.2 Why the fix is complete and minimal

- **No existence/ownership oracle.** Foreign and missing folders produce the same status/code/message
  within each operation context (`Folder not found` for the folder itself, `Parent folder not found`
  for the parent checks) — one shared code path per context.
- **No more 500s on folder mutations.** The FK-failing audit write is gone (operational logging
  retained), and PATCH serializes a freshly reloaded instance.
- **Legit callers unaffected.** Owner create/breadcrumbs/update/delete still succeed (201/200/204);
  sibling-name conflicts still return the real `409`, and self-parent/cycle moves still return `409`.
- **Interface-shape preserved.** Response schema, error envelope, and `404`
  (`code_map.get(404)` → `NOT_FOUND`) come from the existing exception middleware; no new framework.
- Frontend grep confirmed no client depends on 403 or "You do not have access" for `/folders`, so
  changing the code cannot break the shipped UI.

## 4. Regression Tests

New file `backend/tests/integration/test_presentation_folders_security.py` (5 tests, two-user JWT
harness mirroring the B7/B8 suites; `_assert_equalized_folder_not_found` compares status/`NOT_FOUND`/
message, message parameterized for the `Parent folder not found` context):

- owner create/breadcrumbs/update/create-child → success (feature preserved)
- **B's `PATCH` of A's folder == missing-folder 404** (discriminator)
- **B's `DELETE` of A's folder == missing-folder 404** (discriminator)
- **B's breadcrumbs read of A's folder == missing-folder 404** (discriminator)
- **create under A's folder as B == create under missing parent** (discriminator, `Parent folder not found`)

These tests failed at HEAD with the FK 500 (root create) and the 403/message mismatch; all pass now.

Updated `backend/tests/unit/test_presentation_folder_service.py`:

- foreign-update/delete/breadcrumbs cases → `NotFoundError, match="Folder not found"`
- foreign-parent create case → `NotFoundError, match="Parent folder not found"`
- removed the two audit-insert assertions (create/delete) that encoded the broken behavior and the
  now-nonexistent `_audit_service` mock; fixture simplified accordingly.

## 5. Verification

| Check | Result |
|---|---|
| Discriminator suite pre-fix (HEAD `2b3ebb0`) | foreign=403 + message mismatch + FK 500 — 5/5 failed |
| Discriminator suite post-fix | **20 passed** (5 new integration + 15 unit) |
| `uv run --project . pytest tests/unit -q` | **1624 passed** |
| `uv run --project . pytest tests/integration -q` | **274 passed** (269 prior + 5 new) |
| `uv run --project . ruff check app tests` | **All checks passed** |
| Secret scan of diff (sk-…, api-key, secret, password, private keys) | **Clean** |
| `git diff --check` | **Clean** before commit |

## 6. Related-Path Sweep

| Surface | Status |
|---|---|
| `POST /folders` (root / under parent) | **fixed (B9)** — equalized `Parent folder not found`; FK-500 eliminated |
| `GET /folders/{id}/breadcrumbs` | **fixed (B9)** — equalized 404 `Folder not found` |
| `PATCH /folders/{id}` | **fixed (B9)** — equalized 404 + fresh post-flush reload (MissingGreenlet gone) |
| `DELETE /folders/{id}` | **fixed (B9)** — equalized 404; FK-500 eliminated |
| Folder audit writes | Removed (presentation-scoped table cannot hold folder events); `logger.info` retained |
| `PresentationAuditService` / presentation mutations | Unchanged — presentations still audit through the same table |

No other folder path showed a reachable ownership gap; no unrelated refactor was performed.

## 7. No Inventions / Scope Discipline

This milestone changes exactly the ownership/error handling in `presentation_folder_service.py`, adds
the five security tests, reworks the affected folder-service ownership-assertion tests, and commits
this report. The audit-FK 500 and the PATCH `MissingGreenlet` were fixed because they sit directly on
the B9 probe path (the deferred "folder 500" item) and block exercising the equalization contract; no
schema migration or unrelated refactor was introduced. No P0/P1 ops/LLM gap items from
`REMAINING_GAPS.md` were touched. The pre-existing untracked release reports and
`B5_SECURITY_OWNERSHIP_AUDIT_REPORT.md` were preserved untouched. All tests/checks pass; exactly one
atomic commit follows.

Final repository state: post-commit tracked tree clean; the untracked
`B9_PRESENTATION_FOLDERS_OWNERSHIP_EQUALIZATION_RELEASE_REPORT.md` (plus the pre-existing reports)
remains uncommitted. Push: **NO**. PR: **NO**.