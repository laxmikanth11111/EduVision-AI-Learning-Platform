# Teaching Continuity Implementation Report

> Milestone: **Teaching Continuity (source-mode completion ceiling, presenter notes peek, annotation persistence)**

This report records the implementation slice that completes the teaching
experience described in `NEXT_TEACHING_EXPERIENCE_IMPLEMENTATION_REPORT.md` (its
Section I deferred notes mode and annotation persistence). Classification
vocabulary: **IMPLEMENTED / PARTIAL / MOCK / PLANNED / MISSING / BLOCKED /
VERIFIED**. WCAG conformance is never claimed unless actually tested with an
assistive tool.

---

## A. Scope

Three gaps were closed in a single atomic change on top of the release baseline
`6f011f3`:

1. **Source-mode completion ceiling (BUG, IMPLEMENTED + VERIFIED).** A source
   deck could never reach 100% lesson completion: source slide positions were
   always mapped onto the last topic too early, capping completion at ~50% even
   when the learner reached the deck's final slide. The position mapping is now
   mode-aware — source slides map onto topics via the topic outline, with the
   final source slide pinned to the last topic so completion legitimately
   reaches 100%.
2. **Presenter notes peek (PLANNED -> IMPLEMENTED).** A right-hand notes overlay
   (`.notes-overlay`, `#notesPanel`) toggled from the teaching toolbar
   (`#teachNotesToggle`) or the `n`/`N` keys, closed with `Escape` or the toggle
   button, showing the current slide's presenter notes (topic `notes` in
   learning mode, source unit text in source mode) or a visible empty-state
   message.
3. **Annotation persistence across reloads (PLANNED -> IMPLEMENTED).** Per-slide
   markup now persists per view layer to the backend
   (`PresentationAnnotation` rows keyed by
   `(user_id, lesson_id, player_mode, slide_index)`) and is restored on reload,
   so in-progress teaching markup survives a refresh on every deck view.

The milestone also installs per-layer annotation validation (item/point/text/byte
caps, color/size/tool closed-shape validation), a save-status indicator
(`#annotSaveStatus`) with debounced saves that capture their target layer at
schedule time, and a full regression test battery (unit, integration, E2E,
contract).

---

## B. Architecture inspected

Backend reviewed/implemented:

- `app/services/lesson_player_service.py` — `_build_source_topic_map`,
  `_session_total_slides`, player start/`set_position` mode wiring.
- `app/services/learning_session_service.py` — `set_slide_position` mode-aware
  topic resolution (`//` for learning slides, explicit topic map for source).
- `app/services/learner_progress_service.py` — resume links now carry `&mode=`.
- `app/services/presentation_annotation_service.py` (new) — `parse_annotations`
  validation + layer upsert/delete persistence.
- `app/api/v1/annotations.py` (new) — GET/PUT layer endpoints, lesson-owner
  scoped through the shared player ownership helper (403/404/422 semantics).
- `app/schemas/annotations.py`, `app/models/presentation_annotation.py`
  (new) + migration `0037_teaching_continuity.py` (new).
- `app/api/v1/player.py`, `app/main.py` — position route passes `mode`; router
  registration.

Frontend implemented/verified:

- `backend/frontend/player.html` — notes overlay, save-status span, `syncMode()`
  normalization (visual/animation -> learning for session positions while layers
  keep raw view keys), `annotKey()`, debounced `scheduleAnnotSave()` /
  `saveAnnotationsFor(target)`, `loadPersistedAnnotations()` (non-destructive
  merge + redraw), `?mode=` deep-link handling, `n`/`N` shortcuts, thumbnail +
  toolbar wiring, and the `.notes-overlay { bottom: 122px }` fix that keeps the
  teaching toolbar clickable while the notes peek is open.

---

## C. Mode-aware completion (source ceiling fix)

**Semantics.** `PlayerMode` is `source | learning`; the animation/visual decks
track session positions as `learning`. A learning position maps a slide pair to
its topic via `slide_index // 2`. A source slide counts against the uploaded
source deck and is mapped onto topics through `_build_source_topic_map`:

- outline `slide_ranges` (1-based) are matched against each source unit's
  `position`; the first topic whose range covers the position wins;
- any mismatch falls back to an even split
  `floor(i * total_topics / size)`;
- in both paths the **final source slide is pinned to the last topic**, so the
  last source slide reports `(last+1)/total_topics = 100%`.

`set_slide_position` persists the slide index and the resolved topic, updates
the session `player_mode`, and returns the mode-accurate
`completion_percentage`. `PlayerSessionResponse`/`to_player_session` carry the
same values so cold reloads (/player) agree with hot positions (/player/position).

**Verified** by `TestModeAwareSlidePosition` (unit: pair mapping,
topic-map-with-pinned-final, proportional fallback, invalid mode rejection),
integration tests against the real ASGI app
(`test_source_mode_final_slide_reaches_full_completion`,
`test_position_mode_switches_session_representation`), and a browser E2E that
reaches 100% on the last source slide.

---

## D. Presenter notes peek

`#notesPanel` is a fixed right-side region `role="region"` (not a `<main>` banner
or overlay that steals focus); `#teachNotesToggle` carries
`aria-expanded`/`aria-controls`, `#notesBody` is `aria-live="polite"`. Content is
rendered from `currentNotes()` with `escHtml()` (never raw `innerHTML` from deck
text), and an explicit "No presenter notes exist for this slide." empty state is
shown instead of a blank panel. `openNotes`/`closeNotes`/`toggleNotes` update
state, re-render on every `goTo` while open, and restore focus to the toggle on
close. Keyboard: `n`/`N` open while no modal is visible; while open the panel is
modal-like (only `Escape` honoured), matching the existing help/quiz overlays.

The CSS fix `.notes-overlay { bottom: 122px }` (was `bottom: 0`) keeps the
bottom teaching toolbar reachable so the toggle button can both open and close
the panel.

---

## E. Annotation persistence

- **Model/API.** One row per view layer
  `(user_id, lesson_id, player_mode, slide_index)`
  (`unique` `uq_lesson_annotations_layer`); `items` stored as JSON/JSONB.
  `PUT /lessons/{id}/annotations/{player_mode}/{slide_index}` upserts a layer
  (empty payload deletes it); `GET /lessons/{id}/annotations` lists the owner's
  layers. Both routes run through `LessonPlayerService._assert_lesson_ownership`
  so non-owners get 403 and absent lessons 404 without leaking existence.
- **Validation.** `parse_annotations` enforces `<JSON array>`, `<=500` items,
  2..4000 points per stroke, non-empty text `<=2000` chars, `<=300_000` byte
  serialized layer cap, finite coordinates, `#rgb|#rrggbb|#rrggbbaa` colors,
  size 1..48, closed shape kinds (`rect|ellipse|line|arrow`), and pen/
  highlighter tools. Violations surface as 422. No HTML is ever rendered from
  `items` server-side.
- **Frontend.** Strokes commit locally under
  `annotBySlide[playerMode:index]`; `scheduleAnnotSave()` captures the target
  `{mode, rawMode, index, key}` at schedule time so a later navigation cannot
  overwrite the wrong layer, then debounces 700 ms before `saveAnnotationsFor`
  PUTs it. `#annotSaveStatus` announces Saving/Saved/Save failed
  (`role="status"`, `aria-live="polite"`); failures keep the local marks.
  `loadPersistedAnnotations()` merges layers on init without clobbering
  in-progress work, then `redrawAnnots()`. Layer names follow the raw view
  (`playerMode`), so source/learning visual/animation marks stay isolated while
  session positions normalize to `learning`.

---

## F. Deep links and resume parity

`learner_progress_service` resume links are now
`/frontend/player.html?lesson={id}&slide={n}&mode={mode}`; the player honours
`?mode=source|learning` during init, then restores a session that moved off slide
0, then falls back to source-when-units-else-learning. The P15 tests pin the
learning deck via `&mode=learning` (fixed a separator bug in the E2E helper so the
extra query parameter is joined with `&`).

---

## G. Security properties

- Annotation endpoints are auth-scoped (`get_current_user`) and further filtered
  by owner resolution and the session-scan indexes; tests assert 403 for
  cross-user reads/writes and 404 for absent lessons.
- The source deck depends on the owner's `content_units`/`topic_outline` only;
  no cross-owner data is reachable.
- Layer payloads are validate-don't-parse; text is escaped on render; no
  HTML/JS is persisted from the client beyond the closed item schema.

---

## H. Test evidence (all run against `py -3.11`, SQLite test DB, fresh per run)

- `ruff check app tests` — clean (16 findings fixed during dev: 2 auto, 14
  needed `match=` on `pytest.raises(ValueError)`; one missing `select` import;
  one inverted `&mode=` separator).
- Unit: **1605 passed** (`tests/unit`, includes new
  `test_presentation_annotation_service.py`, `test_annotation_routes.py`, and
  `TestModeAwareSlidePosition` + contract additions).
- Integration: **211 passed** (`tests/integration`, real ASGI + JWT; includes the
  two new mode/switch tests and updated P15 resume assertions).
- E2E (`pytest -m e2e`, real Chrome): presentation-player suite **10/10
  passed** including the new notes-overlay and annotation-persistence-across-
  reload tests; P15 resume **3/3 passed**; full `tests/e2e` run **34 passed, 2
  failed** — the two failures
  (`test_learner_journey_panel_renders`,
  `test_p7_dashboard_e2e`) are **pre-existing and out of scope**: neither file is
  touched by this change (the journey assertion expects title-case text while
  the panel's CSS forces `text-transform: uppercase`; the dashboard assertion
  hits a strict-mode `.trend` double-match).
- Browser-level sanity of the new window paint is covered by the E2E run; a
  dedicated visual-a11y (colour-contrast/screen-reader) pass is **PLANNED**
  (not claimed here).

---

## I. Remaining gaps and follow-ups (PLANNED)

- Move the notes overlay to a real focus-trapped dialog or a lower-z
  in-slide note card to allow pointer navigation while notes stay open.
- Auto-pause annotation saves while offline and queue them for the next
  `navigator.online` transition (the current design retries on the next edit).
- Layer garbage-collection ttl for lessons no longer used in a classroom
  (the table has no hard row cap per lesson today).
- A screen-reader + keyboard-only audit of the notes panel (WCAG claim pending).

---

## J. Deliverables

One atomic commit on `feature/individual-user-foundation` (baseline `6f011f3`),
working tree clean, no push/PR. Contains the backend model/migration/service/
schemas/router, the frontend overlay + persistence work, all new/modified tests,
and this report.