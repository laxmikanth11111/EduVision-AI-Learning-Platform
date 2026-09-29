# FINAL — Security & Ownership Audit of the EduVision AI Backend

**Branch:** `feature/individual-user-foundation`
**Generated:** program end state, after B1–B9 fix commits
**Method:** ownership map → boundary sweep → classification → per-issue fix with discriminating
(non-owner vs missing) regression coverage → full-suite verification → atomic commit per issue.
**Scope covered:** every authenticated cross-user resource path reachable by id from an HTTP route
plus the internal worker/queue appendages, and the previously flagged residual surfaces.

---

## 1. Executive Summary

Nine cross-user ownership/response-parity defects were found, fixed, and committed (B1–B9). Each fix
was proven by a discriminating test suite written to fail against the pre-fix behavior and pass after,
and validated with the full unit + integration suites plus `ruff`.

The remaining audit surface (worker tasks that take ids, the simulation engine, the canvas
integration, and the repository layer's unscoped methods) was re-verified at the end-state and is
**closed by design, clean, or a false-positive** — no reachable cross-user path remains. Four
low-severity hardening observations are recorded as recommended follow-ups (section 7); none is
exploitable from the HTTP boundary today.

**Tracked tree is clean; nothing was pushed; no PR was opened.** The pre-existing untracked release
reports and `B5_SECURITY_OWNERSHIP_AUDIT_REPORT.md` were preserved untouched.

---

## 2. Fixed Findings (B1–B9)

Each row: finding → fix (commit) → proof.

| # | Finding | Fix (commit) | Discriminating proof |
|---|---|---|---|
| **B1** | Quiz-generation IDOR: `POST /quizzes/{presentation_id}/generate` generated another user's presentation quiz (raw `presentation_id` from body, insufficient ownership check) | Ownership/route hardening (`a34b5d3`) | New two-user JWT suite: B generating A's quiz → no data returned / blocked; A's own flow still works |
| **B2** | AI-assistant lesson-context IDOR: RAG/generation fetch of lessons by raw id without presentation ownership | Ownership asserted on lesson context paths (`7d9c092`) | Non-owner probe ≈ missing path; owner path preserved |
| **B3** | Effectiveness-assessment IDOR: assessment reads/writes by assessment id without owner filter | Owner-scoped resolve + create with `user_id` (`36d3d04`) | B reading/finishing A's assessment → owner-equivalent response; A unaffected |
| **B4** | Tutor-retention ownership: retention data fetched without binding to the calling learner | Retention queries scoped to `user_id` (`3ea948f`) | B requesting A's retention → empty/404-equal; A's data unchanged |
| **B5** | Runtime-session ownership: resume/state endpoints resolved sessions without owner binding | Uniform session ownership + 404-equalization (`8c0c3f2`) | B probing A's session == missing-session 404 |
| **B6** | Export worker: `export_generation_task` fetched jobs/records without owner re-assertion (queue-borne public id) | Worker re-asserts ownership inside `process_export_job` (`8270a49`) | Worker trigger with cross-user id → job/index filtered to `job.user_id`; storage keys stay user-scoped |
| **B7** | Effectiveness comparison: `compare_groups` aggregated across ALL users' assessments (cross-user leak) | Keyword-only `user_id`, both SELECTs filtered by `user_id` (`cf18846`) | B's comparison of A's group showed A's counts pre-fix (3 failed / 2 passed at HEAD); post-fix `group_b_count == 0` for A's data under B |
| **B8** | Player/annotations oracle + 500s: foreign lessons answered `403 Access denied`, missing lessons `404` (existence/ownership oracle); `advance`/`set-topic` 500'd on unknown session | All lesson reads map `(PermissionError, ValueError)` → uniform `404 Lesson {id} not found`; advance/set-topic catch `ValueError` → 404 (`2b3ebb0`) | 8-test two-user suite: non-owner player/start/checkpoint/mastery/annotations == missing-lesson response; bogus-session advance/set-topic → 404 never 500 |
| **B9** | Presentation-folder oracle + 500s: foreign folders answered `403 You do not have access to this folder`, missing folders `404 Folder not found`; foreign parent `Folder not found` vs missing parent `Parent folder not found`; every folder mutation 500'd (audit FK `presentation_id=folder.id` → `presentation_audit_logs.presentation_id` FK to `presentations.id`); `PATCH` 500'd (`MissingGreenlet` post-flush expired columns) | `_assert_folder_owner` → `404 Folder not found`; parent checks equalized to `Parent folder not found`; folder audit writes removed (presentation-scoped table cannot hold folder events; `logger.info` retained); post-flush re-fetch in `update_folder` (`4f8eff3`) | 5-test two-user suite: B's patch/delete/breadcrumbs of A's folder == missing-folder 404; create under A's folder as B == create under missing parent; owner ops still succeed |

**Commit chain:** `998ebe1` → `a34b5d3` (B1) → `7d9c092` (B2) → `36d3d04` (B3) → `3ea948f` (B4) →
`8c0c3f2` (B5) → `8270a49` (B6) → `cf18846` (B7) → `2b3ebb0` (B8) → `4f8eff3` (B9).

---

## 3. Residual Surface — Verified Closed (end-state, with evidence)

### 3.1 Worker tasks that take an object id — CLOSED-BY-DESIGN + DEFENSE-IN-DEPTH
Id-taking Celery tasks (`video_render_task` `workers/video_tasks.py:42`,
`c3_generate_visuals_task` `c3_visual_tasks.py:58`, `c4_generate_animations_task` `c4_animation_tasks.py:60`,
`export_generation_task`/`process_export_job` `export_service.py:153`, `process_source_ingestion_task`
`presentation_service.py:718`, `lesson_generation_task` `presentation_service.py:899`,
`rag_indexing_task` `tasks.py:392`) receive ids **only from the broker**, never from HTTP params.
Every route-level dispatch point is owner-verified first (`c3_visual_router.py:74`,
`c4_animation_router.py:75/235`, `exports.py:54`, `presentations.py:495/519/537/584-593`,
`presentation_folders.py:98`). c3/c4 workers additionally self-check `owner_id != user_id → abort`
(on a second fetch; `c3_visual_tasks.py:109`). Beat schedule (`celery_app.py:79-116`) carries no
user-input ids. Residual worker reads that are unscoped are internal-only fetches (e.g.
`rag_indexing_service.py:99/168` threads the embedding job with the verified `presentation.owner_id`).

### 3.2 Simulation engine — CLEAN (pre-hardened, in-memory)
`simulation_engine_service.py`: definitions are static registry keys (`simulation_registry_service.py`),
not owned resources; sessions are random in-memory ids; every mutator funnels through
`get_session_state` → `_assert_owner` (uniform 404 for unknown *or* foreign, `simulation_engine_service.py:32-37`);
all 8 routes bind `owner_id=str(user.id)`. No persistence ⇒ no cross-user storage path.

### 3.3 Integrations / canvas — FALSE-POSITIVE / CLEAN
There is **no LTI/LMS integration code**; the only "canvas" surface is the personal Visual Knowledge
Graph canvas API (`api/v1/visual_canvases.py`). `_assert_canvas_owner` (38-54) applies a strict owner 404
on every resolver (get/update/delete/nodes/edges/components/relationships/quiz-blueprint); creation and
listing are user-scoped. The earlier "canvas ownership issue" report is a **false positive**.

### 3.4 Unscoped repository methods — CLEAN (no reachable unscoped path)
Swept all `backend/app/repositories/`. Every unscoped `get_by_public_id`/list is either shadowed by a
user-scoped twin actually used by services (`export_job_repository`, `export_file_repository`,
`review_schedule_repository`, `study_plan_repository`, `learning_goal_repository`,
`learning_path_repository`), worker-only (`presentation_repository.get_by_public_id`), dead code
(`concept_repository.get_by_public_id`, `concept_service.get_concept` — zero callers), or guarded
call-side (`presentation_folder_repository.find_all` under `_assert_folder_owner`;
`generated_lesson_repository.get_by_public_id` under the player's owner check). The known-clean
surfaces (analytics, progress, study plan, video_projects, storage, exports, metrics) were confirmed
user-scoped at the service layer.

---

## 4. Verification Summary (final state)

| Check | Result |
|---|---|
| `uv run --project . pytest tests/unit -q` | **1624 passed** |
| `uv run --project . pytest tests/integration -q` | **274 passed** (incl. 5 new B9, 8 new B8, 5 new B7, plus B1–B6 suites) |
| `uv run --project . ruff check app tests` | **All checks passed** |
| Secret scan of each fix diff (`sk-…`, api-key, secret, password, private keys) | **Clean** |
| `git diff --check` per commit | **Clean** |
| Repo state post-B9 | tracked tree clean; untracked release reports + `B5_SECURITY_OWNERSHIP_AUDIT_REPORT.md` preserved |

---

## 5. Contract Adopted Across the API Boundary

- Foreign and missing resources are byte-equivalent at the HTTP layer within each operation context
  (same `404` status, same `error.code == "NOT_FOUND"`, same message template) — no resource
  existence/ownership oracle.
- Never `403`/`500` for mere access/validation cases; service-layer exception vocabulary may still
  distinguish (e.g. `ValueError` vs `PermissionError`) as long as the boundary equalizes.
- All authenticated routes pass `owner_id=str(user.id)` / `user.id` into the service layer as the
  single source of truth for ownership.
- Existing error envelope (`{"success": false, "error": {code, message, details, request_id}}`)
  retained; equality-test helpers compare `status/code/message` (request_id varies per call).

---

## 6. Scope Discipline / No Inventions

Fixes were confined to the offending routes/services + their regression suites + implementation
reports; no unrelated refactors, no schema migrations, no framework swaps, no dependency changes.
Pre-existing untracked artifacts were left untouched. One deviation is noted explicitly: B9 removed
the broken folder audit writes to the presentation-scoped audit table (restoring folder mutations that
were guaranteed 500s) — documented in the B9 implementation report.

---

## 7. Recommended Follow-ups (not exploitable today — LOW / defense-in-depth)

1. **Dead unscoped repo methods** — `review_schedule_repository.get_by_public_id`,
   `study_plan_repository.get_by_public_id`, `learning_goal_repository.get_by_public_id`,
   `learning_path_repository.get_by_public_id`, `concept_repository.get_by_public_id`,
   `concept_service.get_concept` have no service callers; a future HTTP route wired to them would
   reintroduce an IDOR footgun. Recommend removal or an explicit `# internal-only` guard.
2. **`presentation_repository.search(is_admin=True)` escape hatch** — drops the owner filter; no caller
   passes `True` today, but it is undocumented in the public signature. Recommend deleting or gating it.
3. **c3/c4 worker fetch-then-bail error shape** — workers fetch unscoped then answer `"Not owner"` on
   mismatch rather than a uniform 404; not reachable from HTTP (queue-borne ids). Recommend a shared
   worker-level `get_owned` helper mirroring `video_tasks.py:27`.
4. **Export worker trust model** — `process_export_job` derives ownership from the job row (created
   under route-level `assert_ownership`); a forged broker message would still only reach that job's
   owner's presentations. Already B6-hardened; keep the job-row ownership invariant tested.

---

## 8. Handoff

- **Fixed and merged (tracked):** B1–B9, one atomic commit each
  (`998ebe1` → `a34b5d3` → `7d9c092` → `36d3d04` → `3ea948f` → `8c0c3f2` → `8270a49` → `cf18846` →
  `2b3ebb0` → `4f8eff3`), HEAD = `4f8eff3`.
- **Not committed (by design, pre-existing):** release reports B1–B9, `F1_LEARNING_MODE_COMPLETION_RELEASE_REPORT.md`,
  `NEXT_MILESTONE_RELEASE_REPORT.md`, `B5_SECURITY_OWNERSHIP_AUDIT_REPORT.md`.
- **No reachable cross-user finding remains.** Remaining work is the LOW/defense-in-depth follow-ups in §7
  and the unrelated declared ops/LLM gaps in `REMAINING_GAPS.md` (out of this audit's scope).
- **Push: NO. PR: NO. History rewrite: NO.**