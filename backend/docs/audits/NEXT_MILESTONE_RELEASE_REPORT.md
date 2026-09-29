# Annotation Layer Durability — Release Report

> Milestone: **Annotation layer durability (no stroke silently lost; every layer bound to its own view)**
> Commit: `4691e9a` on `feature/individual-user-foundation` (baseline `8a331a8`).

## What was implemented

Frontend (`backend/frontend/player.html`)

1. Strokes now persist under the **actual view layer** (`rawMode`), never the
   normalized `syncMode()` — visual/animation marks restore to Visual/Animation
   Mode instead of vanishing into the `learning` layer.
2. Replaced the single shared debounce timer (which cancelled earlier pending
   saves) with a **per-layer pending-save map** + single flush: drawing on slide
   A then slide B within 700 ms persists both.
3. `annotClearAll()` queues **every** cleared layer by its own key, so clearing
   stays cleared after reload instead of resurrecting stale marks.
4. New `pagehide`/`beforeunload` flush with `fetch(..., { keepalive: true })`
   so tab close/reload can no longer drop un-flushed strokes.
5. Startup hydration is awaited before any save, and server marks are merged
   under in-progress local strokes, so a fast first save can no longer clobber
   marks that were still loading.
6. Deck index spaces are now mode-aware (`deckLength()`/`sessionIndex()`):
   navigation, thumbnails, mode switching, and session sync agree with the
   visual/animation decks (one slide per topic) instead of the learning deck
   (two slides per topic) — fixing both "Topic not found." overshoot and
   annotations attaching to the wrong slide.

Backend (`backend/app/services/presentation_annotation_service.py`)

7. `replace()` recovers from the concurrent first-write race: on
   `IntegrityError` it rolls back, re-selects, and adopts the winner row,
   folding the write on top — concurrent layer PUTs no longer 500 and the
   layer key stays a single deterministic row.

Tests

8. New unit race test, a new integration suite (`test_annotation_layers_api.py`:
   all-mode round trip, empty-items delete, non-owner 403, invalid input 422),
   and three browser regressions (rapid multi-slide persistence, visual-layer
   persistence, clear-all persistence).

## Verification (all `py -3.11`, fresh test DB)

- Unit: **1606 passed** (baseline 1605 + F3 race test; updated frontend contract).
- Integration: **215 passed** (baseline 211 + 4).
- Presentation-player E2E (real Chrome): **13/13 passed** (baseline 10 + 3).
- `ruff check app tests`: clean. `node --check` on player.html script: clean.
- Full-diff secret scan: clean.

## Commit

`4691e9a` — `fix(player): make annotation layers durable and view-accurate`
(7 files, +832/−24). Tree clean afterwards. **Push: NO. PR: NO.**

## Known limitations

- Visual/animation strokes **mis-persisted earlier** (under `learning:N`) remain
  there; no back-fill migration (the fix stops new data loss).
- Annotation layers are still last-write-wins with no version/conflict
  detection (F4 from the audit remains planned).
- 700 ms debounce batches saves by design; offline edits keep local marks and
  retry on the next edit (no offline queue yet).

## Next milestone (recommended)

**F1 — learning-mode completion drift**: `lesson_player_service._session_total_slides`
uses `max(source_count, total_topics*2)`, so a deck whose source count exceeds
`2 x topics` can never reach 100% completion. Second candidate: **B1 —
quiz-generation IDOR** (lesson loaded by `public_id` without an owner check).