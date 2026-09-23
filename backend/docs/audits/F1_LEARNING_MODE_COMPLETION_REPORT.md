# F1 — Learning-Mode Completion Drift (audit + fix)

> Milestone: **F1 — learning-mode completion drift** on
> `feature/individual-user-foundation` (baseline `4691e9a`).
> Classification vocabulary: **IMPLEMENTED / VERIFIED / PARTIAL / BLOCKED /
> NOT APPLICABLE**.

## A. Objective

When uploaded source units outnumber `2 × topics`, learning-mode completion must
still reach **100%** on the final learning slide, and the start / state readback
must index the learning deck against the topic deck (2 slides per topic) — never
against the merged source length.

## B. Root cause

`LessonPlayerService._session_total_slides` returned
`max(source_count, total_topics * 2)` for the learning / visual / animation
modes. `len(source_units)` was folded into the denominator so that any deck with
`source_count > 2 × topics` had:

- at `8a331a8` (when the position write loaded all units): a completion cap —
  e.g. 3 topics + 10 source units produced 5 topics-worth of buckets, so the
  final learning slide reported `(2+1)/5 = 60%`;
- at HEAD (after the position endpoint began loading units only in source mode):
  a **readback inconsistency** — `start` and `get_state` serialized with the
  inflated denominator (`max(6, 4) = 6` for 2 topics + 6 source), so a stored
  learning position of slide 5 was re-surfaced as a phantom slide outside the
  real 4-slide deck, while writing the same index clamped it to slide 3.

## C. Fix (IMPLEMENTED)

`backend/app/services/lesson_player_service.py` — `_session_total_slides`:

- source mode: `max(source_count, 1)` (unchanged);
- learning / visual / animation: `max(total_topics * 2, 1)` (source count no
  longer influences the learning denominator).

Call sites (all in the same service): `get_state` (≈158), `start` (≈262),
`set_position` (≈321). No schema/migration change. Completion is recomputed on
every position write, so nothing stored needs back-filling.

## D. Semantics (VERIFIED)

- Learning deck = exactly one concept + one visual slide per topic (slide `i` →
  topic `i // 2`); completion bucket `= (topic + 1) / total_topics`.
- Visual / animation modes normalize onto the learning deck.
- Source mode alone uses the uploaded source count (`max(source_count, 1)`,
  final slide pinned to the last topic → 100%).
- Readback (`start` / `get_state`) now clamps any stale position back into the
  real deck instead of re-inflating it.

## E. Regression evidence (VERIFIED, tested against negative)

With the fix temporarily reverted, the new tests fail; with the fix in place
they pass:

| Test | Reverted (old code) | Fixed |
|---|---|---|
| `TestSessionTotalSlides` (unit ×5) | 3 failed | 5 passed |
| `TestLearningCompletionIgnoresSourceCount` (unit ×2) | 1 failed (phantom readback 5 ≠ 3) | 2 passed |
| `test_learning_mode_completion_ignores_surplus_source_units` (integration ×1) | 1 failed (readback returned 5) | 1 passed |
| `test_learning_mode_completion_reaches_100_despite_surplus_source_units` (E2E ×1) | pass | 1 passed |

Scope note, recorded honestly: at HEAD the position-write path already computes
`2 × topics` and the runtime completion writes were already correct; the
residual defect is the readback clamp. The E2E therefore locks the end-to-end
invariant (real browser → backend → stored 100%) with a surplus source deck; it
does not fail under the old code. The unit and integration layers carry the
old-code-discriminating assertions.

## F. Tests added (31 tests total in scope)

- **Unit** (`tests/unit/test_lesson_player_service.py`, +7): `TestSessionTotalSlides`
  — source uses source count; learning = 2/topic; learning ignores surplus
  source units (10 source / 3 topics → 6); visual & animation follow the
  learning deck; never returns 0. `TestLearningCompletionIgnoresSourceCount` —
  final learning slide reaches 100 with 6 surplus units; stale
  inflated-denominator position (slide 5) clamps to slide 3 on start and
  get_state resume.
- **Integration** (`tests/integration/test_p15_resume_api.py`, +1):
  `test_learning_mode_completion_ignores_surplus_source_units` — 2 topics + 6
  source: slide 1 → 50%, slide 3 → 100%, stale stored slide 5 clamps to 3 on
  get_state and start, out-of-range 999 clamps to 3, cold reload reads the
  repaired position.
- **E2E** (`tests/e2e/test_presentation_player_tools.py`, +1):
  `test_learning_mode_completion_reaches_100_despite_surplus_source_units` —
  4 topics + succeeded version (4 blocks) + 10 source units, End key at
  `?mode=learning`, `#ljCompletionPct` ends at **100.0**.

## G. Test results (exact, re-executed this milestone)

| Suite | Command | Result |
|---|---|---|
| Ruff | `uv run --project . ruff check app tests` | **All checks passed** |
| Unit (full) | `uv run --project . pytest tests/unit -q` | **1613 passed** (baseline 1606 + 7) |
| Integration (full) | `uv run --project . pytest tests/integration -q` | **216 passed** (baseline 215 + 1) |
| P15 integration | `test_p15_resume_api.py` (+ peers) | covered by full run |
| Presentation-player E2E | `pytest tests/e2e/test_presentation_player_tools.py -m e2e -q` | **14 passed** (baseline 13 + 1) |
| P15 resume E2E | `pytest tests/e2e/test_p15_resume_e2e.py -m e2e -q` | **3 passed** |
| Postgres (`-m postgres`) | full | 33 passed / **7 failed — pre-existing** |

### Pre-existing failures, deliberately excluded (not introduced by F1)

1. `tests/e2e/test_learner_journey.py::test_learner_journey_panel_renders` —
   FAILS on the clean baseline `4691e9a` too (verified by stashing the F1
   changes and re-running). Assertion `"Learner Progress" in panel.inner_text()`.
2. Seven postgres migration-consistency tests (`test_alembic_revision_is_single_head`,
   `test_migrations_are_idempotent_only_forward`, `test_0032_schema_contract`,
   `test_p13/p14/p15_no_new_migration_head_unchanged`,
   `test_p16_migration_head_is_0034`) — fail because the migration head advanced
   to `0037_teaching_continuity` in `8a331a8` and the frozen expectations were
   never advanced. F1 touches no migrations/schema, so this is out of scope.

## H. Security (VERIFIED)

Diff + working-tree scan for `AIza…`, `sk-…`, `ghp_…`, `github_pat_…`, `xoxb-…`,
`BEGIN PRIVATE KEY`, `client_secret=`, `access_token=`, `refresh_token=`,
`password=`: **no secrets in the changed files**. `backend/.env` stays
untracked/gitignored and untouched. No `console.log` / `debugger` / temporary
artifacts in the diff.

## I. Known limitations

- The E2E browser regression locks the end-to-end 100% invariant but is not an
  old-code discriminator at HEAD (readback-clamp drift is fully captured by the
  unit + integration layers).
- Completion percentages remain relative to stored `completion_percentage`;
  phantom positions from before the fix are repaired lazily on next read/write
  (no back-fill migration).

## J. Repository state

Planned single atomic commit (explicit paths only), message
`fix(player): correct learning mode completion semantics`, plus this report.
Release verification is recorded separately in
`F1_LEARNING_MODE_COMPLETION_RELEASE_REPORT.md`.