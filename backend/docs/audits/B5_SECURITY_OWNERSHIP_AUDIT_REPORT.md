# B5 — Security / Ownership Boundary Audit Report

**Milestone:** B5 (audit-only — no fix implemented)
**Date of audit:** 2026-09-23
**Author:** senior security / release engineer (opencode session)

---

## A. Baseline

| Item | Value |
| --- | --- |
| Branch | `feature/individual-user-foundation` |
| HEAD | `3ea948f5ac6d8aa35ad46889c3d286dca474ad8b` |
| HEAD message | `fix(security): enforce per-user ownership boundary on tutor retention sweep` |
| Parent | `36d3d04` (`fix(effectiveness): enforce presentation ownership boundary on assessments and report`) |
| Tracked working tree | clean (`git status --short` shows only untracked release reports) |
| Untracked release reports (preserved, untouched) | `B1_QUIZ_GENERATION_IDOR_RELEASE_REPORT.md`, `B2_AI_ASSISTANT_LESSON_CONTEXT_IDOR_RELEASE_REPORT.md`, `B3_EFFECTIVENESS_ASSESSMENT_IDOR_RELEASE_REPORT.md`, `B4_TUTOR_RETENTION_OWNERSHIP_RELEASE_REPORT.md`, `F1_LEARNING_MODE_COMPLETION_RELEASE_REPORT.md`, `NEXT_MILESTONE_RELEASE_REPORT.md` |

Previous security milestones considered (historical context, not re-opened):

* B1 — quiz-generation lesson ownership IDOR (`backend/app/api/v1/quiz.py` assert_quiz_ownership)
* B2 — AI assistant lesson-context ownership IDOR (`assistant.py` session/conversation anchors)
* B3 — effectiveness assessment/report ownership boundary
* B4 — tutor retention global cross-user destructive sweep (`mastery_tutor_service.enforce_retention`)
* F1 — learning-mode completion semantics
* Annotation-durability milestones

**Repository safety state at conclusion:** `git diff --check` clean; `git status --short` lists only the six pre-existing untracked release reports plus the new B5 audit report. No tracked source file was modified.

---

## B. Audit scope

Read-only sweep of authenticated paths across:

```
backend/app/api/
backend/app/services/
backend/app/repositories/
backend/app/models/
backend/app/schemas/
```

Coverage was split across two explorer passes plus direct verification reads:

1. **Pass 1 — exports / storage / progress / review / analytics / goals / plan / path / simulation**
   Routers: `exports.py`, `storage` uploads, `learner_progress`, `analytics`, `goals`, `plan`, `path`, `simulation.py`, dashboards/reports.
2. **Pass 2 — player / notes / annotations / visual canvases / animation / video / quiz / quiz-attempt paths**
   Routers: `player.py`, `annotations`, `visual_canvases.py`, `animation_runtime_router.py`, `animation_planner`, `video_runtime_router.py`, `video_projects`, `quiz.py`, quiz-attempt service/repository.
3. **Direct verification (this author)**
   `presentations.py`, `presentation_service.py`, `presentation_folder_service.py`, `exports.py`, `export_service.py`, `video_runtime_router.py`, `animation_runtime_router.py`, `visual_canvases.py`, `bounded_cache.py`, `learning_context_service.py`, plus the B4 two-user test harness and the B5 temporary proof test.

Trace pattern applied to every authenticated route: `route → service → repository/query → model ownership field → read/mutate`, with special attention to queries that fetch a row by identifier WITHOUT an ownership predicate (`get_by_public_id`, `select(Model).where(... id == ...)`).

---

## C. Ownership matrix

| Surface (route/service) | Ownership enforced? | Cross-user tested? | Mutation risk? | Status |
| --- | --- | --- | --- | --- |
| Exports create (`POST /exports`) | Yes — `assert_ownership(request.target_id, user.id)` at route | Not cross-user tested (owner path only) | Low (creation guard) | SAFE |
| Export status/cancel/list (`GET/GET/DELETE /exports/{id}`) | Yes — user-scoped repos (`get_user_job_by_public_id`) | B1–B4 style suite exists | Low | SAFE |
| Export worker (`export_service.process_export_job` / `_build_export_content`) | Route guards creation; worker trusts job row (no re-check) | Not tested | Latent — see I.1 | DEFER |
| Learner progress / analytics / goals / plan / path | Yes — user-scoped repo methods | Not independently re-tested | Low | SAFE |
| Simulation sessions (`/simulations/sessions/*`) | Yes — routes pass `owner_id`; engine enforces | Existing two-user isolation test (L555–695) | Low — owner check caller-conditional | SAFE (note I.3) |
| Player (`GET/POST /lessons/{lesson_id}/player`, advance/set-topic) | Yes — lesson ownership / session owner | Existing suites | Low | SAFE |
| Annotations / notes | Yes — user-scoped | Existing | Low | SAFE |
| Visual canvases (`/visual/canvases*`) | Yes — `_assert_canvas_owner` (404-equalized, incl. NULL owner) | Existing | Low | SAFE |
| Quiz routes (`quiz.py`) | Yes — `assert_quiz_ownership` (L70/L90/L138) | B1 suite | Low | SAFE |
| Quiz attempts (`quiz_attempt_service`) | Yes — user-scoped attempts | Existing | Low | SAFE |
| Tutor/assistant session+message | Yes — B4 user-scoped retention; B2 context anchors | B2/B4 suites | Low | SAFE |
| Folder CRUD (`/folders`) | Yes — `_assert_folder_owner` (raises 403 vs 404 — see I.2) | Not equalized-tested | Low; 403 oracle only | DEFER |
| Presentations create w/ folder | **Broken call** — `validate_folder_ownership` undefined → 500 on folder_id (fails closed) | n/a | Availability only | DEFER (I.2) |
| **Video runtime writes** (`POST /videos/runtime/sync`, `/bookmark`, `/assessment`) | **NO write-side ownership check** | **B5 proof (this report)** | **HIGH — cross-user state clobbering** | **SELECTED** |
| **Animation runtime writes** (`POST /animations/runtime/sync`) | **NO write-side ownership check** | **B5 proof (this report)** | **HIGH — cross-user state clobbering** | **SELECTED (related path)** |
| Video/animation runtime reads (`GET /state`, `/tutor-context`) | Yes — `state.user_id == str(user.id)` → `data:null` otherwise | N/A (guarded) | Low | SAFE |
| Metrics (`GET /metrics`) | No auth (deliberate scrape surface, no PII) | N/A | N/A | SAFE (documented) |

---

## D. Selected B5 finding

**Title:** Cross-user runtime state clobbering via unverified `session_id` writes (interactive video & animation runtime sync).

* **Route(s):**
  * `POST /api/v1/videos/runtime/sync` (`video_runtime_router.py:72-118`)
  * `POST /api/v1/videos/runtime/bookmark` (`video_runtime_router.py:135-157`)
  * `POST /api/v1/videos/runtime/assessment` (`video_runtime_router.py:160-184`)
  * `POST /api/v1/animations/runtime/sync` (`animation_runtime_router.py:38-84`) — identical pattern on the related path.
* **HTTP methods:** `POST`
* **Affected services / modules:** `app.api.v1.video_runtime_router`, `app.api.v1.animation_runtime_router`, `app.utils.bounded_cache.BoundedCache`
* **Affected model/state:** module-global in-memory `BoundedCache` stores `_VIDEO_RUNTIME_STATES`, `_VIDEO_BOOKMARKS`, `_VIDEO_ASSESSMENTS` (video) and `_RUNTIME_STATES` (animation).
* **Attacker-controlled identifier:** `session_id` — an arbitrary free-form string taken verbatim from the JSON body. **It is not validated against any owned resource.** The same `session_id` is the *cache key*.
* **Expected ownership rule:** the runtime state for a `session_id` belongs to its creating user; the read side already encodes this rule (`if not state or state.get("user_id") != str(user.id): return None`). A user must never be able to overwrite, wipe, or inject state into another user's active session.
* **Actual ownership behavior (writes):** `_VIDEO_RUNTIME_STATES.set(req.session_id, {... "user_id": str(user.id) ...})` **unconditionally overwrites** whatever entry exists for the supplied key, with **no check** on the prior entry's `user_id`. `_VIDEO_BOOKMARKS`/`_VIDEO_ASSESSMENTS` **append** to a list keyed by `session_id` with no ownership check on the pre-existing list.
* **Impact:** **Cross-user destructive mutation / cross-user state modification** (mission priority classes 1 and 3). An authenticated attacker (User B) can:
  1. **Destroy** User A's live video/animation playback state: after B `POST /sync`s A's `session_id`, A's subsequent `GET /videos/runtime/state/{id}` and `GET /videos/runtime/tutor-context/{id}` return `data: null` — the session's current scene, timestamp, and tutor-context anchor are silently replaced with B's entry.
  2. **Poison** A's session bookmarks/assessments bucket with attacker-controlled items keyed under A's `session_id`.
* **Severity rationale:** impact is **in-memory / process-local and transient**, and **reads fail closed** (no private-data disclosure, no durable-row mutation) — but the write-side boundary is absent while the read-side boundary is identical in both routers, proving the ownership rule was intended and is being bypassed by the write paths. This is the strongest remaining *provable* authorization defect after B1–B4; it is the same issue category as B4 (destructive cross-user action performed by an authenticated user) applied to live runtime state.
* **Classification:** CROSS-USER STATE MODIFICATION / CROSS-USER DESTRUCTIVE MUTATION (in-memory).

---

## E. Reproduction evidence

A temporary proof test was written under `backend/tests/proof_b5_tmp_audit.py`, run against the real ASGI app with real two-user JWT auth (mirroring the B4 harness), **then removed**. Three cases passed, each demonstrating the missing boundary:

```
User A owns session X (session_id = victim string)
POST /videos/runtime/sync {session_id: X, video_id: video_aaa, scene_index: 1, ...} as A
GET  /videos/runtime/state/X                    as A  ->  data present (A's own state)

POST /videos/runtime/sync {session_id: X, video_id: video_bbb, scene_index: 99} as B   # no ownership check
GET  /videos/runtime/state/X                    as A  ->  data = null   # A's state destroyed by B
```

Actual run output (video):

```
A_READ_BEFORE_B_ATTACK = {'video_id': 'video_aaa', 'scene_index': 1, 'current_timestamp_ms': 5000.0, 'user_id': 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', ...}
A_READ_AFTER_B_ATTACK  = None
```

Actual run output (animation):

```
A_ANIM_READ_BEFORE_B = {'blueprint_id': 'anim_aaa', 'scene_index': 2, 'user_id': 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', ...}
A_ANIM_READ_AFTER_B  = None
```

Bookmark injection (video) also confirmed: B `POST /videos/runtime/bookmark {session_id: X, title: "Injected by B"}` succeeds and stores `user_id = B` under A's session key.

Result summary:

| Scenario | Observed | Expected after fix |
| --- | --- | --- |
| B syncs A's session_id | 200; A's state replaced (A reads null) | 404-equalized, A state untouched |
| B bookmarks into A's session key | 201; bucket polluted under A's key | 404-equalized/no-op, A bucket untouched |
| B syncs same session_id (animation) | 200; A's anim state replaced | 404-equalized, A state untouched |

All three proof tests **passed** against current code — meaning the exploit is verified against HEAD `3ea948f`. The temporary file was deleted before finalizing; `git status --short` after deletion shows no trace of it.

---

## F. Root cause

The read paths establish and enforce per-user ownership; the write paths do not.

**Video (`video_runtime_router.py`):**

```python
# READ  (guard present)
state = _VIDEO_RUNTIME_STATES.get(session_id)
if not state or state.get("user_id") != str(user.id):
    return {"success": True, "data": None}

# WRITE (guard absent) — /sync
_VIDEO_RUNTIME_STATES.set(req.session_id, {"video_id": req.video_id,
    "scene_index": req.scene_index, ..., "user_id": str(user.id), ...})

# WRITE (guard absent) — /bookmark, /assessment
bookmarks = _VIDEO_BOOKMARKS.get(req.session_id) or []
_VIDEO_BOOKMARKS.set(req.session_id, _append_capped(bookmarks, bm, ...))
```

**Animation (`animation_runtime_router.py`):**

```python
# READ  (guard present) — /state/{session_id}
state = _RUNTIME_STATES.get(session_id)
if not state or state.get("user_id") != str(user.id):
    return {"success": True, "data": None}

# WRITE (guard absent) — /sync
_RUNTIME_STATES.set(req.session_id, {"blueprint_id": ..., ..., "user_id": str(user.id), ...})
```

`session_id` is **arbitrary client input used verbatim as the shared BoundedCache key**. Because the key is caller-chosen and never reconciled against the caller's identity on write, any authenticated user can address and clobber any other user's entry for a key they know. The only remaining barrier to a targeted attack is knowing/reaching a victim's `session_id` string — and, because `session_id` is unvalidated free-form text (tests in this repo use literals like `"test_vid_session"`, the animation smoke test uses `"test_anim_session"`), session identifiers are in practice low-entropy guessable strings rather than unguessable tokens. Reads correctly assume these are user-owned; writes betray the same assumption.

---

## G. Proposed minimal fix

Do **not** implement during this audit. The minimal service-boundary fix for the next implementation milestone:

1. **Video `/sync`:** before `set()`, read the existing entry. If an entry exists and its `user_id` differs from `str(user.id)`, raise the repository-standard equalized `NotFoundError` (404, no existence oracle). Otherwise create/update the entry as the caller (behavior unchanged for the legitimate owner and for brand-new keys).
2. **Video `/bookmark` and `/assessment`:** before appending, resolve the existing bucket. If the bucket exists and the newest/most-recent entry's `user_id` differs from `str(user.id)` (or any entry does), raise the same equalized `NotFoundError`. This blocks injecting attacker items under another user's session key while leaving owner behavior and first-write semantics intact.
3. **Animation `/sync`:** apply the identical read-before-write ownership check against `_RUNTIME_STATES`.
4. **API contracts unchanged;** responses for owner and new-key flows keep their current 200/201 shapes. The only new behavior is a 404 for cross-user addresses — consistent with the repo's 404-equalization convention used across B1–B4.

No model/schema/migration/config change is required.

---

## H. Regression-test plan

A new integration file (e.g. `backend/tests/integration/test_video_animation_runtime_security.py`) using the two-user JWT harness (mirror `test_tutor_retention_security.py`):

1. **Fail-before/pass-after — video sync:** A syncs session X; B syncs X; assert 404 and that `GET /state/X` as A still returns A's original data (currently: B's POST returns 200 and A reads null).
2. **Fail-before/pass-after — video bookmark:** A syncs X; B bookmarks into X; assert 404 and that A's bucket is unchanged.
3. **Fail-before/pass-after — video assessment:** A syncs X; B submits assessment into X; assert 404 and bucket unchanged.
4. **Fail-before/pass-after — animation sync:** A syncs X; B syncs X; assert 404 and A still reads her state.
5. **Legitimate owner still works:** A syncs and bookmarks her own session after the fix; 200/201 with correct data round-trip.
6. **Fresh-key semantics:** B may create state under a brand-new key that has no existing entry (200/201) — ensures no regressions to normal session creation flows.
7. **404-equalization:** cross-user address returns the same 404 as a non-existent key (no existence oracle).

---

## I. Deferred findings

Factual descriptions only — not ranked, not selected for B5.

1. **Export worker/tenant-scope at processing time.** `ExportService.process_export_job`/`_build_export_content` load the target presentation by `public_id`/`id` with no ownership predicate. The API route guards creation (`assert_ownership`), so today exploitation requires either an ownership transfer between job creation and processing, a future direct broker enqueue path, or a caller that bypasses the router. Latent/defense-in-depth; ownership re-assertion inside the worker is the natural hardening.
2. **Presentations-create folder validation is a broken call.** `presentation_service.create_presentation`/update paths call `validate_folder_ownership()` which is **undefined** on `PresentationFolderService` → `AttributeError` → 500 when `folder_id` is supplied; and folder reads raise `PermissionDeniedError` (403) rather than equalized 404, giving a minor per-folder existence oracle for folder UUIDs. The 500 fails closed (no authorization bypass) but the dead call should be wired to `_assert_folder_owner` and the 403 → 404 equalization considered.
3. **Simulation owner enforcement is caller-conditional.** `SimulationEngine` receives `owner_id` from each route rather than binding ownership inside the engine; all current callers pass the authenticated user's id, so it is safe today. Fragile if a future caller omits the parameter.
4. **Unscoped `get_by_public_id` repository variants.** Several repositories expose unscoped identifier lookups used only by internal/worker code or dead paths; none are reachable from authenticated routers today. Keep documented; do not treat as vulnerabilities.

---

## J. B6 handoff

```
B5 implementation: NOT STARTED
B5 fix:            NOT IMPLEMENTED
B5 commit:         NONE
Push:              NO
PR:                NO
```

**Next implementation action required (separate prompt):** implement the G-section minimal fix in `video_runtime_router.py` and `animation_runtime_router.py`, add the H-section regression tests, run targeted then full suites (unit + integration + ruff check), produce `B5_RUNTIME_SESSION_OWNERSHIP_IMPLEMENTATION_REPORT.md`, commit **one** atomic commit (`fix(security): enforce per-user ownership boundary on runtime session state`), then create the uncommitted `B5_RUNTIME_SESSION_OWNERSHIP_RELEASE_REPORT.md`.

---

## Repository safety (Phase 9)

```
git diff --check  -> clean
git status --short -> only the 6 pre-existing untracked release reports + this B5 audit report
git diff --stat   -> empty (no tracked changes)
```

The only new untracked file introduced by this audit is `backend/docs/audits/B5_SECURITY_OWNERSHIP_AUDIT_REPORT.md`. No tracked source file was changed; no commit was made.