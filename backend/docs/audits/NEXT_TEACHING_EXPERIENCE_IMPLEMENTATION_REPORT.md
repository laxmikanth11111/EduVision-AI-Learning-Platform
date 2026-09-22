# NEXT Teaching Experience Implementation Report

> Milestone: **Teaching Experience Completion (Teaching Experience #3)**

This report records the architecture review of the "teaching experience" layer and the
small, coherent implementation slice that followed. Classification vocabulary:
**IMPLEMENTED / PARTIAL / MOCK / PLANNED / MISSING / BLOCKED / VERIFIED**.
WCAG conformance is never claimed unless actually tested with an assistive tool.

---

## A. Scope

This milestone did **not** redesign or rebuild any existing Presentation Player
feature. The professional teaching tools (pen, highlighter, eraser, laser, text,
shapes, undo/redo, present mode with scaling, presentation counter, auto-hide
controls, keyboard shortcuts/help, thumbnails, AI assistant grounded in the real
Tutor API, slide-accurate session resume, session-local annotation isolation)
were already released in commit `767fb82`.

The architecture review instead looked for genuinely-*missing* pieces with the
highest teaching value that the existing backend already supports. Two such pieces
were found and implemented:

1. **Real lesson-completion surfacing (PARTIAL -> IMPLEMENTED).** The backend has
   always computed `completion_percentage` on every persistent learning session
   (`/lessons/{id}/player/start`, `/player/position`), and the Dashboard already
   renders it. The player's **Learner Progress panel**, however, hardcoded
   `learnerCompletion = 0` and so always displayed **"Lesson progress 0%"** — even
   while the same lesson on the Dashboard showed real progress. The dashboard and
   the player contradicted each other.
2. **Annotation visibility toggle (MISSING -> IMPLEMENTED).** During live
   teaching, an instructor frequently wants to reveal the *clean* slide to discuss
   without the accumulated markup. No mechanism existed to temporarily hide the
   annotation overlay. Added an accessible toolbar toggle (eye button) that hides
   and restores the overlay canvas without touching the slide DOM.

Two further review findings were deliberately **not** implemented now and are
tracked in Section I (recommended next milestone):

- Notes mode / presenter-notes overlay (source speaker notes already render as
  content cards on source slides; a present-mode notes peek remains future work).
- Annotation persistence (the `student_notes`/`bookmarks` tables are orphans from
  an older schema and do not match the current per-slide canvas data model).

---

## B. Architecture inspected

Backend reviewed (read-only):

- `app/services/learning_session_service.py` — `start_session` seeds
  `completion_percentage = _progress_percentage(topic_index, total_topics)`
  (line 132); `set_slide_position` (line 174) persists slide-accurate positions
  and derives the topic via `slide_index // 2`; `_progress_percentage` (line 249)
  = `((topic_index + 1) / total_topics) * 100`.
- `app/services/learner_progress_service.py` — per-lesson completion aggregation
  (lines 176-210); the Dashboard's lesson-progress rows.
- `app/api/v1/player.py` — `start_player_session`, `set_slide_position`, plus
  `/checkpoint`, `/mastery`; every response serialized through
  `PlayerSessionResponse` (which already contained `completion_percentage`).
- `app/schemas/player.py` — `PlayerSessionResponse.completion_percentage`
  (float, default 0.0). **No backend change was needed.**

Frontend reviewed (read-only):

- `backend/frontend/player.html` — `init()` (line 700) consumes
  `/player/start`; `loadLearnerJourney()`/`renderLearnerJourney()` (lines ~985/1003)
  drive the Learner Progress panel; `syncTopic()` (line 1736) debounces the
  400 ms position write; `refreshLearnerJourney()` previously reset
  `learnerCompletion = 0` after every quiz submit. Annotation overlay wiring:
  `ensureAnnotCanvas` / `sizeAnnotCanvas` / `rebindAnnotLayer` / `setTool`
  (lines ~3425-3700).

Confirmed gap in Section B (teaching session state): the player never read
`completion_percentage` from either `/player/start` or `/player/position`,
so the panel's report was permanently "0%". The dashboard was honest; the player
was not — a genuine PARTIAL worth fixing.

---

## C. Existing capabilities (verified during review)

| Capability | Status | Evidence |
|---|---|---|
| Quiz/interaction flow (adaptive attempts, submit, results) | IMPLEMENTED | `/api/v1/quizzes` router (8 routes); player `startQuiz` → `POST /quizzes/{id}/attempts` → `POST /attempts/{id}/next` (adaptive) → `POST /attempts/{id}/submit`; full in-browser checkpoints + mastery tie-in |
| Teaching session & resume | IMPLEMENTED | `LearningSession` persisted; `/player/start`, `/player/position`; resume via `sessionSlide` |
| AI learning experience | IMPLEMENTED | AI panel grounded in real Tutor endpoints (`/tutor/sessions`, `/messages`); source attribution, confidence; never fabricated |
| Navigation quality | IMPLEMENTED | deep-links, `?slide=` override, thumbnails, keyboard, present-mode scaling, counter |
| Annotation overlay isolation | IMPLEMENTED | separate `<canvas>`; slide DOM never mutated (E2E verified) |
| Annotation visibility control | **MISSING** | no way to hide the overlay → implemented in this milestone |
| Learner progress display | **PARTIAL** | panel existed but hardcoded 0% → implemented in this milestone |

---

## D. New implementation (this milestone)

Files changed (working tree; **not committed** unless instructed):

1. `backend/frontend/player.html`
   - `init()`: captures `state.session.completion_percentage` into
     `learnerCompletion` so the first panel render shows the real value.
   - New `applyCompletionFromResponse(payload)`: stores the returned
     `completion_percentage` and re-renders the Learner Progress panel.
   - `syncTopic()`: reads the `/player/position` response and applies the
     returned completion (live progress as the learner moves).
   - `refreshLearnerJourney()`: no longer zeroes `learnerCompletion` before
     re-fetching (fixes the "back to 0%" flicker after a quiz submit).
   - `renderLearnerJourney()`: adds `id="ljCompletionPct"` for stable test hooks.
   - New toolbar button `#teachAnnotToggle` (eye, `aria-pressed`,
     `onclick="toggleAnnotVisibility()"`).
   - New `annotVisible` flag + `toggleAnnotVisibility()`: toggles overlay
     `visibility`, co-locates pointer events, mutates the button's
     `aria-pressed`/`title`, and returns the active tool to `pointer` when hiding
     so no invisible drawing is attempted. The slide DOM is untouched.

2. `backend/tests/unit/test_player_teaching_tools_contract.py` — new required
   wires: `teachAnnotToggle`, `toggleAnnotVisibility`, `annotVisible`,
   `completion_percentage`, `applyCompletionFromResponse`, `ljCompletionPct`.

3. `backend/tests/e2e/test_presentation_player_tools.py`
   - Generalized `_player_lesson`/`_open_player` to accept a `topics` list so
     progress assertions are deterministic.
   - New `test_annotation_visibility_toggle_hides_and_shows_layer` — draws a
     stroke, hides the overlay, asserts the canvas is invisible and
     `aria-pressed=false`, reveals it, asserts the stroke is still stored.
   - New `test_learner_progress_completion_reflects_slide_position` — asserts the
     panel shows the real backend value for a fresh session (25% for a 4-topic
     deck, never 0%), then jumps to the last slide with the `End` key and asserts
     the panel advances to the backend-computed ceiling (50% in source mode — see
     Section H limitation on slide↔topic mapping).

---

## E. Security

- No new backend surface was added. Only the existing authenticated endpoints
  (`/player/position`, `/player/start`) are consumed; ownership checks remain in
  `LessonPlayerService`.
- The annotation visibility toggle is purely presentational — it never reads or
  transmits learner data and cannot affect another user's deck.
- No credentials, `.env`, local databases, or browser caches were involved; only
  the three listed files changed. `git status` shows exactly those three modified
  files.

## F. Accessibility

- `#teachAnnotToggle` is a real `<button>` with `aria-label`, `aria-pressed`
  (mirrors the live toggle state), and a dynamic `title`.
- Activation state is also communicated visually (`.teach-btn.active`) so the
  toggle is not color-only.
- The existing focus-visible outline (`button:focus-visible`) already covers the
  new button; it is keyboard operable (Tab + Enter/Space).
- **Not claimed:** no full WCAG audit was run with assistive tooling. The player
  retains its pre-existing accessibility posture (labeled toolbar, aria-hidden
  canvas, keyboard help overlay); the new control adds no contrast or text-size
  regression.

## G. Performance

- Progress surfacing adds exactly one JSON field already present in the payload;
  `renderLearnerJourney()` re-renders a small panel only when a position write
  returns or the journey reload completes (debounced 400 ms). No new requests.
- `toggleAnnotVisibility()` mutates a single element's visibility and a button
  attribute — O(1), no canvas repaint/redraw on hide.
- The overlay canvas keeps working after restore because only `visibility`
  changes; sizing (`sizeAnnotCanvas`) is untouched.

## H. Tests & verification

Run under `uv` (Python 3.14 project venv), `backend/` working directory:

| Suite | Result |
|---|---|
| `uv tool run --from ruff ruff check app tests` | PASS (all checks) |
| `node --check` on extracted player.html inline JS | PASS |
| `uv run --project . pytest tests/unit -q` | **1573 passed** |
| `uv run --project . pytest tests/integration -q` | **209 passed** |
| `uv run --project . pytest tests/unit/test_player_teaching_tools_contract.py -q` | **5 passed** |
| `uv run --project . pytest tests/e2e/test_presentation_player_tools.py -m e2e -q` | **8 passed** |
| `uv run --project . pytest tests/e2e/test_p6_full_loop.py -m e2e -q` | PASS (1) — regression for the panel refresh race |

**Regression caught during this milestone:** a first version rendered the panel
early inside `init()`, which surfaced an empty-journey frame before the
checkpoint/mastery fetch finished and briefly broke
`test_p6_full_loop`. Fixed by only *storing* the initial completion in `init()`
and letting `loadLearnerJourney()` perform the first full render.

**Pre-existing failures (reproduced unchanged on pristine `HEAD` — not caused by
this milestone, tracked in Section I):**

| Test | Failure |
|---|---|
| `test_learner_journey_panel_renders` | asserts `"Learner Progress"` but `.lj-panel h4` CSS `text-transform: uppercase` makes `inner_text()` return `"LEARNER PROGRESS"` (test defect) |
| `test_p15_resume_journey_and_refresh` | expects the deck to render `/ 4` slides in the default (source) mode; the manual deck provides 2 content units → panel never shows 4 slides |
| `test_p15_dashboard_resume_deep_link` | same source-mode slide-count expectation |
| `test_p15_resume_is_learner_scoped` | same |

---

## I. Known limitations & recommended next milestone

Known limitations of the delivered slice (honest):

1. **Source-mode completion ceiling.** The backend computes completion from
   `topic = slide_index // 2` (two learning slides per topic). In source mode the
   player exposes one slide per topic, so a source-mode deck can only ever reach
   ~50% completion (topic `(N-1)/2` of N) even on its final slide. The panel now
   displays this value faithfully — the ceiling itself is a pre-existing
   slide↔topic mapping inconsistency between modes that should be a deliberate
   follow-up.
2. **No annotation persistence.** Annotations remain session-local in-memory
   (existing limitation; `student_notes`/`bookmarks` tables are orphaned legacy
   columns and do not match the current per-slide canvas model). Persisting
   annotations needs a new data model and is out of scope.
3. **No presenter-notes mode.** Speaker notes render as content cards on source
   slides; there is no present-mode notes peek or notes toggle yet.

Recommended next milestone — **"Teaching Continuity"** (ordered by value):

1. Resolve the slide↔topic completion mapping so source-mode decks can reach
   real completion parity with learning mode (align `slide_index` semantics per
   mode; update `/player/position` handling and the P15 resume suites).
2. Add a present-mode **notes peek** toggle for instructors (notes already exist
   as NOTE blocks — a small frontend-only overlay).
3. Design and implement **annotation persistence** (migration + model + ownership
   rules + payload validation) only if the product requires cross-session
   annotation continuity; the current orphaned tables must first be reconciled or
   removed.
4. Fix the stale P5/P15 E2E assertions (case-sensitivity; mode-appropriate slide
   counts) so the full E2E directory is green.

---

## J. Repo state & hand-off

Working tree changed files (all uncommitted, ready for review):

- `backend/frontend/player.html` (+40)
- `backend/tests/e2e/test_presentation_player_tools.py` (+84/-9)
- `backend/tests/unit/test_player_teaching_tools_contract.py` (+8)

No commit was created. To finish this milestone, review the diff
(`git diff`), then commit with a message following the repo's
`<type>(<scope>): <subject>` convention (e.g.
`feat(player): surface real lesson progress and add annotation visibility toggle`).