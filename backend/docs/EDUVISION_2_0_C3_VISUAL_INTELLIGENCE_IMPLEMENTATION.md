# EduVision 2.0 Checkpoint C3 — Topic-Level Visual Intelligence Engine Implementation Report

**Status:** PASS
**Branch:** `feature/individual-user-foundation`
**Database:** PostgreSQL (Alembic Head: `0035_c3_topic_visual_assets`, single head)
**E2E Playwright Browser Gate:** PASS (100%) — `upload → auto C3 generation → Visual Mode → topic/subtopic context → reload persistence → download`, zero console/network errors
**Screenshot Evidence:** `backend/docs/screenshots/c3_visual_intelligence_verified.png`
**Auto-Trigger Gate:** PASS — C3 assets appear automatically after C2 regeneration with **no** manual call to `POST /api/v1/c3/visuals/generate`
**Student Quality Gate (C3.15):** 10 / 10 criteria PASSED
**Automated Unit & Integration Test Suite:** PASS (baseline 1388 passing, C3 suite green)

> Scope note: C3 delivers **topic-level** and **subtopic-aware** visuals. C4–C8 features (slide-level narration, adaptive pacing, etc.) are explicitly out of scope here.

---

## 1. Executive Summary

Checkpoint C3 completes the architectural transformation of EduVision AI from text-only lessons into a **topic-level visual intelligence engine**. Given the C2 pedagogical hierarchy, C3 automatically decides whether a learner genuinely benefits from a diagram, selects the most pedagogically appropriate visual type, produces a fully structured **specification** (nodes, edges, steps, columns, labels, relationships), renders a deterministic **SVG**, and attaches a student-facing explanation, concept grounding, and source references for every visual.

The killer distinction of C3: visuals are **topics/subtopics**, not slides. Every asset is placed at the exact C2 outline topic + subtopic it illustrates, keyed by the outline's canonical title so the learner player can resolve each Visual-Mode slide to its asset regardless of lesson-block heading wording.

---

## 2. C2 Dependency

- C3 consumes the **C2 outline** (`topic_outlines.topics` JSONB) as its source of truth for topics, subtopics, concepts, learning objectives, and source references.
- C3's generation **auto-trigger** fires off the **`/topics/regenerate`** request: when a C2 outline completes, `PresentationService` dispatches the C3 Celery task automatically.
- C3 enhances the **C2/dual-mode player** (`player.html`) with a new **Visual Mode** (`#btnModeVisual`) alongside Source and Learning modes.

---

## 3. C3 Objective

1. Produce a **topic/subtopic-aware** visual for every pedagogical topic that benefits from one.
2. Auto-dispatch generation immediately when a C2 outline becomes ready (no manual UI action).
3. Key assets by the C2 outline's canonical **topic title** so the player resolves visuals reliably.
4. Render **deterministic SVG** (not free-form AI images) for reproducibility + auditability.
5. Attach purpose, learning objective, explanation (why/how/takeaway), concepts, and source grounding to every asset.
6. Persist assets and serve them through REST endpoints (list, ready, svg, download) with strict ownership.
7. Verify the whole flow in a real browser: upload → auto C3 → Visual Mode → context → persistence → download, with **zero console/network errors**.

---

## 4. Problem Statement

Prior to C3:
- Lessons rendered as plain text blocks with no diagrams; learners could not "see" a network, a protocol stack, or a process.
- Any prior visual system was slide-bound and one-visual-per-slide, and did not describe *why* a learner needed a given visual.
- There was no auto-trigger: generation required an explicit manual call, so a freshly regenerated outline produced no visuals until a user asked for them.
- The player's topic lookup used the raw lesson-block heading, which could drift from the outline's canonical title (e.g., a lesson intro block named after a C2 *section*), leaving a Visual-Mode slide empty.

---

## 5. Existing Architecture

- **Player delivery:** `LessonPlayerService` serves the composite player session (`GeneratedLesson` + `ContentUnit` blocks + `TopicOutline` metadata).
- **Outline storage:** `TopicOutlineRepository` + `topic_outlines.topics` JSONB.
- **Lesson generation:** `LessonGenerationService` produces `GeneratedBlock`s whose `heading` feeds the player topics.
- **Task infra:** Celery (`celery_app`), `safe_dispatch`, `eager_mode` support.

---

## 6. C3 Root Cause

Two concrete defects drove the C3 engine:

1. **No visual pipeline existed** — lessons were text-only, and there was no structured path from a C2 topic to a diagram to a rendered asset.
2. **Player topic→asset resolution was fragile** — the player keyed visuals by `c3VisualsByTopic[t.title]` using the raw lesson-block heading, while the backend keyed assets by the canonical outline title. When a lesson had an introductory block titled with a C2 *section* name, its Visual-Mode slide resolved to "no visual" even though the topic actually had one.

---

## 7. Target Architecture

```text
C2 Outline (TopicOutlineService)
        │
        ▼
C3VisualPlanningPipeline (plan_presentation_visuals)
        │  per topic/subtopic
        ▼
C3VisualNeedAnalyzer ── need analysis (visual_needed, suggested_type, reason)
        │
        ▼
C3VisualSpecGenerator ── structured VisualSpecification (nodes/edges/steps/columns/...)
        │
        ▼
C3SvgRenderer ── deterministic render_visual(spec) → SVG (XSS-escaped)
        │
        ▼
Validation gate (`_validate_rendered_output`) — well-formed, substantive SVG
        │
        ▼
TopicVisualAssetRepository.generate_and_persist_visual → topic_visual_assets row
        │
        ▼
C3 REST API + Celery task (auto-triggered) + Player Visual Mode
```

---

## 8. Pre-C3 Data Flow

```text
C2 Outline ──> Lesson text blocks ──> Player Learning Mode (text only)
   (no diagrams, no auto-trigger, lesson-heading-only topic lookup)
```

---

## 9. Post-C3 Data Flow

```text
Upload PPTX
   │
   ▼
Extract (C1) ──> C2 Topic Outline ──> /topics/regenerate
   │
   ▼
[AUTO-TRIGGER] PresentationService._trigger_c3_visual_generation
   │  (only after outline is SUCCEEDED)
   │
   ▼
Celery: eduvision.c3.generate_visuals
   │
   ▼
Plan → Need analysis → Spec → Deterministic SVG → Validate → Persist (READY)
   │
   ▼
C3 API (list/ready/svg/download) ──> Player Visual Mode (topic/subtopic context)
   │
   ▼
Reload persistence + SVG download
```

---

## 10. Topic Semantics

A **topic** is a C2 `OutlineTopic` — an educational unit with a canonical `title`, `section`, subtopics, concepts, objectives, and source refs. C3's planner iterates these topics. The canonical `title` doubles as the **asset key** (`TopicVisualAsset.topic_id` / `topic_title`) so any consumer can map a topic to its visuals unambiguously.

---

## 11. Subtopic Semantics

Each topic's `subtopics` are analyzed individually. The relationship triggering a visual can be defined at the **subtopic level**: e.g., the topic *Physical Transmission Media* produces a *Comparison* visual proving the pedagogy of its subtopic *Copper Media Standards*. Every asset records `subtopic_id`/`subtopic_title`, so a single topic may yield multiple visuals — one per visual-worthy subtopic. This is the opposite of one-visual-per-slide.

---

## 12. Concept Semantics

The planner attaches **concept ids** (`topic_id:concept_name`) to each asset, drawn from the subtopic's concepts. The SVG renders concept labels; the player shows them as `c3-concept-chip` badges. `concept_ids` enable deduplication via `compute_visual_fingerprint`.

---

## 13. Educational Metadata

Every asset persists:
- `purpose` (one-line pedagogy) and `learning_objective` (verifiable action).
- `explanation` JSON: `what_you_see`, `how_to_read`, `key_takeaway`, `real_world_example`, `common_mistake`.
- `source_references` for grounding to source slides/units.

---

## 14. Source Provenance

Each asset records a `provenance` of `SourceVisualProvenance`: `source_derived`, `ai_explained`, or `ai_illustrative`. In the real E2E flow all ready assets are `ai_explained` (derived deterministically from the grounded outline, framed pedagogically). The player surfaces `c3-source-ref` chips that jump back to Source Mode.

---

## 15. AI / SOURCE Separation

C3 **never** overwrites the C1 source truth. Assets are generated *from* the C2 outline (which itself is grounded in C1), and every asset is validated for correctness and safety independently of the AI/source provenance assignment. Rendering is fully deterministic (no LLM image generation), so the *content* is source-grounded while the *rendering* is reproducible.

---

## 16. AI Pipeline

- `analyze_visual_need(...)` determines visual necessity, suggested type, and confidence using deterministic pedagogical rules (modality, complexity, comparison/sequence signals).
- `generate_visual_specification(...)` builds the structured `VisualSpecification`.
- These are **rule-based/deterministic**; they do not depend on an external vision model, which guarantees reproducibility and zero-cost re-runs.

---

## 17. Prompt / Structured Output

C3 uses structured Pydantic schemas (`VisualSpecification`, `VisualNeedDecision`, `VisualExplanation`, `TopicVisualPlan`, `PresentationVisualPlan`) as the single contract between planning, rendering, persistence, and the player. Generation is deterministic, so there is no free-text prompt drift.

---

## 18. Data Model

`topic_visual_assets` table:
- `id` (UUID PK), `public_id` (unique), `presentation_id` (FK, indexed), `owner_id`.
- `topic_id`, `topic_title`, `subtopic_id`, `subtopic_title`, `concept_ids` (JSONB).
- `visual_type`, `status`, `provenance`, `asset_format`, `asset_content` (text SVG), `asset_key`.
- `purpose`, `learning_objective`, `explanation` (JSONB), `source_references` (JSONB), `specification` (JSONB).
- `fingerprint` (deterministic, unique), `version`, timestamps.

---

## 19. Database Impact

A single new table `topic_visual_assets` (owned, indexed on `presentation_id` and `owner_id`). No schema changes to existing tables.

---

## 20. Migration Impact

`0035_c3_topic_visual_assets` adds the table (idempotent, transactional DDL). Verified as the **single** Alembic head on PostgreSQL. `alembic current` and `alembic heads` both report `0035_c3_topic_visual_assets (head)`.

---

## 21. API Changes

- `POST /api/v1/c3/visuals/generate` — manual generation entrypoint (contract-compliant; used by API tests). Role: resume hint only, not required for the automatic flow.
- `GET /api/v1/c3/visuals/presentation/{presentation_id}` — list assets.
- `GET /api/v1/c3/visuals/presentation/{presentation_id}/ready` — ready/active assets (used by the player).
- `GET /api/v1/c3/visuals/{visual_id}/svg` — raw SVG.
- `GET /api/v1/c3/visuals/{visual_id}/download` — downloadable SVG.
- Router: `app/api/v1/c3_visual_router.py`; responses: `C3VisualAssetResponse`; ownership enforced via `get_by_id_and_user`.

---

## 22. Frontend Integration

`backend/frontend/player.html` adds **Visual Mode**:
- `#btnModeVisual` toggles Visual Mode; `renderVisualSlide(idx)` renders the C3 container, type badge, deterministic SVG, explanation panel, concept chips, and source refs.
- `fetchC3Visuals()` loads `presentation/{id}/ready` and builds `c3VisualsByTopic`.
- Topic→asset resolution now falls back through: exact `t.title` → case-insensitive key → `t.outline_title` (canonical outline title, from the backend fix) → server-provided `t.visuals[0]`. This closes the C3.14 badge bug (section-named lesson intro blocks now resolve the correct topic's asset).

---

## 23. Ownership / Security

- Every asset is owned by the presentation owner; reads/writes flow through `get_by_id_and_user` and presentation-scoped queries constrained by the authenticated user.
- User-derived text (titles, concept names, subtopics) is **escaped** during rendering — `<script>`/`onload` injection is blocked and persisted output is escaped while raw metadata stays structured (verified by `test_c3_quality_02/03`).
- `fingerprint` uniqueness prevents duplicate blinded assets for the same topic/subtopic/concept set.

---

## 24. Failure & Fallback

- Validation gate rejects malformed/too-short/non-SVG output and records `FAILED` without persisting a broken asset.
- Render-level exceptions mark the plan `FAILED` with an `error_message`; nothing is persisted.
- Before a C2 outline exists, the auto-trigger logs `c3_skipped_no_outline` and no-ops (verified by the auto-trigger gate).
- The player degrades gracefully: loading state → `c3-visual-empty` → `c3-visual-error` as appropriate.

---

## 25. Caching

- `_load_topic_visuals` builds an in-memory `topic_title → [asset]` map per player session (case-insensitive), so ready assets are served without re-querying per slide.
- Assets are persisted in PostgreSQL; no repeated deterministic re-render on page reload (reload persistence verified in browser).

---

## 26. Regeneration

`/topics/regenerate` invalidates prior visuals and re-dispatches C3 automatically:
```text
regenerate_topics() ── commit ── _trigger_c3_visual_generation()
```
If dispatch fails, `c3_visual_regeneration_failed_after_topic_regenerate` is logged and the error surfaced without corrupting the outline.

---

## 27. Performance

- Planning is O(outline topics × subtopics); rendering is deterministic and cheap (SVG string building).
- The Celery worker runs with concurrency 1 (solo) during the E2E gate; ready assets within seconds of auto-trigger.
- `_load_topic_visuals` amortizes per-session lookups.

---

## 28. Observability

Structured logs include:
- `c3_skipped_no_outline`, `c3_visual_generation_dispatched`.
- `c3_generate_visuals_task_started` / `c3_generate_visuals_task_completed` (worker lifecycle).
- `c3_visual_regeneration_failed_after_topic_regenerate`.
The auto-trigger gate correlates the C3 task `request_id` with the `/topics/regenerate` `request_id`, proving dispatch provenance.

---

## 29. Tests

New C3 suite (all passing):
- `test_c3_visual_quality.py` — every type renders valid SVG, escaping, persistence, validation gate, render-failure, deterministic need analysis.
- `test_c3_visual_api.py` / `test_c3_visual_contract.py` — API + ownership.
- `test_c3_visual_pipeline.py` / `test_c3_visual_planning` / `test_c3_visual_spec_generator.py` — planning/spec.
- `test_c3_visual_tasks.py` / `test_c3_visual_tasks_reliability.py` / `test_c3_visual_auto_trigger.py` — auto-trigger + worker reliability.
- `test_c3_visual_player.py` — player topic→asset alignment (outline_title fix).
- `test_c3_svg_renderer.py` / `test_c3_gemini_off.py` — renderer + deterministic-without-Gemini.
- `test_c3_visual_coverage.py` — coverage/coverage semantics.
Baseline 1388 tests pass; C3 contributes a green, focused suite.

---

## 30. Browser Verification

`scripts/verify_c3_browser.py` drives a real Chromium session:
1. register → 2. create presentation → 3. upload PPTX → 4. extraction ready → 5. baseline: 0 C3 assets before outline → 6. `/topics/regenerate` (only user action) → 7. **3 C3 assets appear automatically** → 8. SVG + download endpoints → 9. lesson ready → 10. Player: Visual Mode active, C3 container, type badge, deterministic SVG, explanation, concept chips, source refs, download button → 11. source jump → 12. reload persistence.
**Console errors: 0, Network errors: 0, 404/500: 0.** Screenshot saved to `backend/docs/screenshots/c3_visual_intelligence_verified.png`.

---

## 31. Known Limitations

- Visual *type* choice is rule-based; extremely novel diagrams could benefit from more heuristics (out of scope).
- `asset_content` is inline SVG text (no raster/object storage key yet; storage integration is a later checkpoint).
- Deterministic SVG favours diagram clarity over photorealistic illustration; that is by design.

---

## 32. C3 Scope Boundary

Delivered in scope: topic/subtopic visual intelligence, auto-trigger, deterministic SVG, REST + ownership, frontend Visual Mode, persistence, download, quality gate, browser E2E, doc.
Out of scope (C4–C8): slide-level narration, adaptive pacing, collaborative annotation, cross-learner personalization, mobile-native authoring. Nothing in C4–C8 was implemented.

---

## 33. C4 / C5 Readiness

- C4 (learner journey/pacing) can consume `learning_objective` + concept ids for each asset.
- C5 (assessment) can reference `concept_ids` from visuals for question-authoring.
- The asset keyed by canonical outline title makes these later checkpoints trivial to join.

---

## 34. Reproduction Commands

### 1. Run the browser E2E gate (upload → auto C3 → Visual Mode → reload → download)
```powershell
# Precondition: FastAPI (127.0.0.1:8000), Celery on redis://localhost:6380,
# PostgreSQL 5432. Celery task auto-registered as eduvision.c3.generate_visuals.
cd backend
.venv\Scripts\python.exe scripts\verify_c3_browser.py
# Expect: ALL PASSED (100%); console errors 0; network errors 0
# Screenshot: backend\docs\screenshots\c3_visual_intelligence_verified.png
```

### 2. Run the C3.15 student quality gate
```powershell
cd backend
.venv\Scripts\python.exe scripts\verify_c3_quality.py
# Expect: 10 / 10 criteria PASSED (100%)
```

### 3. Unit & integration tests
```powershell
cd backend
.venv\Scripts\python.exe -m pytest tests -q
# Expect: baseline 1388 passing green, C3 suite green
```

### 4. Lint & types
```powershell
cd backend
.venv\Scripts\Scripts\ruff.exe check app tests scripts
.venv\Scripts\Scripts\ruff.exe format --check app tests scripts
.venv\Scripts\Scripts\mypy.exe app
```

### 5. Verify database head
```powershell
cd backend
.venv\Scripts\python.exe -m alembic heads
.venv\Scripts\python.exe -m alembic current
# Both report: 0035_c3_topic_visual_assets (head)
```

### 6. Auto-trigger (no manual C3 call) proof
```powershell
cd backend
.venv\Scripts\python.exe scripts\verify_c3_autotrigger.py
```

---

## 35. Git / Changeset Evidence

### Modified Files:
- `backend/app/main.py` — register C3 visual router.
- `backend/app/middleware/exception_handler.py` — C3 exception handling.
- `backend/app/models/__init__.py` — export `TopicVisualAsset`.
- `backend/app/schemas/player.py` — `outline_title`/`visuals` on player topics.
- `backend/app/schemas/topic_outline.py` — outline schema additions for C3.
- `backend/app/services/lesson_player_service.py` — `_extract_topics` aligns visuals to canonical outline title; emits `outline_title`.
- `backend/app/services/presentation_service.py` — auto-trigger of C3 on `/topics/regenerate`.
- `backend/app/services/topic_outline_service.py` — outline normalization hooks.
- `backend/app/workers/celery_app.py` — registers `app.workers.c3_visual_tasks`.
- `backend/frontend/player.html` — Visual Mode + topic→asset fallback resolution.
- `backend/app/parsers/document_parser.py`, `backend/tests/unit/test_document_parser.py` — parser robustness.

### Added Files:
- `backend/app/api/v1/c3_visual_router.py`
- `backend/app/database/migrations/versions/0035_c3_topic_visual_assets.py`
- `backend/app/models/topic_visual_asset.py`
- `backend/app/repositories/topic_visual_asset_repository.py`
- `backend/app/schemas/c3_visual_intelligence.py`
- `backend/app/services/c3_svg_renderer.py`
- `backend/app/services/c3_visual_need_analyzer.py`
- `backend/app/services/c3_visual_planning_pipeline.py`
- `backend/app/services/c3_visual_spec_generator.py`
- `backend/app/workers/c3_visual_tasks.py`
- `backend/scripts/verify_c3_browser.py`, `verify_c3_quality.py`, `verify_c3_autotrigger.py`
- `backend/tests/unit/test_c3_*.py` (13 C3 test modules)
- `backend/tests/fixtures/computer_networks_sample.pptx`, `backend/docs/screenshots/c3_visual_intelligence_verified.png`