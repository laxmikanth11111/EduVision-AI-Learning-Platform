# Annotation Layer Durability — Implementation Report

> Milestone: **Annotation layer durability (no stroke silently lost; every layer bound to its own view)**

> Implemented on top of `8a331a8` as one atomic change on
> `feature/individual-user-foundation`.

This report closes the highest-value gap from the production-readiness audit of
the teaching-continuity feature that shipped at `8a331a8`: annotation strokes
drawn in the player were being silently lost, persisted under the wrong view
layer, or resurrected after a reload. Classification vocabulary:
**IMPLEMENTED / PARTIAL / MOCK / PLANNED / MISSING / BLOCKED / VERIFIED**.
WCAG conformance is never claimed unless actually tested with an assistive
tool.

---

## A. Scope

The milestone is **annotation-layer durability**: every stroke commits to the
correct view layer and survives navigation, reload, and tab close — with no 500
under concurrent first-writes. It is deliberately the smallest coherent slice:
one backend service method plus the player's annotation/navigation persistence
path, and no schema migration.

Implemented findings (all VERIFIED):

1. **F3 (backend, IMPLEMENTED + VERIFIED).** `PresentationAnnotationService.replace()`
   could raise a 500 when two concurrent first-writes raced for the same layer
   key (both SELECTed `None`, then one INSERT violated
   `uq_lesson_annotations_layer`). It now catches `IntegrityError`, rolls back,
   re-selects, adopts the winner's row, folds the write on top, and keeps a
   deterministic `public_id`.
2. **P1 (frontend, IMPLEMENTED + VERIFIED).** `saveAnnotationsFor()` PUTs to
   `at.mode` (i.e. `syncMode()` = `learning`) even while the learner is in
   Visual/Animation Mode. Marks drawn on the visual/animation deck were stored
   under `learning:{index}` and their own layer key (`visual:N`) could never be
   restored — reload wiped them and, worse, polluted the learning layer. The PUT
   now targets the real view layer via the captured `rawMode`.
3. **P2/P3 (frontend, IMPLEMENTED + VERIFIED).** One shared debounce timer was
   cleared by every `scheduleAnnotSave()`, so drawing on slide A then drawing on
   slide B within 700 ms silently dropped A's save; `annotClearAll()` iterated
   keys but only the last scheduled save survived, so cleared layers resurrected
   after reload. A per-layer pending-save map with a single flush that persists
   **every** pending layer (and every cleared layer) replaces the shared-timer
   cancellation.
4. **P4 (frontend, IMPLEMENTED + VERIFIED).** No save was guaranteed on tab close
   or page reload. `pagehide`/`beforeunload` now flush all pending layers with
   `fetch(..., { keepalive: true })`.
5. **P11 (frontend, IMPLEMENTED + VERIFIED).** Startup hydration raced the 700 ms
   debounce: a stroke drawn before the `GET /annotations` resolved could be PUT
   over an existing server layer that hydration had not yet merged (the old load
   `continue`d whenever the local layer had items). Pending saves now await the
   hydration promise, and hydration merges server marks under in-progress local
   strokes instead of discarding either.
6. **P7 (frontend, IMPLEMENTED + VERIFIED).** The visual/animation decks render
   `topics[idx]` (one slide per topic) but navigation bounded/counted them as
   `slides` (two per topic) and bound annotations to `current`. Introduced
   `deckLength()` (mode-aware), `sessionIndex()` (mode-aware session position),
   mode-switch index mapping (entering visual/animation lands on the current
   learning slide's topic and never writes a topic index back into
   `currentLearningSlide`), topic-indexed thumbnails for visual/animation, and
   applied `deckLength()` to `goTo`/`next`/`prev`/`End`/`updateChrome`/
   `startIndexFromUrl`. This both fixes `Topic not found.` overshoot rendering
   and makes annotation keys agree with the render so marks restore to the
   slides they were drawn on.

Explicitly **deferred** (documented, out of scope for this slice): F1 learning-
mode completion drift, B1 quiz-generation IDOR, F2 session-uniqueness, F4
stale-write conflict detection — see Section I.

---

## B. Architecture inspected / affected

- `app/services/presentation_annotation_service.py` — `replace()` insert-race
  recovery (F3).
- `app/models/presentation_annotation.py` —
  `uq_lesson_annotations_layer (user_id, lesson_id, player_mode, slide_index)`
  (the constraint the fix works against).
- `app/api/v1/annotations.py` — route already owner-scoped
  (`_owned_lesson` -> 403) and mode-validated via `AnnotationLayerMode.as_set()`;
  unchanged apart from benefiting from F3.
- `backend/frontend/player.html` — annotation persistence block
  (`scheduleAnnotSave`/`saveAnnotationsFor`/`loadPersistedAnnotations`), deck
  index utilities, `setPlayerMode`/`goTo`/`nextSlide`/`updateChrome`/
  `startIndexFromUrl`/`buildThumbnails`, `syncTopic`/`finishLesson`, unload
  listeners.
- Test surfaces: unit annotation-service suite, frontend contract suite, a new
  integration suite hitting the real ASGI app (`test_annotation_layers_api.py`),
  and the browser-level player suite.

---

## C. F3 — concurrent first-write safety (backend)

`replace()` previously did SELECT -> INSERT-or-UPDATE -> `flush()`. Two requests
creating the **same brand-new layer** both SELECTed `None`; the second INSERT
violated `uq_lesson_annotations_layer` and the API returned 500 (the client then
could not reconcile, leaving the layer in the winner's state but surfacing a
failed save). The fix:

```
try:
    await self._uow.flush()
except IntegrityError:
    await self._uow.rollback()
    winner = re-select(same owner/lesson/mode/index)
    if winner is None: raise
    winner.items = items
    await self._uow.flush()
    row = winner
```

`rollback()` is safe on this path because the annotations route performs no
other writes in the transaction before `replace()`; if the row genuinely cannot
be found after rollback the exception re-raises (a client retry then succeeds).
The winner's `public_id` is preserved, so the layer stays single and idempotent.

Unit test
`TestAnnotationLayerPersistence::test_replace_recovers_from_first_write_race`
reproduces this deterministically: the winner's row is committed through a
**separate connection** (so it survives the loser's rollback), the loser's first
SELECT is stubbed to a stale empty read, the INSERT hits the real constraint,
and the test asserts the loser adopts the winner's `public_id`, the row stays
single, and its items equal the loser's write.

---

## D. P1/P2/P3/P4/P11 — durability: per-layer pending map, hydration awaits, unload flush

The shared-timer bug is replaced by an explicit model in `player.html`:

- `annotPendingSaves = {}` — one entry **per layer key**; scheduling a save for
  slide B can never cancel the still-owed save for slide A.
- `queueAnnotSave(target)` arms a single debounce timer once, which runs
  `flushAnnotSaves()`; the flush snapshots all pending targets, awaits the
  startup hydration promise, then PUTs each layer in turn. A save that fails
  keeps its local marks (retried on the next edit).
- `loadPersistedAnnotations()` returns a promise stored as `annotHydration`.
  Its merge rule now **appends** the server layer under in-progress local
  strokes (instead of `continue`), so a stroke drawn inside the hydration
  window never masks existing marks; the next PUT persists the union.
- The PUT URL uses the **captured `rawMode`** (the true view layer), never the
  normalized `syncMode()`. `syncMode()` remains the session/position
  representation; layers stay per-view.
- `pagehide`/`beforeunload` call `flushAnnotSavesOnUnload()`, which fires
  `fetch(..., { keepalive: true })` for every pending layer and clears the
  pending map so no double-send occurs.
- `annotClearAll()` queues **each cleared layer by its own key** (parsed back
  from `"mode:index"`), so every cleared layer is deleted server-side — none
  can resurrect.

E2E regressions pin each behaviour: two strokes drawn inside the debounce
window both persist across reload (P2); clear-all stays cleared after reload
(P3); a visual-mode stroke lives under a `visual:` layer, never `learning:`, and
restores after reload (P1+P7).

---

## E. P7 — one index space per deck

The decks disagree on cardinality: `source` is 1:1 with `sourceUnits`, learning
has two framing slides per topic, and visual/animation have **one slide per
topic**. Everything now consults `deckLength()`:

- `goTo`/`nextSlide`/`prevSlide`/`End` (`goTo(deckLength()-1)`)/`updateChrome`/
  `startIndexFromUrl` clamp to the active deck's real length.
- `buildThumbnails()` renders topic-indexed thumbnails in visual/animation so
  click `i -> goTo(i)` renders `topics[i]`.
- `setPlayerMode()` books `currentSourceSlide`/`currentLearningSlide` **only
  while in those modes**, and entering visual/animation maps `current` onto the
  current learning slide's `topicIdx` before clamping — so deep navigation no
  longer lands on a topic-index that is really a learning slide index.
- `syncTopic()` and `finishLesson()` send `sessionIndex()` — the active deck's
  index translated back into the source/learning session space (visual/
  animation report their topic's concept slide `idx*2`) — while keeping
  `mode: syncMode()`.

The frontend contract test `test_sync_topic_sends_mode_parameter` was updated
to assert the new mode-aware payload (`slide_index: sessionIndex(), mode:
syncMode()`) and the presence of `sessionIndex()`.

---

## F. Security properties

- No new endpoints, models, or migrations were added; the affected route surface
  is unchanged and remains owner-scoped (`_owned_lesson` -> 403) and
  mode-validated (422), plus layer reads filtered by `user_id`.
- `IntegrityError` handling only touches an already-authenticated owner writing
  their own layer key; the re-select repeats the same owner/lesson filter.
- Annotation items are still validate-don't-parse (`parse_annotations`), and the
  frontend still renders from a closed item schema; no new HTML/JS sink.
- Secret scan across the full diff: clean.
- The unload flush uses `keepalive: true` with the same
  `Authorization` header helper already used by `finishLesson`.

---

## G. Test evidence (all run against `py -3.11`, fresh test DB per run)

- `ruff check app tests` — **clean** (no findings on any changed file).
- `node --check` on the extracted `player.html` script block — **clean**.
- Unit — **1606 passed** (`tests/unit`; baseline 1605 + 1 new F3 race test,
  updated frontend-contract assertion).
- Integration — **215 passed** (`tests/integration`; baseline 211 + 4 new
  `test_annotation_layers_api.py` tests: all-mode round trip + isolation,
  empty-items delete, non-owner 403 on read+write, invalid mode/index 422).
- E2E (`pytest -m e2e`, real Chrome) — presentation-player suite
  **13/13 passed** (baseline 10 + 3 new durability regressions).
- A 700 ms debounce remains (batched), so the reload E2E still waits for the
  flush before asserting the backend row.

---

## H. Deliverables

One atomic commit on `feature/individual-user-foundation` (baseline `8a331a8`),
working tree clean afterwards, no push/PR. Files in the change:

- `backend/app/services/presentation_annotation_service.py`
- `backend/frontend/player.html`
- `backend/tests/unit/test_presentation_annotation_service.py`
- `backend/tests/unit/test_player_teaching_tools_contract.py`
- `backend/tests/integration/test_annotation_layers_api.py` (new)
- `backend/tests/e2e/test_presentation_player_tools.py`
- `backend/docs/audits/NEXT_MILESTONE_IMPLEMENTATION_REPORT.md` (this report)

---

## I. Known limitations and next milestones (PLANNED)

Existing data written before this change: visual/animation strokes that were
previously mis-saved under `learning:{index}` stay there (they already appeared
on the learning deck). No data migration back-fills them; new strokes go to the
correct layer. This is disclosed, not corrected.

Deferred audit findings, in priority order for the next milestone:

1. **F1 — learning-mode completion drift** (`lesson_player_service.py`):
   `_session_total_slides` uses `max(source_count, total_topics*2)`, so a deck
   whose source count exceeds `2 x topics` can never report 100%.
2. **B1 — quiz-generation IDOR** (`quiz_generation_service.py`): the generation
   path loads a lesson by `public_id` without an owner check.
3. **F2 — session uniqueness** and **F4 — stale-write conflict detection**
   (detect concurrent saves by version/Etag rather than last-write-wins).

---

## J. Next steps

Merge/verify this slice as the durability baseline; then implement **F1**
(learning-mode completion correctness) as the next single milestone, following
the same verify-document-commit pattern. No WCAG claims are made in this report.