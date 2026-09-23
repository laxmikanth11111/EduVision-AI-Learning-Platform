# B6 — Export-Worker Ownership Re-Assertion: Implementation Report

## 1. Milestone Scope

| | |
|---|---|
| **ID** | B6 |
| **Issue type** | Defense-in-depth authorization hardening (worker-side target ownership re-assertion; no currently reachable cross-user exploit) |
| **Affected service** | `backend/app/services/export_service.py` |
| **Affected flow** | `ExportService.process_export_job` → `ExportService._build_export_content` (Celery `eduvision.exports.generate` worker consumption of an export job) |
| **Branch** | `feature/individual-user-foundation` |
| **Baseline commit** | `8c0c3f2 fix(security): enforce per-user ownership boundary on runtime session state` |
| **Fix commit** | (see final commit) |

## 2. Evidence and Finding

This is the B5-deferred candidate from `B5_SECURITY_OWNERSHIP_AUDIT_REPORT.md`.
Read-only audit trace established the full export job lifecycle:

- `POST /api/v1/exports` (`exports.py`) calls `PresentationService.assert_ownership(request.target_id, owner_id=user.id)`
  **before** persisting any job, so `export_job.user_id` always equals the owning user at creation, then
  `ExportService.create_export_job(user_id=user.id, target_id=request.target_id)` and
  `dispatch_export_job(job.public_id)`.
- Dispatch uses `safe_dispatch(export_generation_task, job.public_id)` with a server-generated
  `expjob_<hex>` public id (never caller-supplied).
- The worker (`export_generation_task` → `_export_generation_async` → `process_export_job`) loads the job
  with the **unscoped** `get_by_public_id`, then calls `_build_export_content(job)`.
- `_build_export_content` resolved the target presentation with
  `select(Presentation).where(where_clause)` where `where_clause` is
  `or_(Presentation.public_id == target_id, Presentation.id == target_uuid)` — **no `owner_id` predicate**.

**Reachability assessment — Case A (no currently reachable cross-user bypass):**

| Possible invocation path | Ownership result |
|---|---|
| Normal authenticated flow (`POST /exports`) | Guarded — presentation ownership asserted before job creation; job user always the owner |
| Celery retry (task `max_retries=3`) | Retries the same job public id; row owner unchanged |
| Celery task direct invocation | Only reachable via `safe_dispatch` from the guarded create route; job public id is server-generated |
| `GET /exports/{export_id}`, `GET /exports`, `DELETE /exports/{export_id}` | User-scoped via `get_user_job_by_public_id`; status/cancel only, never trigger processing |
| Admin/internal endpoints | None exist that enqueue or reprocess export jobs |
| Direct service call from another user request | No route reaches `process_export_job`; only `export_generation_task` inside the worker |

Conclusion: no reachable path can currently produce an `export_job` whose `target_id` is a presentation not
owned by `job.user_id`. The unscoped worker lookup is therefore **not a proven IDOR**; it is a latent,
defense-in-depth gap (a future job-creation path, an ownership transfer between job creation and worker
consumption, or any direct DB row manipulation would export arbitrary presentation content).

**Discriminating pre-fix run** (worker boundary constructed directly, bypassing the guarded route — labeled
as hardening evidence, not an exploit reproduction):

```
6 run in 16.90s: 3 failed, 3 passed
  test_cross_user_job_presentation_mismatch_exported_no_victim_content     FAILED
      ExportContentData(title='Victim Quantum Deck', ... 'QUBIT_SECRET_CONTENT_MARKER' ...)
  test_cross_user_mismatch_matches_missing_presentation_semantics          FAILED
      foreign target resolved to victim content instead of the missing-presentation form
  test_retry_replay_keeps_ownership_boundary                               FAILED
      replay still leaked victim content
```

All three failures show the worker exporting the victim presentation title and unit text when
`job.user_id != presentation.owner_id`.

## 3. Fix

### 3.1 Change

Single, minimal edit in `ExportService._build_export_content`
(`backend/app/services/export_service.py`):

```python
stmt_pres = (
    select(Presentation)
    .where(where_clause, Presentation.owner_id == job.user_id)
    .options(selectinload(Presentation.content_units))
)
```

The presentation lookup now carries the ownership predicate `Presentation.owner_id == job.user_id`,
matching the same convention already used across the repository
(`presentation_repository.py` L93/L131/L219 use `Presentation.owner_id == user_id` /
`== owner_id`).

### 3.2 Why the fix is complete and minimal

- **Equalized fallback, no oracle.** When the predicate fails (foreign target), the lookup returns no row
  and `_build_export_content` falls through to its existing generic fallback
  `ExportContentData(title=f"EduVision Export — {kind.capitalize()}", ...)` — the identical semantics
  already used for a missing presentation. Foreign targets are therefore indistinguishable from missing
  targets, exactly like the route-level 404-equalization convention across B1–B5. A cross-user job still
  completes with a generic stub (no victim content), preserving "no victim content is exported".
- **Single call site.** A grep over `app/` confirms `_build_export_content` is the only presentation
  lookup in the export path; `process_export_job` is the only caller of `_build_export_content`, and
  `export_generation_task` is the only caller of `process_export_job`.
- **No schema, model, migration, router, or API response-shape change.** `ExportJob.user_id` is already a
  non-nullable UUID, so the predicate is always well-defined. The owner job lifecycle is unchanged.
- No new authorization framework; extends the repo's `owner_id` predicate convention.

## 4. Regression Tests

New file `backend/tests/integration/test_export_worker_security.py` (6 tests, built on the shared
`db_session` fixture + `ExportService(UnitOfWork(session=db_session))`, mirroring
`test_export_flow.py`). Labeled **worker ownership-hardening tests, not exploit reproductions** — they
construct mismatched job rows directly because no reachable route can produce them today:

- **Owner export builds content** — A-owned job + A-owned presentation → real (non-generic) content with
  the presentation title/units.
- **Cross-user job/presentation mismatch → no victim content** — `job.user_id=B` +
  `presentation.owner_id=A` → `_build_export_content` must NOT build victim content (discriminator).
- **Cross-user mismatch equals missing-presentation semantics** — foreign target produces the same generic
  fallback as a missing target (no existence/ownership oracle).
- **Missing presentation keeps generic fallback** — existing semantics preserved.
- **Legitimate worker processing completes** — A-owned job + presentation through `process_export_job` →
  status `completed`, `progressPercentage == 100`, `downloadUrl` present.
- **Retry/replay keeps the boundary** — re-invoking `_build_export_content` and `process_export_job` never
  surfaces victim content and completes without error.

All **3** discriminating tests failed against vulnerable HEAD (`8c0c3f2`) and all **6** pass after the fix.
The `export_generation_task` worker wrapper itself is covered unchanged by the existing
`tests/unit/test_export_worker_task.py` (retry semantics verified separately).

## 5. Verification

| Check | Result |
|---|---|
| Pre-fix run of new hardening suite (vulnerable HEAD) | **3 failed, 3 passed** — cross-user/replay leaked victim content |
| Post-fix run of new hardening suite | **6 passed** |
| Existing export tests (`test_export_flow.py`, `test_export_api.py`, `test_export_service.py`, `test_export_worker_task.py`) | **12 passed** (no regression, incl. the route-level `test_create_export_job_requires_ownership`) |
| `uv run --project . pytest tests/unit -q` | **1624 passed** |
| `uv run --project . pytest tests/integration -q` | **256 passed** (250 prior + 6 new) |
| `uv run --project . ruff check app tests` | **All checks passed** |
| Secret scan of diff + new test file (sk-…, api-key, secret, password, private keys) | **Clean** |
| `git diff --check` | **Clean** before commit |

## 6. Related-Path Sweep

| Surface | Status |
|---|---|
| `POST /api/v1/exports` (create) | Already guarded — `assert_ownership` before job creation (unchanged) |
| `GET/DELETE /api/v1/exports/{export_id}` (status/cancel) | Already user-scoped via `get_user_job_by_public_id` (unchanged) |
| `GET /api/v1/exports` (list) | Already user-scoped via `list_jobs(user_id=...)` (unchanged) |
| `export_generation_task` / `_export_generation_async` (worker) | Calls `process_export_job` with server-generated job id; ownership now re-asserted on content construction (B6) |
| `process_export_job` (job load, retry, progress) | Retries the same job row; no new target reconciliation surfaces (unchanged) |
| `_build_export_content` (presentation lookup) | **fixed (B6)** — `Presentation.owner_id == job.user_id` predicate |
| `export_file_repository` / storage writes (`exports/user_{job.user_id.hex}/...`) | Already keyed under `job.user_id` (unchanged) |
| Deferred items I.1–I.4 minus the export candidate (folder-validation 500/403-oracle, simulation owner caller-conditional, unscoped `get_by_public_id`) | remain deferred — not B6 scope |

No other export-related path showed a reachable ownership gap; no unrelated refactor was performed.

## 7. No Inventions / Scope Discipline

This milestone changes exactly one minimal predicate inside `ExportService._build_export_content`, adds the
six worker-hardening tests, and commits this report. No P0/P1 ops/LLM gap items from `REMAINING_GAPS.md`
were touched. The pre-existing untracked release reports (B1–B5, F1, `NEXT_MILESTONE_RELEASE_REPORT.md`)
and the untracked `B5_SECURITY_OWNERSHIP_AUDIT_REPORT.md` were preserved untouched. All tests/checks pass;
exactly one atomic commit follows.

Final repository state: post-commit tracked tree clean; the untracked
`B6_EXPORT_WORKER_OWNERSHIP_RELEASE_REPORT.md` (plus the pre-existing reports) remains uncommitted.
Push: **NO**. PR: **NO**.