# F1 — Learning-Mode Completion Drift — Release Report

> Milestone: **F1 — learning-mode completion drift**
> Fix commit: `f4d0a53` on `feature/individual-user-foundation` (baseline `4691e9a`).

## A. Commit

| Item | Value |
|---|---|
| Commit hash | `f4d0a53` (short) |
| Commit message | `fix(player): correct learning mode completion semantics` |
| Parent | `4691e9a fix(player): make annotation layers durable and view-accurate` |
| Files | 5 (+572 / −1) |

## B. Root cause

`LessonPlayerService._session_total_slides` returned
`max(source_count, total_topics * 2)` for learning/visual/animation. This folded
uploaded source length into the learning denominator, so `source_count > 2 ×
topics` (a) capped completion below 100% when the position write still loaded
all units (`8a331a8`) and (b) at HEAD re-inflated the readback deck in `start` /
`get_state`, re-surfacing phantom slides on resume that the position endpoint
had already clamped.

## C. Fix

`_session_total_slides` now returns `max(total_topics * 2, 1)` for the
learning/visual/animation modes (source mode keeps `max(source_count, 1)`).
All three call sites — `get_state`, `start`, `set_position` — index consistently
against the topic deck. No migration; completion is recomputed per write.

## D. Semantics

Learning deck = `2 × topics` (concept + visual per topic); completion bucket
`(topic + 1) / total_topics`; visual/animation normalize onto learning; source
mode alone uses the source count; readback clamps stale positions into the real
deck.

## E. Regression evidence

With the fix reverted, the discriminating new tests fail (unit `_session_total_slides`
×3, unit + integration phantom-readback clamp); with the fix they pass. The E2E
locks the browser→backend 100% invariant with 10 source units on a 4-topic
learning deck (not old-code-discriminating at HEAD — the residual defect is the
readback clamp, covered by the unit + integration layers).

## F. Results (re-executed)

| Suite | Result |
|---|---|
| `ruff check app tests` | All checks passed |
| Unit (full) | **1613 passed** |
| Integration (full) | **216 passed** |
| Presentation-player E2E | **14 passed** |
| P15 resume E2E | **3 passed** |
| Postgres (`-m postgres`) | 33 passed / 7 failed — **pre-existing** (migration-head expectations frozen before `8a331a8`'s `0037`; F1 touches no schema) |
| `test_learner_journey_panel_renders` E2E | fails on the clean baseline `4691e9a` too — **pre-existing** (verified via stash) |

## G. Security

Diff/working-tree scan (`AIza`, `sk-`, `ghp_`, `github_pat_`, `xoxb-`,
`BEGIN PRIVATE KEY`, `client_secret=`, `access_token=`, `refresh_token=`,
`password=`): **clean**. `backend/.env` untracked/ignored, untouched.

## H. Repository state

Immediately after the atomic commit, tracked working tree is **clean**; the only
remaining untracked file is the pre-existing, deliberately-uncommitted
`backend/docs/audits/NEXT_MILESTONE_RELEASE_REPORT.md` (prior milestone
documentation). **Push: NO. PR: NO.**

## I. Known limitations

- E2E is an end-to-end invariant lock, not an old-code discriminator (noted above).
- Pre-fix phantom positions are repaired lazily on the next read/write; no
  back-fill migration.

## J. Next milestone (recommended)

**B1 — quiz-generation IDOR**: quiz content is generated for a lesson loaded by
`public_id` without an owner check. Continue from the audit candidate already
recorded in this branch's milestone releases.