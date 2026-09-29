# B9 — presentation-folder ownership-response equalization — Release report

## Change
- `backend/app/services/presentation_folder_service.py`
  - `_assert_folder_owner` now raises `NotFoundError("Folder not found")` instead of
    `PermissionDeniedError("You do not have access to this folder")` — a foreign folder is now
    byte-identical to a missing folder (`404` / `NOT_FOUND` / `Folder not found`).
  - create/update parent checks collapsed to one equalized branch: foreign parent and missing parent
    both → `404 / NOT_FOUND / "Parent folder not found"`.
  - Removed the presentation-scoped audit writes (`presentation_audit_logs`), which passed
    `presentation_id=folder.id` against an FK to `presentations.id` → every folder create/update/delete
    was a guaranteed `IntegrityError` **500** in any FK-enforcing DB. Replaced with `logger.info`
    records. `PresentationAuditService` dependency dropped.
  - `update_folder` re-fetches after flush and returns the fresh instance — fixes a `MissingGreenlet`
    500 when PATCH serialized post-flush expired ORM columns.
- New `backend/tests/integration/test_presentation_folders_security.py` (5 two-user JWT tests):
  owner ops succeed; B's patch/delete/breadcrumbs of A's folder == missing-folder 404; create under
  A's folder as B == create under missing parent.
- `backend/tests/unit/test_presentation_folder_service.py`: foreign folder/parent cases now assert the
  equalized `NotFoundError` messages; broken audit-insert assertions removed.

## Verification
- Folder suite: **20 passed** (15 unit + 5 integration).
- Full suites: **unit 1624 passed; integration 274 passed** (269 prior + 5 new).
- `ruff check app tests`: clean. Secret scan: clean. `git diff --check`: clean.
- Discriminator, pre-fix (HEAD `2b3ebb0`): foreign=403 + message mismatch + FK **500** — 5/5 failed.

## Commit
- `4f8eff3 fix(security): equalize presentation folder ownership responses to 404`
- Push: **NO**. PR: **NO**. This report intentionally left uncommitted.