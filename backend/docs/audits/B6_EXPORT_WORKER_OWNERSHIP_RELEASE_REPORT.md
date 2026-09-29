# B6 — Export-Worker Ownership Re-Assertion: Release Report

## 1. Summary

**Classification: B. No currently reachable cross-user exploit; defense-in-depth hardening/documentation.**

B6 hardened the Celery export worker's content-construction boundary. The export job creation route
already enforces presentation ownership (`PresentationService.assert_ownership` before
`create_export_job`), and every reachable worker invocation uses a server-generated job public id from
that guarded route — so **no cross-user exploit is currently reachable through the API**. Read-only
audit found one latent defense-in-depth gap: `ExportService._build_export_content` resolved the target
presentation by public id / numeric id **with no `owner_id` predicate**. The worker now re-asserts
`Presentation.owner_id == job.user_id` on that lookup, so a foreign target resolves identically to a
missing target (generic fallback export) with no victim content and no existence/ownership oracle.

## 2. Baseline

- Branch: `feature/individual-user-foundation`
- Baseline commit: `8c0c3f2 fix(security): enforce per-user ownership boundary on runtime session state`
- Full export lifecycle traced end-to-end (route → job row → `export_generation_task` →
  `_export_generation_async` → `process_export_job` → `_build_export_content`) in the implementation report.

## 3. Reachability / Exploitability Evidence

| Invocation path | Result |
|---|---|
| `POST /api/v1/exports` | Guarded — `assert_ownership` before job creation; job `user_id` always the owner |
| Celery retry (max_retries=3) | Replays the same job row; owner unchanged |
| Task direct invocation / broker | Only reachable via `safe_dispatch` from the guarded route; job public id server-generated |
| `GET/DELETE /exports/{export_id}`, `GET /exports` | User-scoped status/cancel/list; never triggers processing |
| Admin/internal endpoints | None exist that enqueue or reprocess export jobs |

**Conclusion:** no reachable path can currently produce a job whose `target_id` is a presentation not
owned by `job.user_id`. The worker-side unscoped lookup was a latent gap (future job-creation path,
ownership transfer post-creation, or direct DB row manipulation), not a proven IDOR — hence
**classification B**.

## 4. Fix / Hardening

`backend/app/services/export_service.py` — single predicate added to the worker's presentation lookup:

```python
.where(where_clause, Presentation.owner_id == job.user_id)
```

- Minimal, no redesign; no schema/model/migration/router/API-shape change (`ExportJob.user_id` is
  already non-nullable).
- Matches the existing repo convention (`Presentation.owner_id == user_id` in
  `presentation_repository.py` L93/L131/L219).
- Foreign target → no row → existing generic fallback export (identical to missing-presentation
  semantics): no victim content, no oracle.

## 5. Tests

New `backend/tests/integration/test_export_worker_security.py` (6 worker ownership-hardening tests —
labeled as hardening evidence, not exploit reproduction, since no route can produce the mismatched rows):

- Owner export builds content; cross-user mismatch exports no victim content; cross-user == missing
  semantics; missing-presentation generic fallback; legitimate worker processing completes; retry/replay
  keeps the boundary.
- **Pre-fix (`8c0c3f2`): 3 failed** — cross-user/replay leaked victim content.
- **Post-fix: 6 passed.**

## 6. Verification

| Check | Result |
|---|---|
| New hardening suite | 6 passed (post-fix), 6 passed (post-commit) |
| Existing export tests (flow/api/service/worker-task) | 12 passed |
| `pytest tests/unit -q` | 1624 passed |
| `pytest tests/integration -q` | 256 passed (250 prior + 6 new) |
| `ruff check app tests` | All checks passed |
| Secret scan of staged diff + new test file | Clean |
| `git diff --check`, `git show --check HEAD` | Clean |

## 7. Commit

- `8270a49 fix(security): reassert export ownership in worker` (ONE atomic commit)
- Files: `backend/app/services/export_service.py` (5+/1−),
  `backend/docs/audits/B6_EXPORT_WORKER_OWNERSHIP_IMPLEMENTATION_REPORT.md`,
  `backend/tests/integration/test_export_worker_security.py`

## 8. Limitations / Deferred

- Worker lookup is re-asserted at content construction; job load itself remains the repo-standard
  unscoped `get_by_public_id` (only reachable with server-generated ids today — consistent with the
  worker-context convention). Deferred as in B5 audit (I.4), not B6 scope.
- Presentational/folder path validation (B5 audit I.1), simulation owner caller-conditional (I.3) remain
  deferred — not B6 scope.
- This is defensive hardening; it does not imply a previously-exploited IDOR existed.

## 9. Repository State

- Post-commit tracked tree clean. Commit chain: `8c0c3f2 → 8270a49`.
- Untracked release/audit reports preserved untouched: B1, B2, B3, B4, B5-release,
  B5-audit, F1-release, NEXT_MILESTONE-release, and this `B6_EXPORT_WORKER_OWNERSHIP_RELEASE_REPORT.md`.
- Push: **NO**. PR: **NO**.